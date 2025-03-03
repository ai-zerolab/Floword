from contextlib import AsyncExitStack
from typing import Optional, TypeVar

from mcp import ClientSession, StdioServerParameters, Tool
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from pydantic import BaseModel


class SSEServerParameters(BaseModel):
    url: str
    headers: dict | None = None
    timeout: float = 5
    sse_read_timeout: float = 60 * 5


ServerParams = TypeVar("ServerParams", StdioServerParameters, SSEServerParameters)


class MCPClient:
    server_params: ServerParams

    def __init__(self, server_params: ServerParams):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()

        self.server_params: StdioServerParameters | SSEServerParameters = server_params

    async def initialize(self) -> None:
        """Connect to an MCP server"""

        if isinstance(self.server_params, StdioServerParameters):
            transport = await self.exit_stack.enter_async_context(stdio_client(self.server_params))
        elif isinstance(self.server_params, SSEServerParameters):
            transport = await self.exit_stack.enter_async_context(
                self.exit_stack.enter_async_context(sse_client(self.server_params)),
            )
        else:
            raise TypeError(f"Unsupported server parameters type: {type(self.server_params)}")
        transport = await self.exit_stack.enter_async_context(stdio_client(self.server_params))
        self.stdio, self.write = transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

    async def get_tools(self) -> list[Tool]:
        response = await self.session.list_tools()
        return response.tools

    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        messages = [{"role": "user", "content": query}]

        response = await self.session.list_tools()
        available_tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
            }
            for tool in response.tools
        ]

        # Initial Claude API call
        response = self.anthropic.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1000,
            messages=messages,
            tools=available_tools,
        )

        # Process response and handle tool calls
        tool_results = []
        final_text = []

        for content in response.content:
            if content.type == "text":
                final_text.append(content.text)
            elif content.type == "tool_use":
                tool_name = content.name
                tool_args = content.input

                # Execute tool call
                result = await self.session.call_tool(tool_name, tool_args)
                tool_results.append({"call": tool_name, "result": result})
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                # Continue conversation with tool results
                if hasattr(content, "text") and content.text:
                    messages.append({"role": "assistant", "content": content.text})
                messages.append({"role": "user", "content": result.content})

                # Get next response from Claude
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=messages,
                )

                final_text.append(response.content[0].text)

        return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == "quit":
                    break

                response = await self.process_query(query)
                print("\n" + response)

            except Exception as e:
                print(f"\nError: {e!s}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()
