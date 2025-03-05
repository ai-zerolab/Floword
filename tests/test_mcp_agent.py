from functools import partial
from pathlib import Path

import pytest
from inline_snapshot import snapshot
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
)
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
    assert tool_call_parts == snapshot([
        PartStartEvent(
            index=0,
            part=ToolCallPart(tool_name="mock-echo_text", args={"text": "a"}),
        ),
        PartStartEvent(
            index=1,
            part=ToolCallPart(tool_name="mock-get_user_info", args={"user_id": 0}),
        ),
        PartStartEvent(index=2, part=ToolCallPart(tool_name="mock-raise_error", args={})),
        PartStartEvent(
            index=3,
            part=ToolCallPart(tool_name="mock-complex_operation", args={"data": {}}),
        ),
    ])

    tool_response_parts = [message async for message in agent.run_tool_stream(execute_all_tool_calls=True)]
    assert tool_response_parts == snapshot([
        PartStartEvent(index=0, part=TextPart(content="")),
        PartDeltaEvent(
            index=0,
            delta=TextPartDelta(
                content_delta='{"mock-echo_text":{"meta":null,"content":[{"type":"text","text":"a","annotations":null}],"isError":false},"mock-get_user_info":{"meta":null,"content":[{"type":"text","text":"{\\"id\\": '
            ),
        ),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="0, ")),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='\\"name\\": ')),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='\\"User ')),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='0\\", ')),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='\\"email\\": ')),
        PartDeltaEvent(
            index=0,
            delta=TextPartDelta(
                content_delta='\\"user0@example.com\\"}","annotations":null}],"isError":false},"mock-raise_error":{"meta":null,"content":[{"type":"text","text":"Error '
            ),
        ),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="executing ")),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="tool ")),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="raise_error: ")),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="An ")),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="error ")),
        PartDeltaEvent(
            index=0,
            delta=TextPartDelta(
                content_delta='occurred","annotations":null}],"isError":true},"mock-complex_operation":{"meta":null,"content":[{"type":"text","text":"{\\"processed\\": '
            ),
        ),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="true, ")),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='\\"input_data\\": ')),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="{}, ")),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='\\"options_used\\": ')),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='[\\"default\\"], ')),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='\\"verbose_mode\\": ')),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="false, ")),
        PartDeltaEvent(index=0, delta=TextPartDelta(content_delta='\\"result\\": ')),
        PartDeltaEvent(
            index=0,
            delta=TextPartDelta(content_delta='\\"Success\\"}","annotations":null}],"isError":false}}'),
        ),
    ])
