"""Conversation page component for the Floword UI."""

import asyncio
from typing import Any, Dict, List, Optional, Tuple, Callable

import gradio as gr

from floword.ui.api_client import APIError, FlowordAPIClient
from floword.ui.components.chat_interface import ChatInterface, create_chat_interface, update_models
from floword.ui.components.conversation_list import (
    ConversationList,
    create_conversation,
    create_conversation_list,
    find_conversation_id,
    get_conversations,
    load_conversation,
)
from floword.ui.components.tool_call_popup import (
    ToolCallPopup,
    create_tool_call_popup,
    get_selected_tool_calls,
    prepare_tool_calls,
)
from floword.ui.models.conversation import ConversationState

# Set up logging
from floword.log import logger


class ConversationPage:
    """Conversation page component."""

    def __init__(self):
        """Initialize the conversation page."""
        self.conversation_state = ConversationState()
        self.chat_interface = ChatInterface(self.conversation_state)
        self.tool_call_popup = ToolCallPopup(self.conversation_state)

    async def check_server_connection(self, url: str, token: Optional[str] = None) -> Tuple[bool, str]:
        """Check if the server is reachable.

        Args:
            url: The URL of the backend.
            token: Optional API token.

        Returns:
            A tuple of (is_connected, message).
        """
        client = FlowordAPIClient(url, token)
        try:
            # Try to get conversations as a simple API check
            await client.get_conversations()
            await client.close()
            return True, ""
        except Exception as e:
            await client.close()
            logger.error(f"Server connection check failed: {str(e)}")
            return False, f"Cannot connect to server at {url}. Please check your backend configuration."

    async def refresh_conversations(
        self, url: str, token: Optional[str] = None
    ) -> Tuple[Dict[str, Any], List[Tuple[str, str]], str, bool]:
        """Refresh the conversation list.

        Args:
            url: The URL of the backend.
            token: Optional API token.

        Returns:
            A tuple of (conversation_list_update, conversation_id_title_pairs, error_message, is_connected).
        """
        is_connected, error_message = await self.check_server_connection(url, token)

        if not is_connected:
            return gr.update(choices=[]), [], error_message, False

        try:
            conversations = await get_conversations(url, token)
            titles = [title for _, title in conversations]
            return gr.update(choices=titles, value=None), conversations, "", True
        except Exception as e:
            logger.exception(e)
            return gr.update(choices=[]), [], str(e), False

    async def create_conversation_wrapper(
        self, connected: bool, url: str, token: Optional[str] = None
    ) -> Tuple[Optional[str], List[Tuple[str, str]]]:
        """Wrapper for create_conversation to handle async.

        Args:
            connected: Whether the backend is connected.
            url: The URL of the backend.
            token: Optional API token.

        Returns:
            A tuple of (conversation_id, conversation_list).
        """
        if not connected:
            return None, []

        try:
            return await create_conversation(url, token)
        except Exception as e:
            logger.exception(e)
            raise gr.Error(f"Failed to create conversation: {str(e)}")

    def update_after_create(
        self, conv_id: Optional[str], conversations: List[Tuple[str, str]]
    ) -> Tuple[Dict[str, Any], List[Tuple[str, str]]]:
        """Update the conversation list after creating a new conversation.

        Args:
            conv_id: The ID of the newly created conversation.
            conversations: The list of conversation (id, title) pairs.

        Returns:
            A tuple of (conversation_list_update, conversation_id_title_pairs).
        """
        if not conv_id or not conversations:
            return gr.update(choices=[]), []

        titles = [title for _, title in conversations]
        # Set the value to the newly created conversation's title
        new_title = next((title for cid, title in conversations if cid == conv_id), None)
        return gr.update(choices=titles, value=new_title), conversations

    async def load_conversation_wrapper(
        self, conv_id: str, url: str, token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Wrapper for load_conversation to handle async.

        Args:
            conv_id: The ID of the conversation to load.
            url: The URL of the backend.
            token: Optional API token.

        Returns:
            The conversation messages in Gradio format.
        """
        if not conv_id:
            return []

        try:
            # Update the conversation state
            self.conversation_state.conversation_id = conv_id

            # Load the conversation
            conversation_state = await load_conversation(conv_id, url, token)

            # Return the conversation history in the format expected by Gradio
            if isinstance(conversation_state, list):
                # If it's already a list, check if it's in the right format
                if conversation_state and isinstance(conversation_state[0], dict) and "role" in conversation_state[0]:
                    return conversation_state

                # Convert from old format (list of lists) to new format (list of dicts)
                result = []
                for item in conversation_state:
                    if isinstance(item, list) and len(item) == 2:
                        user_msg, assistant_msg = item
                        if user_msg:
                            result.append({"role": "user", "content": user_msg})
                        if assistant_msg:
                            result.append({"role": "assistant", "content": assistant_msg})
                return result

            # If it's a ConversationState object, use its to_gradio_history method
            if hasattr(conversation_state, "to_gradio_history"):
                return conversation_state.to_gradio_history()

            return []
        except Exception as e:
            logger.exception(e)
            raise gr.Error(f"Failed to load conversation: {str(e)}")

    def update_tool_call_popup_visibility(self, show_popup: bool) -> Dict[str, Any]:
        """Update the visibility of the tool call popup.

        Args:
            show_popup: Whether to show the popup.

        Returns:
            A Gradio update object for the popup.
        """
        return gr.update(visible=show_popup)

    def handle_tool_calls(
        self, history: List[Dict[str, Any]], always_permit: bool
    ) -> Tuple[Dict[str, Any], List[List[Any]], List[Dict[str, Any]]]:
        """Handle tool calls and prepare the popup.

        Args:
            history: The conversation history.
            always_permit: Whether to always permit tool calls.

        Returns:
            A tuple of (popup_visibility, tool_calls_list, tool_calls_state).
        """
        # Check if the last message has a tool call
        if history and len(history) > 0:
            last_message = history[-1]
            if isinstance(last_message, dict) and last_message.get("role") == "assistant":
                metadata = last_message.get("metadata", {})
                if metadata and metadata.get("is_tool_call") and not always_permit:
                    # Extract tool calls from the message
                    tool_calls_data = []
                    for tc in self.conversation_state.pending_tool_calls:
                        tool_calls_data.append({
                            "tool_name": tc.tool_name,
                            "args": tc.args,
                            "tool_call_id": tc.tool_call_id,
                        })

                    if tool_calls_data:
                        tool_calls_list, _ = prepare_tool_calls(tool_calls_data)
                        return self.update_tool_call_popup_visibility(True), tool_calls_list, tool_calls_data

        # No tool calls or always_permit is True
        return self.update_tool_call_popup_visibility(False), [], []

    def create_page(self) -> gr.Blocks:
        """Create the conversation page.

        Returns:
            A Gradio Blocks component for the conversation page.
        """
        with gr.Blocks() as conversation_page:
            gr.Markdown("# Conversation")

            # Connection status
            connection_status = gr.Markdown("")

            with gr.Row():
                with gr.Column(scale=1):
                    # Conversation list
                    new_chat_btn, conversation_list, conversation_ids = create_conversation_list()

                    # Refresh button
                    refresh_btn = gr.Button("Refresh", variant="secondary")

                with gr.Column(scale=3):
                    # Chat interface
                    chatbot, msg, submit_btn, provider, model_name, temperature, max_tokens = create_chat_interface()

                    # Always permit tool calls checkbox
                    always_permit = gr.Checkbox(label="Always permit tool calls", value=True, interactive=False)

            # State variables
            conversation_id = gr.State(None)
            backend_url = gr.State("http://localhost:9772")
            api_token = gr.State(None)
            is_connected = gr.State(False)
            tool_calls_state = gr.State([])  # Proper state for tool calls
            selected_tool_calls = gr.State([])  # State for selected tool calls
            message_state = gr.State("")  # State for storing the message content

            # Tool call popup
            tool_call_popup, tool_calls_list, permit_btn, permit_all_btn, cancel_btn = create_tool_call_popup()

            # Event handlers

            # Function to update connection status message
            def update_connection_status(error_msg: str, is_connected: bool) -> str:
                if not is_connected:
                    return f"⚠️ {error_msg}"
                return ""

            # Refresh conversations when the page loads and check server connection
            conversation_page.load(
                fn=self.refresh_conversations,
                inputs=[backend_url, api_token],
                outputs=[conversation_list, conversation_ids, connection_status, is_connected],
            )

            # Create a new conversation
            new_chat_btn.click(
                fn=self.create_conversation_wrapper,
                inputs=[is_connected, backend_url, api_token],
                outputs=[conversation_id, conversation_ids],
            ).then(
                fn=self.update_after_create,
                inputs=[conversation_id, conversation_ids],
                outputs=[conversation_list, conversation_ids],
            )

            # Handle conversation selection
            conversation_list.change(
                fn=find_conversation_id,
                inputs=[conversation_list, conversation_ids],
                outputs=[conversation_id],
            ).then(
                fn=self.load_conversation_wrapper,
                inputs=[conversation_id, backend_url, api_token],
                outputs=[chatbot],
            ).then(
                fn=self.handle_tool_calls,
                inputs=[chatbot, always_permit],
                outputs=[tool_call_popup, tool_calls_list, tool_calls_state],
            )

            # Update model list when provider changes
            provider.change(
                fn=update_models,
                inputs=[provider],
                outputs=[model_name],
            )

            # Send message
            def save_message_to_state(message, *args):
                # Save the message to state before it gets cleared
                return message, *args

            submit_btn.click(
                fn=save_message_to_state,  # Save the message to state
                inputs=[
                    msg,
                    is_connected,
                    chatbot,
                    conversation_id,
                    backend_url,
                    api_token,
                    provider,
                    model_name,
                    temperature,
                    max_tokens,
                    always_permit,
                ],
                outputs=[
                    message_state,  # Store the message in state
                    is_connected,
                    chatbot,
                    conversation_id,
                    backend_url,
                    api_token,
                    provider,
                    model_name,
                    temperature,
                    max_tokens,
                    always_permit,
                ],
                queue=False,
            ).then(
                fn=lambda: "",  # Clear the message input
                outputs=[msg],
                queue=False,
            ).then(
                fn=send_message,
                inputs=[
                    message_state,  # Use the message from state
                    chatbot,
                    conversation_id,
                    backend_url,
                    api_token,
                    provider,
                    model_name,
                    temperature,
                    max_tokens,
                    always_permit,
                ],
                outputs=chatbot,
            ).then(
                fn=self.handle_tool_calls,
                inputs=[chatbot, always_permit],
                outputs=[tool_call_popup, tool_calls_list, tool_calls_state],
            )

            # Submit message with Enter key
            msg.submit(
                fn=save_message_to_state,  # Save the message to state
                inputs=[
                    msg,
                    is_connected,
                    chatbot,
                    conversation_id,
                    backend_url,
                    api_token,
                    provider,
                    model_name,
                    temperature,
                    max_tokens,
                    always_permit,
                ],
                outputs=[
                    message_state,  # Store the message in state
                    is_connected,
                    chatbot,
                    conversation_id,
                    backend_url,
                    api_token,
                    provider,
                    model_name,
                    temperature,
                    max_tokens,
                    always_permit,
                ],
                queue=False,
            ).then(
                fn=lambda: "",  # Clear the message input
                outputs=[msg],
                queue=False,
            ).then(
                fn=send_message,
                inputs=[
                    message_state,  # Use the message from state
                    chatbot,
                    conversation_id,
                    backend_url,
                    api_token,
                    provider,
                    model_name,
                    temperature,
                    max_tokens,
                    always_permit,
                ],
                outputs=chatbot,
            ).then(
                fn=self.handle_tool_calls,
                inputs=[chatbot, always_permit],
                outputs=[tool_call_popup, tool_calls_list, tool_calls_state],
            )

            # Process tool calls selection
            def process_tool_calls_selection(tool_calls_list, tool_calls_state):
                selected_ids = get_selected_tool_calls(tool_calls_list, tool_calls_state)
                return selected_ids

            # Permit tool call
            permit_btn.click(
                fn=process_tool_calls_selection,
                inputs=[tool_calls_list, tool_calls_state],
                outputs=[selected_tool_calls],
                queue=False,
            ).then(
                fn=permit_tool_call,
                inputs=[
                    chatbot,
                    conversation_id,
                    selected_tool_calls,
                    always_permit,
                    backend_url,
                    api_token,
                ],
                outputs=chatbot,
            ).then(
                fn=lambda: (gr.update(visible=False), [], []),  # Hide the popup and clear tool calls
                outputs=[tool_call_popup, tool_calls_list, tool_calls_state],
                queue=False,
            )

            # Permit all tool calls
            permit_all_btn.click(
                fn=lambda: True,  # Set always_permit to True
                outputs=[always_permit],
                queue=False,
            ).then(
                fn=permit_tool_call,
                inputs=[
                    chatbot,
                    conversation_id,
                    selected_tool_calls,  # This will be empty, but that's OK for always_permit=True
                    always_permit,
                    backend_url,
                    api_token,
                ],
                outputs=chatbot,
            ).then(
                fn=lambda: (
                    gr.update(visible=False),
                    [],
                    [],
                    False,
                ),  # Hide the popup, clear tool calls, reset always_permit
                outputs=[tool_call_popup, tool_calls_list, tool_calls_state, always_permit],
                queue=False,
            )

            # Cancel tool call
            cancel_btn.click(
                fn=lambda: (gr.update(visible=False), [], []),  # Hide the popup and clear tool calls
                outputs=[tool_call_popup, tool_calls_list, tool_calls_state],
                queue=False,
            )

            # Refresh button
            refresh_btn.click(
                fn=self.refresh_conversations,
                inputs=[backend_url, api_token],
                outputs=[conversation_list, conversation_ids, connection_status, is_connected],
            )

        return conversation_page


# Create a global conversation page for use in the UI
conversation_page = ConversationPage()


def create_conversation_page() -> gr.Blocks:
    """Create the conversation page.

    Returns:
        A Gradio Blocks component for the conversation page.
    """
    return conversation_page.create_page()


# Import at the end to avoid circular imports
from floword.ui.components.chat_interface import send_message, permit_tool_call
