"""API client for the Floword UI."""

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union

import httpx
from httpx_sse import ServerSentEvent, aconnect_sse

from floword.ui.models.conversation import ConversationState, Message, MessageRole, ToolCall
from pydantic_ai.models import ModelSettings
from floword.log import logger


class APIError(Exception):
    """API error exception."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        """Initialize the API error.

        Args:
            message: The error message.
            status_code: Optional HTTP status code.
            response_text: Optional response text.
        """
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(message)


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
        self.client = httpx.AsyncClient(headers=self.headers, timeout=30.0)
        logger.info(f"Initialized API client with base URL: {base_url}")

    async def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Handle an API response.

        Args:
            response: The response to handle.

        Returns:
            The parsed response data.

        Raises:
            APIError: If the response indicates an error.
        """
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            try:
                error_data = response.json()
                error_message = error_data.get("detail", str(e))
            except json.JSONDecodeError:
                error_message = response.text or str(e)

            logger.error(f"API error: {error_message} (status code: {response.status_code})")
            raise APIError(
                message=f"API error: {error_message}",
                status_code=response.status_code,
                response_text=response.text,
            ) from e
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse response as JSON: {response.text}")
            raise APIError(
                message="Failed to parse response as JSON",
                response_text=response.text,
            ) from e

    async def test_connection(self) -> Dict[str, Any]:
        """Test the connection to the backend.

        Returns:
            The API response data.

        Raises:
            APIError: If the connection test fails.
        """
        url = f"{self.base_url}"
        logger.info(f"Testing connection to: {url}")
        try:
            response = await self.client.get(url)
            data = await self._handle_response(response)
            logger.info(f"Connection test successful!")
            return data
        except httpx.RequestError as e:
            logger.error(f"Connection test failed: {str(e)}")
            raise APIError(f"Connection failed: {str(e)}") from e

    async def create_conversation(self) -> str:
        """Create a new conversation and return its ID.

        Returns:
            The conversation ID.

        Raises:
            APIError: If the conversation creation fails.
        """
        url = f"{self.base_url}/api/v1/conversation/create"
        logger.info(f"Creating conversation at: {url}")
        try:
            response = await self.client.post(url)
            data = await self._handle_response(response)
            conversation_id = data["conversation_id"]
            logger.info(f"Created conversation with ID: {conversation_id}")
            return conversation_id
        except (httpx.RequestError, KeyError) as e:
            logger.error(f"Failed to create conversation: {str(e)}")
            raise APIError(f"Failed to create conversation: {str(e)}") from e

    async def get_conversations(self, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
        """Get a list of conversations.

        Args:
            limit: The maximum number of conversations to return.
            offset: The offset to start from.

        Returns:
            A dictionary containing the conversations.

        Raises:
            APIError: If the request fails.
        """
        url = f"{self.base_url}/api/v1/conversation/list"
        params = {"limit": limit, "offset": offset}
        logger.info(f"Getting conversations from: {url} with params: {params}")
        try:
            response = await self.client.get(url, params=params)
            data = await self._handle_response(response)
            logger.info(f"Retrieved {len(data.get('datas', []))} conversations")
            return data
        except httpx.RequestError as e:
            logger.error(f"Failed to get conversations: {str(e)}")
            raise APIError(f"Failed to get conversations: {str(e)}") from e

    async def get_conversation_info(self, conversation_id: str) -> Dict[str, Any]:
        """Get information about a conversation.

        Args:
            conversation_id: The ID of the conversation.

        Returns:
            A dictionary containing the conversation information.

        Raises:
            APIError: If the request fails.
        """
        url = f"{self.base_url}/api/v1/conversation/info/{conversation_id}"
        logger.info(f"Getting conversation info from: {url}")
        try:
            response = await self.client.get(url)
            data = await self._handle_response(response)
            logger.info(f"Retrieved info for conversation: {conversation_id}")
            return data
        except httpx.RequestError as e:
            logger.error(f"Failed to get conversation info: {str(e)}")
            raise APIError(f"Failed to get conversation info: {str(e)}") from e

    async def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation.

        Args:
            conversation_id: The ID of the conversation.

        Raises:
            APIError: If the deletion fails.
        """
        url = f"{self.base_url}/api/v1/conversation/delete/{conversation_id}"
        logger.info(f"Deleting conversation at: {url}")
        try:
            response = await self.client.post(url)
            await self._handle_response(response)
            logger.info(f"Deleted conversation: {conversation_id}")
        except httpx.RequestError as e:
            logger.error(f"Failed to delete conversation: {str(e)}")
            raise APIError(f"Failed to delete conversation: {str(e)}") from e

    async def chat_stream(
        self,
        conversation_id: str,
        prompt: str,
        model_settings: Optional[ModelSettings] = None,
        always_permit: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream chat responses from the API.

        Args:
            conversation_id: The ID of the conversation.
            prompt: The prompt to send.
            model_settings: Optional model settings.

        Yields:
            SSE events from the API.

        Raises:
            APIError: If the streaming fails.
        """
        url = f"{self.base_url}/api/v1/conversation/chat/{conversation_id}"
        payload = {"prompt": prompt}
        if always_permit:
            payload["auto_permit"] = True
        if model_settings:
            payload["llm_model_settings"] = model_settings

        logger.info(f"Streaming chat from: {url} with prompt: {prompt[:50]}...(always_permit: {always_permit})")
        try:
            async with aconnect_sse(self.client, "POST", url, json=payload) as event_source:
                logger.info(f"Connected to SSE stream for conversation: {conversation_id}")
                async for sse in event_source.aiter_sse():
                    if sse.data:
                        try:
                            yield json.loads(sse.data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse SSE data as JSON: {sse.data}")
                            raise APIError(f"Failed to parse SSE data: {str(e)}") from e
        except httpx.RequestError as e:
            logger.error(f"Streaming chat failed: {str(e)}")
            raise APIError(f"Streaming chat failed: {str(e)}") from e

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

        Raises:
            APIError: If the tool call permission fails.
        """
        url = f"{self.base_url}/api/v1/conversation/permit-call-tool/{conversation_id}"
        payload = {"execute_all_tool_calls": execute_all}
        if tool_call_ids:
            payload["execute_tool_call_ids"] = tool_call_ids

        logger.info(f"Permitting tool calls at: {url}")
        logger.info(f"Execute all: {execute_all}, Tool call IDs: {tool_call_ids}")

        try:
            async with aconnect_sse(self.client, "POST", url, json=payload) as event_source:
                logger.info(f"Connected to SSE stream for tool call permission: {conversation_id}")
                async for sse in event_source.aiter_sse():
                    if sse.data:
                        try:
                            yield json.loads(sse.data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse SSE data as JSON: {sse.data}")
                            raise APIError(f"Failed to parse SSE data: {str(e)}") from e
        except httpx.RequestError as e:
            logger.error(f"Tool call permission failed: {str(e)}")
            raise APIError(f"Tool call permission failed: {str(e)}") from e

    async def retry_conversation(
        self, conversation_id: str, model_settings: Optional[ModelSettings] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Retry a conversation.

        Args:
            conversation_id: The ID of the conversation.
            model_settings: Optional model settings.

        Yields:
            SSE events from the API.

        Raises:
            APIError: If the retry fails.
        """
        url = f"{self.base_url}/api/v1/conversation/retry/{conversation_id}"
        payload = {}
        if model_settings:
            payload["llm_model_settings"] = model_settings

        logger.info(f"Retrying conversation at: {url}")
        try:
            async with aconnect_sse(self.client, "POST", url, json=payload) as event_source:
                logger.info(f"Connected to SSE stream for retry: {conversation_id}")
                async for sse in event_source.aiter_sse():
                    if sse.data:
                        try:
                            yield json.loads(sse.data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse SSE data as JSON: {sse.data}")
                            raise APIError(f"Failed to parse SSE data: {str(e)}") from e
        except httpx.RequestError as e:
            logger.error(f"Retry failed: {str(e)}")
            raise APIError(f"Retry failed: {str(e)}") from e

    async def close(self) -> None:
        """Close the client."""
        logger.info("Closing API client")
        await self.client.aclose()
