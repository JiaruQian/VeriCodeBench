# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from src.utils import log_time
import json
from logging import getLogger
import os
import time
import httpx
import random

import google.generativeai as genai
from google.generativeai import types
from openai import AzureOpenAI, OpenAI


from src import local_mcp as MCP
from src.env import Dialog, Message
from src.utils import (
    retry_on_resource_exhausted,
    retry_on_transient_errors,
    timeout_in_thread,
)
from src.vllm import get_vllm_base_url, get_vllm_model_path


logger = getLogger()


def chat(
    dialog: Dialog,
    model: str,
    temperature: float,
    use_mcp: bool = False,
    max_tool_iterations: int = 5,
) -> Message:
    if model.startswith("gemini"):
        return chat_gemini(dialog, model, temperature, use_mcp, max_tool_iterations)
    elif model.startswith("gpt"):
        # temperature not supported for GPT
        return chat_openai(dialog, model, use_mcp, max_tool_iterations)
    elif "vllm" in model:
        # Default to vLLM for other models
        # Note: not all of them may support tool use and formatting may need
        # to be adjusted
        return chat_vllm(dialog, temperature, use_mcp, max_tool_iterations)
    elif "claude" in model:
        return chat_llama_api(dialog, model, temperature, use_mcp, max_tool_iterations)
    else:
        raise ValueError(f"Unsupported model: {model}")


@log_time
def chat_openai(
    dialog: Dialog,
    model: str,
    use_mcp: bool = False,
    max_tool_iterations: int = 5,
) -> Message:
    """
    Chat with MCP tool support.
    """
    if use_mcp:
        # Get MCP tools
        tools = MCP.list_tools(
            filter_names=["lean_loogle", "leanexplore_search"],
            format="openai",
        )
        functions = [t["function"]["name"] for t in tools]
        logger.debug(f"[MCP] Received {len(tools)} functions(s): {functions}")
    else:
        tools = None
        max_tool_iterations = 0

    client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version="2024-12-01-preview",
    )

    return tool_calling_loop_openai(
        client=client,
        model=model,
        messages=dialog.to_openai(),  # mutated by the function
        tools=tools,
        max_tool_iterations=max_tool_iterations,
    )


@log_time
def chat_llama_api(
    dialog: Dialog,
    model: str,
    temperature: float,
    use_mcp: bool = False,
    max_tool_iterations: int = 5,
) -> Message:
    """
    Chat with MCP tool support.
    """
    if use_mcp:
        # Get MCP tools
        tools = MCP.list_tools(
            filter_names=["lean_loogle", "leanexplore_search"],
            format="openai",
        )
        functions = [t["function"]["name"] for t in tools]
        logger.debug(f"[MCP] Received {len(tools)} functions(s): {functions}")
    else:
        tools = None
        max_tool_iterations = 0

    api_keys = [os.getenv("LLAMA_API_KEY")]
    
    # alternative key for load balancing
    alt_key = os.getenv("LLAMA_API_KEY_2")
    if alt_key:
        api_keys.append(alt_key)

    api_key = random.choice(api_keys)

    client = OpenAI(
        base_url="https://api.llama.com/v1",
        api_key=api_key,
        timeout=None,
        max_retries=0,
    )
    
    return tool_calling_loop_llama_api(
        client=client,
        model=model,
        temperature=temperature,
        messages=dialog.to_openai(),  # mutated by the function
        tools=tools,
        max_tool_iterations=max_tool_iterations,
    )


@log_time
def chat_vllm(
    dialog: Dialog,
    temperature: float,
    use_mcp: bool = False,
    max_tool_iterations: int = 5,
) -> Message:
    """
    Chat with MCP tool support using vLLM OpenAI-compatible API.
    Assumes vLLM server is already running.
    """
    if use_mcp:
        # Get MCP tools
        tools = MCP.list_tools(
            filter_names=["lean_loogle", "leanexplore_search"],
            format="openai",
        )
        functions = [t["function"]["name"] for t in tools]
        logger.debug(f"[MCP] Received {len(tools)} functions(s): {functions}")
    else:
        tools = None
        max_tool_iterations = 0

    client = OpenAI(
        base_url=get_vllm_base_url(),
        api_key="EMPTY",  # no key needed for local vLLM but required by the class
        timeout=httpx.Timeout(600.0),  # sets connect/read/write/pool all to 600s
        max_retries=0,  # avoid long wall-times from retries
    )

    return tool_calling_loop_vllm(
        client=client,
        temperature=temperature,
        messages=dialog.to_openai(),  # mutated by the function
        tools=tools,
        max_tool_iterations=max_tool_iterations,
    )


def chat_gemini(
    dialog: Dialog,
    model: str,
    temperature: float,
    use_mcp: bool = False,
    max_tool_iterations: int = 5,
) -> Message:
    """
    Chat with MCP tool support.
    """
    if use_mcp:
        # Get MCP tools
        mcp_functions = MCP.list_tools(
            filter_names=["lean_loogle", "leanexplore_search"],
            format="gemini",
        )
        functions = [t["name"] for t in mcp_functions]
        logger.debug(f"[MCP] Received {len(mcp_functions)} functions(s): {functions}")
        tools = [types.Tool(function_declarations=[tool for tool in mcp_functions])]
    else:
        tools = None
        max_tool_iterations = 0

    model_obj = genai.GenerativeModel(model, system_instruction=dialog.system_prompt)
    return tool_calling_loop_gemini(
        model_obj=model_obj,
        contents=dialog.to_gemini(),  # mutated by the function
        tools=tools,
        temperature=temperature,
        max_tool_iterations=max_tool_iterations,
    )


TOOL_LOOP_MESSAGE = """
You have up to {remaining} tool calls remaining.

If you decide to proceed directly to fixing the problems in the code,
please first summarize your findings from the tool calls for future reference.
I will remove your tool calls, their outputs, and the related messages from the record.
Later, you will only see what you choose to include in the summary.
"""


TOOL_LOOP_END_MESSAGE = """
You have no more tool calls remaining.

Let's proceed with the main task in two steps:

1. Summarize your findings from the tool calls for future reference.
I will remove your tool calls, their outputs, and the related messages from the record.
Later, you will only see what you choose to include in the summary.

2. Proceed to fix the problems with the code.
""".strip()


def tool_calling_loop_openai(
    client: AzureOpenAI,
    model: str,
    messages: list[dict],
    tools: list[dict] | None,
    max_tool_iterations: int,
    max_attempts: int = 10000,
    timeout: int = 600,  # 10 minutes
) -> Message:
    """
    Handles the iterative tool calling process with Azure OpenAI.

    Mutates the 'messages' list with tool calls and responses.

    Returns the next main message and the (inner) tool calling dialog.
    """

    tool_dialog = Dialog()

    @retry_on_transient_errors(max_attempts=max_attempts, base_backoff=0.5)
    @timeout_in_thread(seconds=timeout + 30)
    def generate(tools):
        """Helper to call chat completions with current state."""
        kwargs = {
            "model": model,
            "messages": messages,
            "timeout": timeout,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        start = time.monotonic()
        response = client.chat.completions.create(**kwargs)
        end = time.monotonic()
        try:
            input_tokens: int = response.usage.prompt_tokens
            output_tokens: int = response.usage.completion_tokens
        except AttributeError:
            input_tokens = 0
            output_tokens = 0
        logger.info(
            f"OpenAI response time: {end - start:.2f} s for "
            f"{input_tokens} input tokens and {output_tokens} output tokens"
        )
        return response

    for iteration in range(max_tool_iterations + 1):
        if iteration == max_tool_iterations:
            tools = None

        try:
            response = generate(tools)
        except RuntimeError as e:
            raise RuntimeError("Failed to generate response") from e

        assert len(response.choices) == 1, response
        choice = response.choices[0]
        assistant_message = choice.message

        text = assistant_message.content or ""
        tool_calls = assistant_message.tool_calls

        logger.debug(
            f"Received text={bool(text)}, tool_calls={len(tool_calls) if tool_calls else 0}"
        )

        try:
            input_tokens: int = response.usage.prompt_tokens
            output_tokens: int = response.usage.completion_tokens
        except AttributeError:
            input_tokens = 0
            output_tokens = 0
        tool_dialog.append(
            Message.assistant(
                text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )

        if not tool_calls or iteration == max_tool_iterations:
            # Done if no more tool calls or max iterations reached
            total_input_tokens: int = sum(msg.input_tokens for msg in tool_dialog)
            total_output_tokens: int = sum(msg.output_tokens for msg in tool_dialog)
            return Message.assistant(
                text, tool_dialog, total_input_tokens, total_output_tokens
            )

        # Append the assistant message with tool_calls to the conversation
        messages.append(assistant_message.model_dump())

        # Execute ALL tool calls (OpenAI can return multiple in parallel)
        for tool_call in tool_calls:
            tool_dialog.append(Message.assistant(f"function_call {tool_call.function}"))

            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            tool_result = MCP.call_tool(tool_name, tool_args)
            logger.info(f"Called MCP tool {tool_name} with arguments {tool_args}")

            # Each tool response must reference its tool_call_id
            tool_response = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(tool_result)
                if isinstance(tool_result, dict)
                else str(tool_result),
            }
            messages.append(tool_response)
            tool_dialog.append(Message.user(json.dumps(tool_response, indent=4)))

        remaining = max_tool_iterations - (iteration + 1)
        if remaining > 0:
            msg = TOOL_LOOP_MESSAGE.format(remaining=remaining)
        else:
            msg = TOOL_LOOP_END_MESSAGE
        messages.append({"role": "user", "content": msg})
        tool_dialog.append(Message.user(msg))

    raise RuntimeError("unreachable")



def tool_calling_loop_llama_api(
    client: OpenAI,
    model: str,
    temperature: float,
    messages: list[dict],
    tools: list[dict] | None,
    max_tool_iterations: int,
    max_attempts: int = 10000,
    timeout: int = 600,  # 10 minutes
) -> Message:
    """
    Handles the iterative tool calling process with Llama API.

    Mutates the 'messages' list with tool calls and responses.

    Returns the next main message and the (inner) tool calling dialog.

    For chat, API reference: https://llama.developer.meta.com/docs/api/chat/

    For tool call, API reference: https://llama.developer.meta.com/docs/features/tool-calling/
    """
    def _get_input_output_tokens(response) -> tuple[int, int]:
        try:
            input_tokens: int = 0
            output_tokens: int = 0
            for metric_dict in response.metrics:
                match metric_dict["metric"]:
                    case "num_prompt_tokens":
                        input_tokens = metric_dict["value"]
                    case "num_completion_tokens":
                        output_tokens = metric_dict["value"]
            return input_tokens, output_tokens
        except AttributeError:
            return 0, 0


    tool_dialog = Dialog()

    @retry_on_transient_errors(max_attempts=max_attempts, base_backoff=0.5)
    @timeout_in_thread(seconds=timeout + 30)
    def generate(tools):
        """Helper to call chat completions with current state."""
        kwargs = {
            "model": model,
            "messages": messages,
            "timeout": timeout,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if "claude" in model:
            kwargs["max_completion_tokens"] = 64000

        start = time.monotonic()
        response = client.chat.completions.create(**kwargs)
        end = time.monotonic()

        input_tokens, output_tokens = _get_input_output_tokens(response)

        logger.info(
            f"OpenAI response time: {end - start:.2f} s for "
            f"{input_tokens} input tokens and {output_tokens} output tokens"
        )
        return response

    for iteration in range(max_tool_iterations + 1):
        if iteration == max_tool_iterations:
            tools = None

        try:
            response = generate(tools)
        except RuntimeError as e:
            raise RuntimeError("Failed to generate response") from e

        
        assistant_message = response.completion_message

        text = assistant_message["content"]["text"] or ""
        tool_calls = assistant_message.get("tool_calls")

        logger.debug(
            f"Received text={bool(text)}, tool_calls={len(tool_calls) if tool_calls else 0}"
        )

        input_tokens, output_tokens = _get_input_output_tokens(response)

        tool_dialog.append(
            Message.assistant(
                text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )

        if not tool_calls or iteration == max_tool_iterations:
            # Done if no more tool calls or max iterations reached
            total_input_tokens: int = sum(msg.input_tokens for msg in tool_dialog)
            total_output_tokens: int = sum(msg.output_tokens for msg in tool_dialog)
            return Message.assistant(
                text, tool_dialog, total_input_tokens, total_output_tokens
            )

        # Append the assistant message with tool_calls to the conversation
        messages.append(assistant_message.model_dump())

        # Execute ALL tool calls (OpenAI can return multiple in parallel)
        for tool_call in tool_calls:
            tool_dialog.append(Message.assistant(f"function_call {tool_call['function']}"))

            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            tool_result = MCP.call_tool(tool_name, tool_args)
            logger.info(f"Called MCP tool {tool_name} with arguments {tool_args}")

            # Each tool response must reference its tool_call_id
            tool_response = {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(tool_result)
                if isinstance(tool_result, dict)
                else str(tool_result),
            }
            messages.append(tool_response)
            tool_dialog.append(Message.user(json.dumps(tool_response, indent=4)))

        remaining = max_tool_iterations - (iteration + 1)
        if remaining > 0:
            msg = TOOL_LOOP_MESSAGE.format(remaining=remaining)
        else:
            msg = TOOL_LOOP_END_MESSAGE
        messages.append({"role": "user", "content": msg})
        tool_dialog.append(Message.user(msg))

    raise RuntimeError("unreachable")




def tool_calling_loop_vllm(
    client: OpenAI,
    temperature: float,
    messages: list[dict],
    tools: list[dict] | None,
    max_tool_iterations: int,
    timeout: int = 600,  # 10 minutes
) -> Message:
    """
    Handles the iterative tool calling process with vLLM OpenAI-compatible API.

    Mutates the 'messages' list with tool calls and responses.

    Returns the next main message and the (inner) tool calling dialog.
    """

    tool_dialog = Dialog()

    @retry_on_transient_errors(max_attempts=32, base_backoff=0.5)
    @timeout_in_thread(seconds=timeout + 30)
    def generate(tools):
        """Helper to call chat completions with current state."""
        kwargs = {
            "model": get_vllm_model_path(),
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return client.chat.completions.create(**kwargs)

    for iteration in range(max_tool_iterations + 1):
        if iteration == max_tool_iterations:
            tools = None

        try:
            response = generate(tools)
        except Exception as e:
            raise RuntimeError("Failed to generate response after retries.") from e

        try:
            input_tokens: int = response.usage.prompt_tokens
            output_tokens: int = response.usage.completion_tokens
        except Exception:
            raise RuntimeError(
                f"Failed to retrieve token usage from response: {response}"
            )

        assert len(response.choices) == 1, response
        choice = response.choices[0]
        assistant_message = choice.message

        text = assistant_message.content or ""
        reasoning_content = assistant_message.reasoning_content or ""
        tool_calls = assistant_message.tool_calls

        logger.debug(
            f"[vLLM] Received text={bool(text)}, tool_calls={len(tool_calls) if tool_calls else 0}"
        )

        tool_dialog.append(
            Message.assistant(
                content=f"reasoning_content {reasoning_content}",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )

        tool_dialog.append(
            Message.assistant(
                content=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )

        if not tool_calls or iteration == max_tool_iterations:
            # Done if no more tool calls or max iterations reached
            total_input_tokens: int = sum(msg.input_tokens for msg in tool_dialog)
            total_output_tokens: int = sum(msg.output_tokens for msg in tool_dialog)
            return Message.assistant(
                text, tool_dialog, total_input_tokens, total_output_tokens
            )

        # Append the assistant message with tool_calls to the conversation
        messages.append(
            {
                "role": "assistant",
                "reasoning_content": reasoning_content,
            }
        )

        messages.append(
            {
                "role": "assistant",
                "tool_calls": tool_calls,
            }
        )

        # Execute ALL tool calls (OpenAI-compatible API can return multiple in parallel)
        for tool_call in tool_calls:
            tool_dialog.append(Message.assistant(f"function_call {tool_call.function}"))

            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            tool_result = MCP.call_tool(tool_name, tool_args)
            logger.info(f"Called MCP tool {tool_name} with arguments {tool_args}")

            # Each tool response must reference its tool_call_id
            tool_response = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(tool_result)
                if isinstance(tool_result, dict)
                else str(tool_result),
            }
            messages.append(tool_response)
            tool_dialog.append(Message.user(json.dumps(tool_response, indent=4)))

        remaining = max_tool_iterations - (iteration + 1)
        if remaining > 0:
            msg = TOOL_LOOP_MESSAGE.format(remaining=remaining)
        else:
            msg = TOOL_LOOP_END_MESSAGE
        messages.append({"role": "user", "content": msg})
        tool_dialog.append(Message.user(msg))

    raise RuntimeError("unreachable")


def tool_calling_loop_gemini(
    model_obj: genai.GenerativeModel,
    contents: list[dict],
    tools: list[types.Tool] | None,
    temperature: float,
    max_tool_iterations: int,
) -> Message:
    """
    Handles the iterative tool calling process with the Gemini model.

    Mutates the 'contents' list with tool calls and responses.

    Returns the next main message and the (inner) tool calling dialog.
    """

    tool_dialog = Dialog()

    @retry_on_resource_exhausted
    def generate(tools):
        """Helper to call generate_content with current state."""
        return model_obj.generate_content(
            contents,
            generation_config={"temperature": temperature},
            tools=tools if tools else None,
        )

    def part_type(part) -> str:
        return part._pb.WhichOneof("data")

    for iteration in range(max_tool_iterations + 1):
        if iteration == max_tool_iterations:
            tools = None

        response = generate(tools)
        input_tokens: int = response.usage_metadata.prompt_token_count
        output_tokens: int = response.usage_metadata.candidates_token_count
        assert len(response.candidates) == 1, response
        parts: list[types.Part] = response.candidates[0].content.parts
        assert parts, response
        logger.debug(f"Received {[part_type(p) for p in parts]}")

        text = "".join(p.text for p in parts if part_type(p) == "text")
        tool_dialog.append(
            Message.assistant(
                text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )

        function_calls = [
            p.function_call for p in parts if part_type(p) == "function_call"
        ]

        if not function_calls or iteration == max_tool_iterations:
            # done if no more tool calls or max iterations reached
            response_text = response.text if response.text else ""
            total_input_tokens: int = sum(msg.input_tokens for msg in tool_dialog)
            total_output_tokens: int = sum(msg.output_tokens for msg in tool_dialog)
            return Message.assistant(
                response_text, tool_dialog, total_input_tokens, total_output_tokens
            )

        # otherwise execute tools and prepare new input
        tool_dialog.append(Message.assistant(f"function_call {function_calls[0]}"))

        tool_name = function_calls[0].name
        tool_args = dict(function_calls[0].args)
        tool_result = MCP.call_tool(tool_name, tool_args)
        logger.info(f"Called MCP tool {tool_name} with arguments {tool_args}")
        contents.append({"role": "model", "parts": parts})
        tool_parts = [
            {
                "function_response": {
                    "name": tool_name,
                    "response": tool_result,
                }
            }
        ]
        contents.append(
            {
                "role": "user",
                "parts": tool_parts,
            }
        )
        tool_dialog.append(Message.user(json.dumps(tool_parts, indent=4)))
        remaining = max_tool_iterations - (iteration + 1)
        if remaining > 0:
            msg = TOOL_LOOP_MESSAGE.format(remaining=remaining)
        else:
            msg = TOOL_LOOP_END_MESSAGE
        contents.append({"role": "user", "parts": [{"text": msg}]})
        tool_dialog.append(Message.user(msg))

    raise RuntimeError("unreachable")
