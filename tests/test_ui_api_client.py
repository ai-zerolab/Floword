"""Tests for the Floword UI API client."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx_sse import ServerSentEvent

from floword.ui.api_client import FlowordAPIClient


class MockSSEGenerator:
    """Mock SSE generator for testing."""

    def __init__(self, events: list[dict[str, str]]):
        """Initialize the mock SSE generator.

        Args:
            events: List of events to yield.
        """
        self.events = events
        self.index = 0

    def __aiter__(self):
        """Return self as an async iterator."""
        return self

    async def __anext__(self):
        """Return the next event."""
        if self.index >= len(self.events):
            raise StopAsyncIteration
        event = self.events[self.index]
        self.index += 1
        return ServerSentEvent(
            event=event.get("event", ""),
            data=event.get("data", ""),
            id=event.get("id", ""),
            retry=event.get("retry", ""),
        )


class MockEventSource:
    """Mock event source for testing."""

    def __init__(self, events: list[dict[str, str]]):
        """Initialize the mock event source.

        Args:
            events: List of events to yield.
        """
        self.events = events

    def aiter_sse(self):
        """Return an async iterator for SSE events."""
        return MockSSEGenerator(self.events)

    async def __aenter__(self):
        """Enter the context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager."""
        pass


@pytest.fixture
def mock_httpx_client():
    """Mock the httpx client."""
    with patch("httpx.AsyncClient") as mock_client:
        yield mock_client


@pytest.mark.asyncio
async def test_create_conversation(mock_httpx_client):
    """Test creating a conversation."""
    # Setup
    mock_response = MagicMock()
    mock_response.json.return_value = {"conversation_id": "test-id"}
    mock_response.raise_for_status = MagicMock()

    mock_client_instance = AsyncMock()
    mock_client_instance.post.return_value = mock_response
    mock_httpx_client.return_value = mock_client_instance

    # Execute
    client = FlowordAPIClient("http://localhost:9772")
    conversation_id = await client.create_conversation()

    # Assert
    assert conversation_id == "test-id"
    mock_client_instance.post.assert_called_once_with("http://localhost:9772/api/v1/conversation/create")
    mock_response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_get_conversations(mock_httpx_client):
    """Test getting conversations."""
    # Setup
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "datas": [
            {
                "conversation_id": "test-id",
                "title": "Test Conversation",
                "created_at": "2025-03-07T08:00:00+00:00",
                "updated_at": "2025-03-07T08:00:00+00:00",
                "usage": {},
            }
        ],
        "limit": 100,
        "offset": 0,
        "has_more": False,
    }
    mock_response.raise_for_status = MagicMock()

    mock_client_instance = AsyncMock()
    mock_client_instance.get.return_value = mock_response
    mock_httpx_client.return_value = mock_client_instance

    # Execute
    client = FlowordAPIClient("http://localhost:9772")
    conversations = await client.get_conversations()

    # Assert
    assert conversations["datas"][0]["conversation_id"] == "test-id"
    mock_client_instance.get.assert_called_once_with(
        "http://localhost:9772/api/v1/conversation/list",
        params={"limit": 100, "offset": 0},
    )
    mock_response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_chat_stream(mock_httpx_client):
    """Test streaming chat responses."""
    # Setup
    mock_events = [
        {"data": json.dumps({"data": {"event_kind": "part_start", "part": {"content": "Hello", "part_kind": "text"}}})},
        {
            "data": json.dumps({
                "data": {"event_kind": "part_delta", "delta": {"content_delta": " world", "part_delta_kind": "text"}}
            })
        },
    ]

    # Create a mock client instance
    mock_client_instance = AsyncMock()
    mock_httpx_client.return_value = mock_client_instance

    # Mock the aconnect_sse function
    with patch("floword.ui.api_client.aconnect_sse") as mock_aconnect_sse:
        mock_event_source = MockEventSource(mock_events)
        mock_aconnect_sse.return_value = mock_event_source

        # Execute
        client = FlowordAPIClient("http://localhost:9772")
        events = []
        async for event in client.chat_stream("test-id", "Hello"):
            events.append(event)

        # Assert
        assert len(events) == 2
        assert events[0]["data"]["event_kind"] == "part_start"
        assert events[0]["data"]["part"]["content"] == "Hello"
        assert events[1]["data"]["event_kind"] == "part_delta"
        assert events[1]["data"]["delta"]["content_delta"] == " world"

        mock_aconnect_sse.assert_called_once_with(
            mock_client_instance,
            "POST",
            "http://localhost:9772/api/v1/conversation/chat/test-id",
            json={"prompt": "Hello"},
        )
