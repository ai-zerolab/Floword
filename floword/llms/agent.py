from collections.abc import AsyncIterator, Iterable
from typing import Any

from mcp import Tool
from pydantic_ai.messages import ModelMessage, ToolCallPart, ToolReturnPart
from pydantic_ai.models import (
    ModelRequestParameters,
    ModelResponse,
    ModelResponseStreamEvent,
    ModelSettings,
)
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import Usage

from floword.llms.models import init_model
from floword.mcp.manager import MCPManager


class Agent:
    def __init__(
        self,
        provider: str,
        model_name: str,
        mcp_manager: MCPManager,
        usage: Usage | None = None,
        *model_args: Iterable[Any],
        **model_kwargs: dict[str, Any],
    ):
        self.model = init_model(provider, model_name, *model_args, **model_kwargs)
        self.mcp_manager = mcp_manager

        self._last_conversation: list[ModelMessage] | None = None
        self._last_response: ModelResponse | None = None
        self._usage: Usage = usage or Usage()

    def get_tool_definitions(self, server_name: str, tools: list[Tool]) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=f"{server_name}-{tool.name}",
                description=tool.description or "",
                parameters_json_schema=tool.inputSchema,
            )
            for tool in tools
        ]

    def dispatch_tool_definition_name(self, tool_definition_name: str) -> tuple[str, str]:
        server_name, tool_name = tool_definition_name.split("-")
        return server_name, tool_name

    def map_tools(self) -> list[ToolDefinition]:
        return [
            tool_def
            for server_name, tools in self.mcp_manager.tools.items()
            for tool_def in self.get_tool_definitions(server_name, tools)
        ]

    async def _execute_one_tool_call_part(self, tool_call_part: ToolCallPart) -> ToolReturnPart:
        server_name, tool_name = self.dispatch_tool_definition_name(tool_call_part.tool_name)
        call_tool_result = await self.mcp_manager.call_tool(server_name, tool_name, tool_call_part.args)
        return ToolReturnPart(
            tool_name=tool_call_part.tool_name,
            content=call_tool_result,
            tool_call_id=tool_call_part.tool_call_id,
        )

    async def execute_all_tool_calls(self, message: ModelMessage) -> list[ToolReturnPart]:
        if not isinstance(message, ModelResponse):
            return []

        return await asyncio.gather(
            *(self._execute_one_tool_call_part(tool_call_part) for tool_call_part in message.tool_call_parts)
        )

    async def execute_tool_calls(
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

    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        *,
        execute_all_tool_calls: bool = False,
        execute_tool_call_ids: list[str] | None = None,
        execute_tool_call_part: list[ToolCallPart] | None = None,
    ) -> AsyncIterator[ModelResponseStreamEvent]:
        if execute_all_tool_calls:
            tool_return_parts = await self.execute_all_tool_calls(messages[-1])
        else:
            tool_return_parts = await self.execute_tool_calls(
                messages[-1], execute_tool_call_ids, execute_tool_call_part
            )

        self._last_conversation = [*messages, ModelRequest(parts=tool_return_parts)]
        model_request_parameters = ModelRequestParameters(
            function_tools=self.map_tools(),
            allow_text_result=True,
            result_tools=[],
        )

        async with self.model.request_stream(
            self._last_conversation, model_settings, model_request_parameters
        ) as response:
            async for message in response:
                if not message:
                    continue
                yield message
            self._last_response = response.get()
            self._usage.incr(response.usage(), requests=1)

    def all_messages(self) -> list[ModelMessage]:
        if self._last_conversation is None:
            # No request has been made yet
            return []
        return [*self._last_conversation, self._last_response]

    def last_response(self) -> ModelResponse | None:
        return self._last_response

    def usage(self) -> Usage:
        return self._usage


if __name__ == "__main__":
    import asyncio
    from pathlib import Path

    from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

    from floword.config import Config
    from floword.log import logger
    from floword.mcp.manager import init_mcp_manager

    async def main():
        config = Config(mcp_config_path=(Path.cwd() / "./mcp.json").as_posix())
        async with init_mcp_manager(config) as mcp_manager:
            # Just a placeholder to show it's working
            logger.info(f"MCP manager initialized with {len(mcp_manager.clients)} clients")

            agent = Agent(
                provider="bedrock",
                model_name="anthropic.claude-3-5-sonnet-20241022-v2:0",
                mcp_manager=mcp_manager,
            )

            async for message in agent.request_stream(
                messages=[
                    ModelRequest(
                        parts=[
                            SystemPromptPart(content="You are a helpful assistent"),
                            UserPromptPart(content="Use tool to list all files in /opt"),
                        ]
                    )
                ],
                model_settings=None,
            ):
                print(message)

            last_response = agent.last_response()
            all_messages = agent.all_messages()
            print(agent.usage())
            logger.info(f"Last response: {last_response}")
            async for message in agent.request_stream(
                messages=all_messages,
                model_settings=None,
                execute_tool_call_ids=[p.tool_call_id for p in last_response.parts if isinstance(p, ToolCallPart)],
                execute_tool_call_part=[],
            ):
                print(message)
            print(agent.usage())

    asyncio.run(main())
