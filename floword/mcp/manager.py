from __future__ import annotations

import json
from contextlib import asynccontextmanager
from functools import cache
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Depends
from mcp import Tool
from pydantic import BaseModel, Field

from floword.config import Config, get_config
from floword.log import logger
from floword.mcp.clinet import MCPClient, ServerParams

if TYPE_CHECKING:
    from mcp.types import CallToolResult

_HERE = Path(__file__).parent
DEFAULT_MCP_CONFIG_PATH = _HERE / "mcp.json"


def escape(server_name: str) -> str:
    # Convert server name to follow this pattern: [a-zA-Z0-9_]+
    # Convert all invalid char to ascii code with prefix `_`
    return "".join([f"_{ord(c):x}" if not c.isalnum() else c for c in server_name])


async def get_mcp_manager(config: Config = Depends(get_config)):
    mcp_manager = _get_mcp_manager(config.mcp_config_path)
    if not mcp_manager.initialized:
        # For direct use
        await mcp_manager.initialize()

    return mcp_manager


@asynccontextmanager
async def init_mcp_manager(config: Config):
    mcp_manager = _get_mcp_manager(config.mcp_config_path)
    await mcp_manager.initialize()
    logger.info("MCP manager initialized")
    yield mcp_manager
    await mcp_manager.cleanup()
    logger.info("MCP manager disposed")


def _get_mcp_manager(config_path: PathLike) -> MCPManager:
    return _init_mcp_manager_singleton(Path(config_path).expanduser().resolve().absolute().as_posix())


@cache
def _init_mcp_manager_singleton(config_path: str) -> MCPManager:
    return MCPManager(config_path)


ServerName = str


class MCPConfig(BaseModel):
    mcp_servers: dict[ServerName, ServerParams] = Field({}, alias="mcpServers")


class MCPManager:
    clients: dict[ServerName, MCPClient]
    disabled_clients: list[ServerName]
    failed_clients: dict[ServerName, tuple[ServerParams, Exception]]
    initialized: bool
    tools: dict[ServerName, list[Tool]]

    def __init__(self, config_path: PathLike) -> None:
        logger.info(f"Loading MCP config from {config_path}")
        config_path = Path(config_path)
        if not config_path.exists() or not config_path.is_file():
            logger.warning(
                f"Does not exist or is not a file {config_path}. Using default MCP config path: {DEFAULT_MCP_CONFIG_PATH}"
            )
            config_path = DEFAULT_MCP_CONFIG_PATH

        mcp_configs = json.loads(config_path.read_text())
        self.disabled_clients = [
            server_name
            for server_name, server_params in mcp_configs["mcpServers"].items()
            if not server_params.get("enabled", True)
        ]

        self.mcp_config = MCPConfig.model_validate(mcp_configs)
        self.clients = {
            escape(server_name): MCPClient(server_name, server_params)
            for server_name, server_params in self.mcp_config.mcp_servers.items()
            if server_name not in self.disabled_clients
        }
        self.failed_clients = {}
        self.initialized = False

    async def initialize(self):
        for server_name, client in self.clients.items():
            try:
                await client.initialize()
            except Exception as e:
                logger.exception(f"Error connecting to {server_name}: {e}")
                self.failed_clients[server_name] = (client.server_params, e)

        if self.failed_clients:
            logger.error(f"{len(self.failed_clients)} MCP clients failed to connect")
            self.clients = {
                escape(server_name): client
                for server_name, client in self.clients.items()
                if server_name not in self.failed_clients
            }
        self.tools = await self._list_tools()
        self.initialized = True

    async def cleanup(self) -> None:
        for client in self.clients.values():
            await client.cleanup()

    async def _list_tools(self) -> dict[ServerName, list[Tool]]:
        return {server_name: await client.get_tools() for server_name, client in self.clients.items()}

    async def call_tool(self, server_name: ServerName, tool_name: str, args: str | dict) -> CallToolResult:
        if isinstance(args, str):
            args = json.loads(args)

        logger.info(f"Calling tool {tool_name} on {server_name}")
        return await self.clients[server_name].call_tool(tool_name, args)

    def get_tools(self) -> dict[ServerName, list[Tool]]:
        return self.tools
