import os
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, TypeVar

from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from pydantic import BaseModel

if TYPE_CHECKING:
    from mcp.types import CallToolResult


class SSEServerParameters(BaseModel):
    url: str
    headers: dict | None = None
    timeout: float = 5
    sse_read_timeout: float = 60 * 5


ServerParams = TypeVar("ServerParams", StdioServerParameters, SSEServerParameters)


class MCPClient:
    server_name: str
    server_params: ServerParams

    def __init__(self, server_name: str, server_params: ServerParams):
        # Initialize session and client objects
        self.server_name = server_name
        self.session: ClientSession | None = None
        self.exit_stack = AsyncExitStack()

        self.server_params: StdioServerParameters | SSEServerParameters = server_params

    async def initialize(self) -> None:
        """Connect to an MCP server"""

        if isinstance(self.server_params, StdioServerParameters):
            server_params = self.server_params.model_copy(
                update={"env": {**os.environ, **(self.server_params.env or {})}}
            )

            transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        elif isinstance(self.server_params, SSEServerParameters):
            transport = await self.exit_stack.enter_async_context(
                self.exit_stack.enter_async_context(sse_client(**self.server_params.model_dump())),
            )
        else:
            raise TypeError(f"Unsupported server parameters type: {type(self.server_params)}")
        self.stdio, self.write = transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

    async def get_tools(self) -> list[Tool]:
        response = await self.session.list_tools()
        return response.tools

    async def call_tool(self, tool_name: str, args: dict | None = None) -> "CallToolResult":
        return await self.session.call_tool(tool_name, args)

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()
