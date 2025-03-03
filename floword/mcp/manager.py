from __future__ import annotations

import json
from contextlib import asynccontextmanager
from functools import cache
from os import PathLike
from pathlib import Path

from fastapi import Depends
from pydantic import BaseModel, Field

from floword.config import Config, get_config
from floword.log import logger
from floword.mcp.clinet import MCPClient, ServerParams


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
    yield
    await mcp_manager.cleanup()
    logger.info("MCP manager disposed")


@cache
def _get_mcp_manager(config_path: PathLike):
    return MCPManager(config_path)


ServerName = str


class MCPConfig(BaseModel):
    mcp_servers: dict[ServerName, ServerParams] = Field({}, alias="mcpServers")


class MCPManager:
    clients: dict[ServerName, MCPClient]
    disabled_clients: list[ServerName]
    failed_clients: dict[ServerName, tuple[ServerParams, Exception]]
    initialized: bool

    def __init__(self, config_path: PathLike) -> None:
        logger.info(f"Loading MCP config from {config_path}")
        config_path = Path(config_path)

        mcp_configs = json.loads(config_path.read_text())
        self.disabled_clients = []
        for server_name, server_params in mcp_configs["mcpServers"].items():
            if not server_params.get("enabled", True):
                del mcp_configs["mcpServers"][server_name]
                self.disabled_clients.append(server_name)

        self.mcp_config = MCPConfig.model_validate(mcp_configs)
        self.clients = {
            server_name: MCPClient(server_params) for server_name, server_params in self.mcp_config.mcp_servers.items()
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
                server_name: client
                for server_name, client in self.clients.items()
                if server_name not in self.failed_clients
            }
        self.initialized = True

    async def cleanup(self) -> None:
        for client in self.clients.values():
            await client.cleanup()


if __name__ == "__main__":
    import asyncio

    async def main():
        await get_mcp_manager(Config(mcp_config_path=(Path.cwd() / "./mcp.json").as_posix()))

    asyncio.run(main())
