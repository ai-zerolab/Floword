import asyncio
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

from floword.mcp.manager import MCPManager

if TYPE_CHECKING:
    from pydantic_ai.models import Model


class AlreadyResponsedError(TypeError):
    pass


class NeedUserPromptError(TypeError):
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
        return [
            tool_def
            for server_name, tools in self.mcp_manager.get_tools().items()
            for tool_def in self._get_tool_definitions(server_name, tools)
        ]

    async def _execute_one_tool_call_part(self, tool_call_part: ToolCallPart) -> ToolReturnPart:
        server_name, tool_name = self._dispatch_tool_definition_name(tool_call_part.tool_name)
        call_tool_result = await self.mcp_manager.call_tool(server_name, tool_name, tool_call_part.args)
        return ToolReturnPart(
            tool_name=tool_call_part.tool_name,
            content=call_tool_result,
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

    async def resume_stream(
        self, model_settings: ModelSettings | None = None
    ) -> AsyncIterator[ModelResponseStreamEvent]:
        if not self._last_conversation or isinstance(self._last_conversation[-1], ModelResponse):
            raise AlreadyResponsedError("Already responded.")

        return await self._request_stream(
            self._last_conversation,
            model_settings,
        )

    async def chat_stream(
        self,
        prompt: str,
        model_settings: ModelSettings | None = None,
    ) -> AsyncIterator[ModelResponseStreamEvent]:
        previous_conversation = self._last_conversation or self._get_init_messages()
        if isinstance(previous_conversation[-1], ModelResponse):
            raise NeedUserPromptError("Please resume the conversation.")

        messages = [
            *previous_conversation,
            ModelRequest(parts=[UserPromptPart(content=prompt)]),
        ]

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
    ) -> AsyncIterator[ModelResponseStreamEvent]:
        async for m in self._request_stream(
            self._last_conversation or self._get_init_messages(),
            model_settings,
            execute_all_tool_calls=execute_all_tool_calls,
            execute_tool_call_ids=execute_tool_call_ids,
            execute_tool_call_part=execute_tool_call_part,
        ):
            yield m

    async def _request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        *,
        execute_all_tool_calls: bool = False,
        execute_tool_call_ids: list[str] | None = None,
        execute_tool_call_part: list[ToolCallPart] | None = None,
    ) -> AsyncIterator[ModelResponseStreamEvent]:
        if execute_all_tool_calls:
            tool_return_parts = await self._execute_all_tool_calls(messages[-1])
        else:
            tool_return_parts = await self._execute_tool_calls(
                messages[-1], execute_tool_call_ids, execute_tool_call_part
            )
        if tool_return_parts:
            messages = [*messages, ModelRequest(parts=tool_return_parts)]
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
            self._last_conversation = [*messages, self._last_response]
            self._usage.incr(response.usage(), requests=1)

    def all_messages(self) -> list[ModelMessage]:
        if self._last_conversation is None:
            # No request has been made yet
            return []
        return self._last_conversation

    def last_response(self) -> ModelResponse | None:
        return self._last_response

    def usage(self) -> Usage:
        return self._usage
