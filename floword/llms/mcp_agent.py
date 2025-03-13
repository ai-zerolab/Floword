import asyncio
import json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from mcp import Tool
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    SystemPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import (
    ModelRequestParameters,
    ModelResponse,
    ModelResponseStreamEvent,
    ModelSettings,
)
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import Usage

from floword.log import logger
from floword.mcp.manager import MCPManager

if TYPE_CHECKING:
    from pydantic_ai.models import Model


class ConversationError(TypeError):
    pass


class AlreadyResponsedError(ConversationError):
    pass


class NeedUserPromptError(ConversationError):
    pass


class InvalidResponseError(ConversationError):
    pass


class MCPAgent:
    def __init__(
        self,
        model: "Model",
        mcp_manager: MCPManager,
        *,
        system_prompt: str | None = None,
        last_conversation: list[ModelMessage] | None = None,
        usage: Usage | None = None,
    ):
        self.model = model
        self.mcp_manager = mcp_manager

        self._system_prompt = system_prompt
        self._last_conversation: list[ModelMessage] = last_conversation
        self._last_response: ModelResponse | None = None
        self._usage: Usage = usage or Usage()

    def _get_init_messages(self) -> list[ModelMessage]:
        return [ModelRequest(parts=[SystemPromptPart(content=self._system_prompt)])]

    def _get_tool_definitions(self, server_name: str, tools: list[Tool]) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=f"{server_name}-{tool.name}",
                description=tool.description or "",
                parameters_json_schema=tool.inputSchema,
            )
            for tool in tools
        ]

    def _dispatch_tool_definition_name(self, tool_definition_name: str) -> tuple[str, str]:
        server_name, tool_name = tool_definition_name.split("-")
        return server_name, tool_name

    def _map_tools(self) -> list[ToolDefinition]:
        r = []
        for server_name, tools in self.mcp_manager.get_tools().items():
            r.extend(self._get_tool_definitions(server_name, tools))
        return r

    async def _execute_one_tool_call_part(self, tool_call_part: ToolCallPart) -> ToolReturnPart:
        server_name, tool_name = self._dispatch_tool_definition_name(tool_call_part.tool_name)
        try:
            call_tool_result = await self.mcp_manager.call_tool(server_name, tool_name, tool_call_part.args)
        except Exception as e:
            logger.exception(e)
            return ToolReturnPart(
                tool_name=tool_call_part.tool_name,
                content={"error": str(e)},
                tool_call_id=tool_call_part.tool_call_id,
            )
        else:
            return ToolReturnPart(
                tool_name=tool_call_part.tool_name,
                content=call_tool_result.model_dump(),
                tool_call_id=tool_call_part.tool_call_id,
            )

    async def _execute_all_tool_calls(self, message: ModelMessage) -> list[ToolReturnPart]:
        if not isinstance(message, ModelResponse):
            return []

        return await asyncio.gather(
            *(
                self._execute_one_tool_call_part(tool_call_part)
                for tool_call_part in message.parts
                if isinstance(tool_call_part, ToolCallPart)
            )
        )

    async def _execute_tool_calls(
        self,
        message: ModelMessage,
        execute_tool_call_ids: list[str] | None,
        execute_tool_call_part: list[ToolCallPart] | None,
    ) -> list[ToolReturnPart]:
        if not isinstance(message, ModelResponse):
            return []

        selected_tool_call_parts = execute_tool_call_part or []
        if execute_tool_call_ids:
            selected_tool_call_parts = [
                *selected_tool_call_parts,
                *[
                    tool_call_part
                    for tool_call_part in message.parts
                    if isinstance(tool_call_part, ToolCallPart) and tool_call_part.tool_call_id in execute_tool_call_ids
                ],
            ]

        return await asyncio.gather(
            *(self._execute_one_tool_call_part(tool_call_part) for tool_call_part in selected_tool_call_parts)
        )

    async def retry_stream(
        self, model_settings: ModelSettings | None = None
    ) -> AsyncIterator[ModelResponseStreamEvent | ModelRequest]:
        if self._last_conversation and isinstance(self._last_conversation[-1], ModelResponse):
            raise AlreadyResponsedError("Already responded.")

        messages = self._last_conversation or self._get_init_messages()
        yield messages[-1]
        async for m in self._request_stream(
            messages,
            model_settings,
        ):
            yield m

    async def chat_stream(
        self,
        prompt: str,
        model_settings: ModelSettings | None = None,
    ) -> AsyncIterator[ModelResponseStreamEvent | ModelRequest]:
        logger.info(f"Starting conversation with prompt: {prompt}")
        if self._last_conversation and not isinstance(self._last_conversation[-1], ModelResponse):
            raise NeedUserPromptError("Please resume the conversation.")

        previous_conversation = self._last_conversation or self._get_init_messages()
        messages = [
            *previous_conversation,
            ModelRequest(parts=[UserPromptPart(content=prompt)]),
        ]
        yield messages[-1]

        async for m in self._request_stream(
            messages,
            model_settings,
        ):
            yield m

    async def run_tool_stream(
        self,
        model_settings: ModelSettings | None = None,
        *,
        execute_all_tool_calls: bool = False,
        execute_tool_call_ids: list[str] | None = None,
        execute_tool_call_part: list[ToolCallPart] | None = None,
    ) -> AsyncIterator[ModelResponseStreamEvent | ModelRequest]:
        logger.info(f"Handling tool call: {execute_all_tool_calls}, {execute_tool_call_ids}, {execute_tool_call_part}")
        messages = self._last_conversation or self._get_init_messages()
        if execute_all_tool_calls:
            tool_return_parts = await self._execute_all_tool_calls(messages[-1])
        else:
            tool_return_parts = await self._execute_tool_calls(
                messages[-1], execute_tool_call_ids, execute_tool_call_part
            )
        if tool_return_parts:
            messages = [*messages, ModelRequest(parts=tool_return_parts)]
            yield messages[-1]

        async for m in self._request_stream(
            messages,
            model_settings,
        ):
            yield m

    async def _request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
    ) -> AsyncIterator[ModelResponseStreamEvent]:
        if not isinstance(messages[-1], ModelRequest):
            raise NeedUserPromptError("Please resume the conversation.")

        model_request_parameters = ModelRequestParameters(
            function_tools=self._map_tools(),
            allow_text_result=True,
            result_tools=[],
        )
        async with self.model.request_stream(messages, model_settings, model_request_parameters) as response:
            async for message in response:
                if not message:
                    continue
                yield message
            self._last_response = response.get()
            self._validate_response(self._last_response)
            self._last_conversation = [*messages, self._last_response]
            self._usage.incr(response.usage(), requests=1)

    def _validate_response(self, response: ModelResponse):
        if not isinstance(response, ModelResponse):
            raise InvalidResponseError(f"Invalid response: {response}")

        if not response.parts:
            return

        for part in response.parts:
            if isinstance(part, ToolCallPart) and isinstance(part.args, str):
                try:
                    json.loads(part.args)
                except json.JSONDecodeError as e:
                    raise InvalidResponseError(f"Invalid response: {response}") from e

    def all_messages(self) -> list[ModelMessage]:
        if self._last_conversation is None:
            # No request has been made yet
            return []
        return self._last_conversation

    def last_response(self) -> ModelResponse | None:
        return self._last_response

    def usage(self) -> Usage:
        return self._usage
