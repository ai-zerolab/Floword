"""Chat interface component for the Floword UI."""

import asyncio
from typing import Any, Dict, List, Optional, Tuple, Callable, AsyncGenerator, Union

import gradio as gr

from floword.llms.models import get_known_models, get_supported_providers
from floword.ui.api_client import APIError, FlowordAPIClient
from floword.ui.message_processor import MessageProcessor
from floword.ui.models.conversation import (
    ConversationState,
    Message,
    MessageRole,
    ToolCall,
)
from floword.log import logger
from pydantic_ai.models import ModelSettings

# Set up logging


class ChatInterface:
    """Chat interface component."""

    def __init__(self, conversation_state: Optional[ConversationState] = None):
        """Initialize the chat interface.

        Args:
            conversation_state: Optional conversation state to use.
        """
        self.conversation_state = conversation_state or ConversationState()
        self.message_processor = MessageProcessor(self.conversation_state)
        self.streaming_task = None
        self.cancel_event = asyncio.Event()

    def create_interface(
        self,
    ) -> Tuple[
        gr.Chatbot,
        gr.Textbox,
        gr.Button,
        gr.Dropdown,
        gr.Dropdown,
        gr.Slider,
        gr.Number,
    ]:
        """Create the chat interface component.

        Returns:
            A tuple of (chatbot, message_input, submit_button, provider, model_name, temperature, max_tokens).
        """
        chatbot = gr.Chatbot(
            height=500,
            show_copy_button=True,
            render_markdown=True,
            type="messages",
            value=self.conversation_state.to_gradio_history(),
        )

        with gr.Row():
            with gr.Column(scale=8):
                msg = gr.Textbox(
                    placeholder="Type a message...",
                    show_label=False,
                    container=False,
                    scale=8,
                )
            with gr.Column(scale=1):
                submit_btn = gr.Button("Send", variant="primary")

        with gr.Accordion("Model Settings", open=False):
            with gr.Row(visible=False):
                provider = gr.Dropdown(
                    choices=get_supported_providers(),
                    label="Provider",
                    value="openai",
                )
                model_name = gr.Dropdown(
                    label="Model",
                    choices=get_known_models("openai"),
                    value="gpt-4o",
                )

            with gr.Row():
                temperature = gr.Slider(
                    minimum=0.0,
                    maximum=1.0,
                    value=0.7,
                    step=0.1,
                    label="Temperature",
                )
                max_tokens = gr.Number(
                    value=8192,
                    label="Max Tokens",
                    precision=0,
                )

        return chatbot, msg, submit_btn, provider, model_name, temperature, max_tokens

    def update_models(self, provider: str) -> List[str]:
        """Update the model list based on the selected provider.

        Args:
            provider: The selected provider.

        Returns:
            A list of models for the provider.
        """
        return get_known_models(provider)

    async def send_message(
        self,
        message: str,
        conversation_id: str,
        url: str,
        token: Optional[str] = None,
        provider: str = "openai",
        model_name: str = "gpt-4o",
        temperature: float = 0.7,
        max_tokens: int = 8192,
        on_update: Optional[Callable[[ConversationState], None]] = None,
        always_permit: bool = False,
    ) -> AsyncGenerator[List[Dict[str, Any]], None]:
        """Send a message to the backend and stream the response.

        Args:
            message: The message to send.
            conversation_id: The ID of the conversation.
            url: The URL of the backend.
            token: Optional API token.
            provider: The model provider.
            model_name: The model name.
            temperature: The temperature parameter.
            max_tokens: The max tokens parameter.
            on_update: Optional callback for state updates.

        Yields:
            The updated conversation history in Gradio format.

        Raises:
            gr.Error: If the message sending fails.
        """
        if not conversation_id:
            raise gr.Error("No conversation selected. Please create a new conversation first.")

        # Reset state
        self.cancel_event.clear()
        self.message_processor.clear()
        self.conversation_state.error = None
        self.conversation_state.is_loading = True

        # Add the user message to the conversation state
        self.conversation_state.add_user_message(message)

        # Yield the initial history with the user message
        yield self.conversation_state.to_gradio_history()

        # Create the model settings
        model_settings = ModelSettings(
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Create the API client
        client = FlowordAPIClient(url, token)

        try:
            # Add an empty assistant message to show typing indicator
            self.conversation_state.add_assistant_message("")

            if on_update:
                on_update(self.conversation_state)

            # Yield the history with the empty assistant message
            yield self.conversation_state.to_gradio_history()

            # Stream the response
            tool_calls_data = None
            async for event in client.chat_stream(conversation_id, message, model_settings, always_permit):
                # Check if we should cancel
                if self.cancel_event.is_set():
                    logger.info("Message streaming cancelled")
                    break

                # Process the event
                message_updated, tool_calls_updated = self.message_processor.process_event(event)

                # If we have updates, yield the updated history
                if message_updated:
                    if on_update:
                        on_update(self.conversation_state)

                    yield self.conversation_state.to_gradio_history()

                # If we have tool calls, prepare to return them
                if tool_calls_updated and self.conversation_state.pending_tool_calls:
                    tool_calls_data = [
                        {
                            "tool_name": tc.tool_name,
                            "args": tc.args,
                            "tool_call_id": tc.tool_call_id,
                        }
                        for tc in self.conversation_state.pending_tool_calls
                    ]

                    if on_update:
                        on_update(self.conversation_state)

                    # Add is_tool_call flag to the last message's metadata
                    history = self.conversation_state.to_gradio_history()

                    # Yield the final history with tool calls
                    yield history

            # Update the state
            self.conversation_state.is_loading = False

            if on_update:
                on_update(self.conversation_state)

            # Yield the final history
            yield self.conversation_state.to_gradio_history()

            await client.close()

        except APIError as e:
            # Update the state
            self.conversation_state.is_loading = False
            self.conversation_state.error = str(e)

            if on_update:
                on_update(self.conversation_state)

            await client.close()
            raise gr.Error(f"Failed to send message: {str(e)}")

        except Exception as e:
            # Update the state
            self.conversation_state.is_loading = False
            self.conversation_state.error = str(e)

            if on_update:
                on_update(self.conversation_state)

            await client.close()
            logger.exception(e)
            raise gr.Error(f"Failed to send message: {str(e)}")

    def cancel_streaming(self) -> None:
        """Cancel the current streaming task."""
        if self.streaming_task and not self.streaming_task.done():
            self.cancel_event.set()

    async def permit_tool_call(
        self,
        conversation_id: str,
        selected_tool_calls: List[str],
        always_permit: bool,
        url: str,
        token: Optional[str] = None,
        on_update: Optional[Callable[[ConversationState], None]] = None,
    ) -> AsyncGenerator[List[Dict[str, Any]], None]:
        """Permit tool calls and stream the response.

        Args:
            conversation_id: The ID of the conversation.
            selected_tool_calls: The IDs of the selected tool calls to permit.
            always_permit: Whether to always permit tool calls.
            url: The URL of the backend.
            token: Optional API token.
            on_update: Optional callback for state updates.

        Yields:
            The updated conversation history in Gradio format.

        Raises:
            gr.Error: If the tool call permission fails.
        """
        if not conversation_id:
            raise gr.Error("No conversation selected. Please create a new conversation first.")

        # Reset state
        self.cancel_event.clear()
        self.message_processor.clear()
        self.conversation_state.error = None
        self.conversation_state.is_loading = True

        # Update the state
        self.conversation_state.always_permit_tools = always_permit

        if on_update:
            on_update(self.conversation_state)

        # Yield the initial history
        yield self.conversation_state.to_gradio_history()

        # Create the API client
        client = FlowordAPIClient(url, token)

        try:
            # Stream the response
            async for event in client.permit_tool_call(
                conversation_id,
                execute_all=always_permit,
                tool_call_ids=selected_tool_calls if not always_permit else None,
            ):
                # Check if we should cancel
                if self.cancel_event.is_set():
                    logger.info("Tool call permission streaming cancelled")
                    break

                # Process the event
                message_updated, tool_calls_updated = self.message_processor.process_event(event)

                # If we have updates, yield the updated history
                if message_updated or tool_calls_updated:
                    if on_update:
                        on_update(self.conversation_state)

                    yield self.conversation_state.to_gradio_history()

            # Clear pending tool calls
            self.conversation_state.clear_pending_tool_calls()

            # Update the state
            self.conversation_state.is_loading = False

            if on_update:
                on_update(self.conversation_state)

            # Yield the final history
            yield self.conversation_state.to_gradio_history()

            await client.close()

        except APIError as e:
            # Update the state
            self.conversation_state.is_loading = False
            self.conversation_state.error = str(e)

            if on_update:
                on_update(self.conversation_state)

            await client.close()
            raise gr.Error(f"Failed to permit tool call: {str(e)}")

        except Exception as e:
            # Update the state
            self.conversation_state.is_loading = False
            self.conversation_state.error = str(e)

            if on_update:
                on_update(self.conversation_state)

            await client.close()
            logger.exception(e)
            raise gr.Error(f"Failed to permit tool call: {str(e)}")


# Create a global chat interface for use in the UI
chat_interface = ChatInterface()


def create_chat_interface() -> Tuple[
    gr.Chatbot,
    gr.Textbox,
    gr.Button,
    gr.Dropdown,
    gr.Dropdown,
    gr.Slider,
    gr.Number,
]:
    """Create the chat interface component.

    Returns:
        A tuple of (chatbot, message_input, submit_button, provider, model_name, temperature, max_tokens).
    """
    return chat_interface.create_interface()


def update_models(provider: str) -> List[str]:
    """Update the model list based on the selected provider.

    Args:
        provider: The selected provider.

    Returns:
        A list of models for the provider.
    """
    return chat_interface.update_models(provider)


async def send_message(
    message: str,
    history: List[Dict[str, Any]],
    conversation_id: Union[str, Any],
    url: str,
    token: Optional[str] = None,
    provider: str = "openai",
    model_name: str = "gpt-4o",
    temperature: float = 0.7,
    max_tokens: int = 8192,
    always_permit: bool = False,
) -> AsyncGenerator[List[Dict[str, Any]], None]:
    """Send a message to the backend and stream the response.

    Args:
        message: The message to send.
        history: The conversation history.
        conversation_id: The ID of the conversation.
        url: The URL of the backend.
        token: Optional API token.
        provider: The model provider.
        model_name: The model name.
        temperature: The temperature parameter.
        max_tokens: The max tokens parameter.
        always_permit: Whether to always permit tool calls.

    Yields:
        The updated conversation history in Gradio format.
    """
    # Ensure conversation_id is a string
    if not isinstance(conversation_id, str):
        logger.warning(f"Expected conversation_id to be a string, got {type(conversation_id)}")
        if not conversation_id:
            raise gr.Error("No conversation selected. Please create a new conversation first.")
        # Try to convert to string if possible
        try:
            conversation_id = str(conversation_id)
        except Exception as e:
            logger.exception(e)
            raise gr.Error("Invalid conversation ID")

    # Convert the history to a conversation state
    conversation_state = ConversationState(conversation_id=conversation_id)
    for msg in history:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                conversation_state.add_user_message(content)
            elif role == "assistant":
                conversation_state.add_assistant_message(content)
                metadata = msg.get("metadata", {})
                if metadata and metadata.get("log"):
                    conversation_state.add_tool_call(ToolCall.model_validate_json(metadata["log"]))
    print(conversation_state)
    # Create a temporary chat interface with the conversation state
    temp_chat_interface = ChatInterface(conversation_state)

    # Send the message and stream the response
    async for updated_history in temp_chat_interface.send_message(
        message=message,
        conversation_id=conversation_id,
        url=url,
        token=token,
        provider=provider,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        always_permit=always_permit,
    ):
        yield updated_history


async def permit_tool_call(
    history: List[Dict[str, Any]],
    conversation_id: Union[str, Any],
    selected_tool_calls: Union[List[str], Any],
    always_permit: bool,
    url: str,
    token: Optional[str] = None,
) -> AsyncGenerator[List[Dict[str, Any]], None]:
    """Permit tool calls and stream the response.

    Args:
        history: The conversation history.
        conversation_id: The ID of the conversation.
        selected_tool_calls: The IDs of the selected tool calls to permit.
        always_permit: Whether to always permit tool calls.
        url: The URL of the backend.
        token: Optional API token.

    Yields:
        The updated conversation history in Gradio format.
    """
    # Ensure conversation_id is a string
    if not isinstance(conversation_id, str):
        logger.warning(f"Expected conversation_id to be a string, got {type(conversation_id)}")
        if not conversation_id:
            raise gr.Error("No conversation selected. Please create a new conversation first.")
        # Try to convert to string if possible
        try:
            conversation_id = str(conversation_id)
        except Exception as e:
            logger.exception(e)
            raise gr.Error("Invalid conversation ID")

    # Ensure selected_tool_calls is a list of strings
    if not isinstance(selected_tool_calls, list):
        logger.warning(f"Expected selected_tool_calls to be a list, got {type(selected_tool_calls)}")
        selected_tool_calls = []

    # Convert the history to a conversation state
    conversation_state = ConversationState(conversation_id=conversation_id)
    for msg in history:
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                conversation_state.add_user_message(content)
            elif role == "assistant":
                conversation_state.add_assistant_message(content)

    # Create a temporary chat interface with the conversation state
    temp_chat_interface = ChatInterface(conversation_state)

    # Permit the tool call and stream the response
    async for updated_history in temp_chat_interface.permit_tool_call(
        conversation_id=conversation_id,
        selected_tool_calls=selected_tool_calls,
        always_permit=always_permit,
        url=url,
        token=token,
    ):
        yield updated_history
