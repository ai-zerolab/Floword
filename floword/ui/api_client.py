"""API client for the Floword UI."""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from httpx_sse import ServerSentEvent, aconnect_sse

from floword.ui.models import ConversationState
from pydantic_ai.models import ModelSettings

# Set up logging
logger = logging.getLogger(__name__)


class FlowordAPIClient:
    """API client for the Floword backend."""

    def __init__(self, base_url: str, api_token: Optional[str] = None):
        """Initialize the API client.

        Args:
            base_url: The base URL of the API.
            api_token: Optional API token for authentication.
        """
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}
        self.client = httpx.AsyncClient(headers=self.headers)
        logger.info(f"Initialized API client with base URL: {base_url}")

    async def test_connection(self) -> str:
        """Test the connection to the backend.

        Returns:
            A status message.
        """
        url = f"{self.base_url}"
        logger.info(f"Making GET request to: {url}")
        response = await self.client.get(url)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Test connection successful!")
        return data

    async def create_conversation(self) -> str:
        """Create a new conversation and return its ID.

        Returns:
            The conversation ID.
        """
        url = f"{self.base_url}/api/v1/conversation/create"
        logger.info(f"Making POST request to: {url}")
        response = await self.client.post(url)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Created conversation with ID: {data['conversation_id']}")
        return data["conversation_id"]

    async def get_conversations(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get a list of conversations.

        Args:
            limit: The maximum number of conversations to return.
            offset: The offset to start from.

        Returns:
            A dictionary containing the conversations.
        """
        url = f"{self.base_url}/api/v1/conversation/list"
        logger.info(f"Making GET request to: {url} with params: limit={limit}, offset={offset}")
        response = await self.client.get(
            url,
            params={"limit": limit, "offset": offset},
        )
        response.raise_for_status()
        data = response.json()
        logger.info(f"Retrieved {len(data.get('datas', []))} conversations")
        return data

    async def get_conversation_info(self, conversation_id: str) -> Dict[str, Any]:
        """Get information about a conversation.

        Args:
            conversation_id: The ID of the conversation.

        Returns:
            A dictionary containing the conversation information.
        """
        url = f"{self.base_url}/api/v1/conversation/info/{conversation_id}"
        logger.info(f"Making GET request to: {url}")
        response = await self.client.get(url)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Retrieved info for conversation: {conversation_id}")
        return data

    async def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation.

        Args:
            conversation_id: The ID of the conversation.
        """
        url = f"{self.base_url}/api/v1/conversation/delete/{conversation_id}"
        logger.info(f"Making POST request to: {url}")
        response = await self.client.post(url)
        response.raise_for_status()
        logger.info(f"Deleted conversation: {conversation_id}")

    async def chat_stream(
        self, conversation_id: str, prompt: str, model_settings: Optional[ModelSettings] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream chat responses from the API.

        Args:
            conversation_id: The ID of the conversation.
            prompt: The prompt to send.
            model_settings: Optional model settings.

        Yields:
            SSE events from the API.
        """
        url = f"{self.base_url}/api/v1/conversation/chat/{conversation_id}"
        payload = {"prompt": prompt}
        if model_settings:
            payload["llm_model_settings"] = model_settings

        logger.info(f"Making POST request to: {url} with prompt: {prompt[:50]}...")
        async with aconnect_sse(self.client, "POST", url, json=payload) as event_source:
            logger.info(f"Connected to SSE stream for conversation: {conversation_id}")
            async for sse in event_source.aiter_sse():
                if sse.data:
                    yield json.loads(sse.data)

    async def permit_tool_call(
        self,
        conversation_id: str,
        execute_all: bool = False,
        tool_call_ids: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Permit tool calls.

        Args:
            conversation_id: The ID of the conversation.
            execute_all: Whether to execute all tool calls.
            tool_call_ids: Optional list of tool call IDs to execute.

        Yields:
            SSE events from the API.
        """
        url = f"{self.base_url}/api/v1/conversation/permit-call-tool/{conversation_id}"
        payload = {"execute_all_tool_calls": execute_all}
        if tool_call_ids:
            payload["execute_tool_call_ids"] = tool_call_ids

        logger.info(f"Making POST request to: {url}")
        logger.info(f"Execute all: {execute_all}, Tool call IDs: {tool_call_ids}")

        async with aconnect_sse(self.client, "POST", url, json=payload) as event_source:
            logger.info(f"Connected to SSE stream for tool call permission: {conversation_id}")
            async for sse in event_source.aiter_sse():
                if sse.data:
                    yield json.loads(sse.data)

    async def retry_conversation(
        self, conversation_id: str, model_settings: Optional[ModelSettings] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Retry a conversation.

        Args:
            conversation_id: The ID of the conversation.
            model_settings: Optional model settings.

        Yields:
            SSE events from the API.
        """
        url = f"{self.base_url}/api/v1/conversation/retry/{conversation_id}"
        payload = {}
        if model_settings:
            payload["llm_model_settings"] = model_settings

        logger.info(f"Making POST request to: {url}")
        async with aconnect_sse(self.client, "POST", url, json=payload) as event_source:
            logger.info(f"Connected to SSE stream for retry: {conversation_id}")
            async for sse in event_source.aiter_sse():
                if sse.data:
                    yield json.loads(sse.data)

    async def close(self) -> None:
        """Close the client."""
        logger.info("Closing API client")
        await self.client.aclose()
