"""Test script for the Floword UI models."""

from floword.ui.models import (
    BackendConfig,
    BackendMode,
    ConversationState,
    ToolCall,
)


def test_backend_config():
    """Test the BackendConfig model."""
    # Test default values
    config = BackendConfig()
    assert config.mode == BackendMode.LOCAL
    assert config.port == 9772
    assert config.api_url == "http://localhost:9772"
    assert config.api_token is None
    assert config.env_vars == {}

    # Test custom values
    config = BackendConfig(
        mode=BackendMode.REMOTE,
        port=8000,
        api_url="http://example.com",
        api_token="test-token",
        env_vars={"FLOWORD_DEFAULT_MODEL_PROVIDER": "openai"},
    )
    assert config.mode == BackendMode.REMOTE
    assert config.port == 8000
    assert config.api_url == "http://example.com"
    assert config.api_token == "test-token"
    assert config.env_vars == {"FLOWORD_DEFAULT_MODEL_PROVIDER": "openai"}


def test_conversation_state():
    """Test the ConversationState model."""
    # Test default values
    state = ConversationState()
    assert state.conversation_id is None
    assert state.messages == []
    assert state.pending_tool_calls == []
    assert state.always_permit_tools is False

    # Test with values
    tool_call = ToolCall(
        tool_name="execute_command",
        args='{"command": "echo hello"}',
        tool_call_id="tool-123",
    )
    state = ConversationState(
        conversation_id="conv-123",
        messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
        pending_tool_calls=[tool_call],
        always_permit_tools=True,
    )
    assert state.conversation_id == "conv-123"
    assert len(state.messages) == 2
    assert state.messages[0]["role"] == "user"
    assert state.messages[0]["content"] == "Hello"
    assert state.messages[1]["role"] == "assistant"
    assert state.messages[1]["content"] == "Hi there!"
    assert len(state.pending_tool_calls) == 1
    assert state.pending_tool_calls[0].tool_name == "execute_command"
    assert state.pending_tool_calls[0].args == '{"command": "echo hello"}'
    assert state.pending_tool_calls[0].tool_call_id == "tool-123"
    assert state.always_permit_tools is True
