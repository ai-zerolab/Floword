from pathlib import Path

import pytest
from mcp import Tool
from pydantic_ai.models.function import FunctionModel

from floword.config import Config
from floword.mcp.clinet import MCPClient, StdioServerParameters
from floword.mcp.manager import MCPManager, escape, init_mcp_manager


@pytest.fixture
def invalid_mcp_config(tmp_path: Path) -> Path:
    """Create an invalid MCP config file."""
    config_path = tmp_path / "invalid_mcp.json"
    config_path.write_text("invalid json")
    return config_path


@FunctionModel
def test_escape():
    """Test the escape function."""
    assert escape("test") == "test"
    assert escape("test-server") == "test_2dserver"
    assert escape("test.server") == "test_2eserver"
    assert escape("test@server") == "test_40server"

    return {"success": True}


@FunctionModel
def test_mcp_manager_init(temp_mcp_config: Path):
    """Test MCPManager initialization."""
    manager = MCPManager(temp_mcp_config)

    # Check that the manager was initialized correctly
    assert not manager.initialized
    assert "mock" in manager.clients
    assert "disabled-mock" in manager.disabled_clients
    assert len(manager.failed_clients) == 0

    return {"success": True}


@FunctionModel
def test_mcp_manager_init_invalid_path():
    """Test MCPManager initialization with invalid path."""
    with pytest.raises(ValueError, match="Invalid MCP config path"):
        MCPManager(Path("/nonexistent/path"))

    return {"success": True}


@FunctionModel
def test_mcp_manager_init_invalid_json(invalid_mcp_config: Path):
    """Test MCPManager initialization with invalid JSON."""
    with pytest.raises(Exception):
        MCPManager(invalid_mcp_config)

    return {"success": True}


async def test_mcp_manager_get_tools(temp_mcp_config):
    """Test the get_tools method."""
    # Create a mock MCPManager with predefined tools
    manager = MCPManager(temp_mcp_config)

    # Mock the tools dictionary
    tool1 = Tool(name="tool1", description="Tool 1", inputSchema={})
    tool2 = Tool(name="tool2", description="Tool 2", inputSchema={})
    manager.tools = {"server1": [tool1], "server2": [tool2]}
    manager.initialized = True

    # Test get_tools
    tools = manager.get_tools()
    assert len(tools) == 2
    assert "server1" in tools
    assert "server2" in tools
    assert tools["server1"] == [tool1]
    assert tools["server2"] == [tool2]


async def test_init_mcp_manager_context_manager(temp_mcp_config):
    """Test the init_mcp_manager context manager."""
    config = Config(mcp_config_path=temp_mcp_config.as_posix())

    # Mock the initialize and cleanup methods
    original_initialize = MCPManager.initialize
    original_cleanup = MCPManager.cleanup

    initialize_called = False
    cleanup_called = False

    async def mock_initialize(self):
        nonlocal initialize_called
        initialize_called = True
        self.initialized = True
        self.tools = {}

    async def mock_cleanup(self):
        nonlocal cleanup_called
        cleanup_called = True

    MCPManager.initialize = mock_initialize
    MCPManager.cleanup = mock_cleanup

    try:
        async with init_mcp_manager(config) as manager:
            assert initialize_called
            assert not cleanup_called
            assert manager.initialized

        assert cleanup_called
    finally:
        # Restore original methods
        MCPManager.initialize = original_initialize
        MCPManager.cleanup = original_cleanup


class TestMCPManagerWithMocks:
    """Tests for MCPManager using mocks."""

    @pytest.fixture
    def mock_manager(self, temp_mcp_config):
        """Create a mock MCPManager."""
        manager = MCPManager(temp_mcp_config)
        manager.initialized = True

        # Create mock clients
        client1 = MCPClient("server1", StdioServerParameters(command="echo", args=["mock"]))
        client2 = MCPClient("server2", StdioServerParameters(command="echo", args=["mock"]))

        manager.clients = {"server1": client1, "server2": client2}

        return manager

    async def test_call_tool_with_string_args(self, monkeypatch, mock_manager):
        """Test calling a tool with string arguments."""

        async def mock_call_tool(self, tool_name, args):
            assert tool_name == "test_tool"
            assert args == {"arg1": "value1"}
            return "tool result"

        # Apply the monkeypatch
        monkeypatch.setattr(MCPClient, "call_tool", mock_call_tool)

        # Call the tool
        result = await mock_manager.call_tool("server1", "test_tool", '{"arg1": "value1"}')
        assert result == "tool result"

    async def test_call_tool_with_dict_args(self, monkeypatch, mock_manager):
        """Test calling a tool with dict arguments."""

        async def mock_call_tool(self, tool_name, args):
            assert tool_name == "test_tool"
            assert args == {"arg1": "value1"}
            return "tool result"

        # Apply the monkeypatch
        monkeypatch.setattr(MCPClient, "call_tool", mock_call_tool)

        # Call the tool
        result = await mock_manager.call_tool("server1", "test_tool", {"arg1": "value1"})
        assert result == "tool result"
