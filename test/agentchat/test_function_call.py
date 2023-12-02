try:
    from openai import OpenAI
except ImportError:
    OpenAI = None
import pytest
import asyncio
import json
import autogen
from autogen.math_utils import eval_math_responses
from test_assistant_agent import KEY_LOC
import sys


@pytest.mark.skipif(OpenAI is None, reason="openai>=1 not installed")
def test_eval_math_responses():
    config_list = autogen.config_list_from_models(
        KEY_LOC, exclude="aoai", model_list=["gpt-4-0613", "gpt-3.5-turbo-0613", "gpt-3.5-turbo-16k"]
    )
    functions = [
        {
            "name": "eval_math_responses",
            "description": "Select a response for a math problem using voting, and check if the response is correct if the solution is provided",
            "parameters": {
                "type": "object",
                "properties": {
                    "responses": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The responses in a list",
                    },
                    "solution": {
                        "type": "string",
                        "description": "The canonical solution",
                    },
                },
                "required": ["responses"],
            },
        },
    ]
    client = autogen.OpenAIWrapper(config_list=config_list)
    response = client.create(
        messages=[
            {
                "role": "user",
                "content": 'evaluate the math responses ["1", "5/2", "5/2"] against the true answer \\frac{5}{2}',
            },
        ],
        functions=functions,
    )
    print(response)
    responses = client.extract_text_or_completion_object(response)
    print(responses[0])
    function_call = responses[0].function_call
    name, arguments = function_call.name, json.loads(function_call.arguments)
    assert name == "eval_math_responses"
    print(arguments["responses"])
    # if isinstance(arguments["responses"], str):
    #     arguments["responses"] = json.loads(arguments["responses"])
    arguments["responses"] = [f"\\boxed{{{x}}}" for x in arguments["responses"]]
    print(arguments["responses"])
    arguments["solution"] = f"\\boxed{{{arguments['solution']}}}"
    print(eval_math_responses(**arguments))


def test_json_extraction():
    from autogen.agentchat import UserProxyAgent

    user = UserProxyAgent(name="test", code_execution_config={"use_docker": False})

    jstr = '{\n"location": "Boston, MA"\n}'
    assert user._format_json_str(jstr) == '{"location": "Boston, MA"}'

    jstr = '{\n"code": "python",\n"query": "x=3\nprint(x)"}'
    assert user._format_json_str(jstr) == '{"code": "python","query": "x=3\\nprint(x)"}'

    jstr = '{"code": "a=\\"hello\\""}'
    assert user._format_json_str(jstr) == '{"code": "a=\\"hello\\""}'


def test_execute_function():
    from autogen.agentchat import UserProxyAgent

    # 1. test calling a simple function
    def add_num(num_to_be_added):
        given_num = 10
        return num_to_be_added + given_num

    user = UserProxyAgent(name="test", function_map={"add_num": add_num})

    # correct execution
    correct_args = {"name": "add_num", "arguments": '{ "num_to_be_added": 5 }'}
    assert user.execute_function(func_call=correct_args)[1]["content"] == "15"

    # function name called is wrong or doesn't exist
    wrong_func_name = {"name": "subtract_num", "arguments": '{ "num_to_be_added": 5 }'}
    assert "Error: Function" in user.execute_function(func_call=wrong_func_name)[1]["content"]

    # arguments passed is not in correct json format
    wrong_json_format = {
        "name": "add_num",
        "arguments": '{ "num_to_be_added": 5, given_num: 10 }',
    }  # should be "given_num" with quotes
    assert "You argument should follow json format." in user.execute_function(func_call=wrong_json_format)[1]["content"]

    # function execution error with wrong arguments passed
    wrong_args = {"name": "add_num", "arguments": '{ "num_to_be_added": 5, "given_num": 10 }'}
    assert "Error: " in user.execute_function(func_call=wrong_args)[1]["content"]

    # 2. test calling a class method
    class AddNum:
        def __init__(self, given_num):
            self.given_num = given_num

        def add(self, num_to_be_added):
            self.given_num = num_to_be_added + self.given_num
            return self.given_num

    user = UserProxyAgent(name="test", function_map={"add_num": AddNum(given_num=10).add})
    func_call = {"name": "add_num", "arguments": '{ "num_to_be_added": 5 }'}
    assert user.execute_function(func_call=func_call)[1]["content"] == "15"
    assert user.execute_function(func_call=func_call)[1]["content"] == "20"

    # 3. test calling a function with no arguments
    def get_number():
        return 42

    user = UserProxyAgent("user", function_map={"get_number": get_number})
    func_call = {"name": "get_number", "arguments": "{}"}
    assert user.execute_function(func_call)[1]["content"] == "42"


@pytest.mark.asyncio
async def test_a_execute_function():
    from autogen.agentchat import UserProxyAgent
    import time

    # Create an async function
    async def add_num(num_to_be_added):
        given_num = 10
        time.sleep(1)
        return num_to_be_added + given_num

    user = UserProxyAgent(name="test", function_map={"add_num": add_num})
    correct_args = {"name": "add_num", "arguments": '{ "num_to_be_added": 5 }'}

    # Asset coroutine doesn't match.
    assert user.execute_function(func_call=correct_args)[1]["content"] != "15"
    # Asset awaited coroutine does match.
    assert (await user.a_execute_function(func_call=correct_args))[1]["content"] == "15"

    # function name called is wrong or doesn't exist
    wrong_func_name = {"name": "subtract_num", "arguments": '{ "num_to_be_added": 5 }'}
    assert "Error: Function" in (await user.a_execute_function(func_call=wrong_func_name))[1]["content"]

    # arguments passed is not in correct json format
    wrong_json_format = {
        "name": "add_num",
        "arguments": '{ "num_to_be_added": 5, given_num: 10 }',
    }  # should be "given_num" with quotes
    assert (
        "You argument should follow json format."
        in (await user.a_execute_function(func_call=wrong_json_format))[1]["content"]
    )

    # function execution error with wrong arguments passed
    wrong_args = {"name": "add_num", "arguments": '{ "num_to_be_added": 5, "given_num": 10 }'}
    assert "Error: " in (await user.a_execute_function(func_call=wrong_args))[1]["content"]

    # 2. test calling a class method
    class AddNum:
        def __init__(self, given_num):
            self.given_num = given_num

        def add(self, num_to_be_added):
            self.given_num = num_to_be_added + self.given_num
            return self.given_num

    user = UserProxyAgent(name="test", function_map={"add_num": AddNum(given_num=10).add})
    func_call = {"name": "add_num", "arguments": '{ "num_to_be_added": 5 }'}
    assert (await user.a_execute_function(func_call=func_call))[1]["content"] == "15"
    assert (await user.a_execute_function(func_call=func_call))[1]["content"] == "20"

    # 3. test calling a function with no arguments
    def get_number():
        return 42

    user = UserProxyAgent("user", function_map={"get_number": get_number})
    func_call = {"name": "get_number", "arguments": "{}"}
    assert (await user.a_execute_function(func_call))[1]["content"] == "42"


@pytest.mark.skipif(
    not OpenAI or not sys.version.startswith("3.10"),
    reason="do not run if openai is not installed or py!=3.10",
)
def test_update_function():
    config_list_gpt4 = autogen.config_list_from_json(
        "OAI_CONFIG_LIST",
        filter_dict={
            "model": ["gpt-4", "gpt-4-0314", "gpt4", "gpt-4-32k", "gpt-4-32k-0314", "gpt-4-32k-v0314"],
        },
    )
    llm_config = {
        "config_list": config_list_gpt4,
        "seed": 42,
        "functions": [],
    }

    user_proxy = autogen.UserProxyAgent(
        name="user_proxy",
        human_input_mode="NEVER",
        is_termination_msg=lambda x: True if "TERMINATE" in x.get("content") else False,
    )
    assistant = autogen.AssistantAgent(name="test", llm_config=llm_config)

    # Define a new function *after* the assistant has been created
    assistant.update_function_signature(
        {
            "name": "greet_user",
            "description": "Greets the user.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        is_remove=False,
    )
    user_proxy.initiate_chat(
        assistant,
        message="What functions do you know about in the context of this conversation? End your response with 'TERMINATE'.",
    )
    messages1 = assistant.chat_messages[user_proxy][-1]["content"]
    print(messages1)

    assistant.update_function_signature("greet_user", is_remove=True)
    user_proxy.initiate_chat(
        assistant,
        message="What functions do you know about in the context of this conversation? End your response with 'TERMINATE'.",
    )
    messages2 = assistant.chat_messages[user_proxy][-1]["content"]
    print(messages2)
    # The model should know about the function in the context of the conversation
    assert "greet_user" in messages1
    assert "greet_user" not in messages2


if __name__ == "__main__":
    # test_json_extraction()
    # test_execute_function()
    test_update_function()
    asyncio.run(test_a_execute_function())
    test_eval_math_responses()
