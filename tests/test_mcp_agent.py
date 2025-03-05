from functools import partial
from pathlib import Path

import pytest
from inline_snapshot import snapshot
from pydantic_ai.models.test import TestModel

from floword.llms.mcp_agent import MCPAgent
from floword.mcp.manager import MCPManager


@pytest.fixture
async def agent_builder(temp_mcp_config: Path):
    """Test MCPManager initialization."""
    mcp_manager = MCPManager(temp_mcp_config)

    await mcp_manager.initialize()

    caller = partial(
        MCPAgent,
        model=None,
        mcp_manager=mcp_manager,
        system_prompt="You are a helpful assistent",
    )

    yield caller


async def test_mcp_agent_plain_response(agent_builder):
    agent: MCPAgent = agent_builder(model=TestModel())

    tool_call_parts = [message async for message in agent.chat_stream("I know you will call tools")]
    assert len(tool_call_parts) == snapshot(5)

    tool_response_parts = [message async for message in agent.run_tool_stream(execute_all_tool_calls=True)]
    assert len(tool_response_parts) == snapshot(24)
