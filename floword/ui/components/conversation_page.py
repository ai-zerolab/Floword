"""Conversation page component for the Floword UI."""

from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from floword.ui.components.chat_interface import (
    create_chat_interface,
    send_message,
    update_models,
)
from floword.ui.components.conversation_list import (
    create_conversation,
    create_conversation_list,
    get_conversations,
    load_conversation,
)
from floword.ui.components.tool_call_popup import (
    create_tool_call_popup,
    get_selected_tool_calls,
    permit_tool_call_wrapper,
    prepare_tool_calls,
)
from floword.ui.api_client import FlowordAPIClient


async def check_server_connection(url: str, token: Optional[str] = None) -> Tuple[bool, str]:
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
        return False, f"Cannot connect to server at {url}. Please check your backend configuration."


async def refresh_conversations(url: str, token: Optional[str] = None) -> Tuple[Dict, List[Tuple[str, str]], str, bool]:
    """Refresh the conversation list.

    Args:
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        A tuple of (conversation_list_update, conversation_id_title_pairs, error_message, is_connected).
    """
    is_connected, error_message = await check_server_connection(url, token)

    if not is_connected:
        return gr.update(choices=[]), [], error_message, False

    try:
        conversations = await get_conversations(url, token)
        titles = [title for _, title in conversations]
        return gr.update(choices=titles, value=None), conversations, "", True
    except Exception as e:
        return gr.update(choices=[]), [], str(e), False


def find_conversation_id(selected_title: str, conversations: List[Tuple[str, str]]) -> str:
    """Find the conversation ID for a selected title.

    Args:
        selected_title: The selected conversation title.
        conversations: The list of conversation (id, title) pairs.

    Returns:
        The conversation ID.
    """
    for conv_id, title in conversations:
        if title == selected_title:
            return conv_id
    return ""


# Wrapper function to handle async create_conversation
async def create_conversation_wrapper(
    connected: bool, url: str, token: Optional[str] = None
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
    return await create_conversation(url, token)


# Function to update conversation list after creating a new conversation
def update_after_create(
    conv_id: Optional[str], conversations: List[Tuple[str, str]]
) -> Tuple[Dict, List[Tuple[str, str]]]:
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


# Wrapper function to handle async load_conversation
async def load_conversation_wrapper(conv_id: str, url: str, token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Wrapper for load_conversation to handle async.

    Args:
        conv_id: The ID of the conversation to load.
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        The conversation messages.
    """
    if not conv_id:
        return []
    return await load_conversation(conv_id, url, token)


# Wrapper function to handle async send_message
async def send_message_wrapper(
    connected: bool,
    message: str,
    history: List[Dict[str, Any]],
    conversation_id: str,
    url: str,
    token: Optional[str] = None,
    provider: str = "openai",
    model_name: str = "gpt-4o",
    temperature: float = 0.7,
    max_tokens: int = 1000,
) -> Tuple[List[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    """Wrapper for send_message to handle async generator.

    Args:
        connected: Whether the backend is connected.
        message: The message to send.
        history: The conversation history.
        conversation_id: The ID of the conversation.
        url: The URL of the backend.
        token: Optional API token.
        provider: The model provider.
        model_name: The model name.
        temperature: The temperature parameter.
        max_tokens: The max tokens parameter.

    Returns:
        A tuple of (updated_history, tool_calls_data).
    """
    if not connected:
        return history, None

    # Create a copy of the history to avoid modifying the original
    history_copy = list(history)
    tool_calls_data = None

    # Consume the generator
    async for updated_history, tool_calls in send_message(
        message,
        history_copy,
        conversation_id,
        url,
        token,
        provider,
        model_name,
        temperature,
        max_tokens,
    ):
        history_copy = updated_history
        if tool_calls:
            tool_calls_data = tool_calls

    return history_copy, tool_calls_data


def create_conversation_page() -> gr.Blocks:
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

        # State variables
        conversation_id = gr.State(None)
        backend_url = gr.State("http://localhost:9772")
        api_token = gr.State(None)
        tool_calls_state = gr.State([])
        is_connected = gr.State(False)

        # Tool call popup
        tool_call_popup, tool_calls_list, always_permit, permit_btn, permit_all_btn, cancel_btn = (
            create_tool_call_popup()
        )

        # Event handlers

        # Function to update connection status message
        def update_connection_status(error_msg: str, is_connected: bool) -> str:
            if not is_connected:
                return f"⚠️ {error_msg}"
            return ""

        # Refresh conversations when the page loads and check server connection
        conversation_page.load(
            fn=refresh_conversations,
            inputs=[backend_url, api_token],
            outputs=[conversation_list, conversation_ids, connection_status, is_connected],
        )

        # Create a new conversation
        new_chat_btn.click(
            fn=create_conversation_wrapper,
            inputs=[is_connected, backend_url, api_token],
            outputs=[conversation_id, conversation_ids],
        ).then(
            fn=update_after_create,
            inputs=[conversation_id, conversation_ids],
            outputs=[conversation_list, conversation_ids],
        )

        # Handle conversation selection
        conversation_list.change(
            fn=find_conversation_id,
            inputs=[conversation_list, conversation_ids],
            outputs=[conversation_id],
        ).then(
            fn=load_conversation_wrapper,
            inputs=[conversation_id, backend_url, api_token],
            outputs=[chatbot],
        )

        # Update model list when provider changes
        provider.change(
            fn=update_models,
            inputs=[provider],
            outputs=[model_name],
        )

        # Send message
        submit_btn.click(
            fn=send_message_wrapper,
            inputs=[
                is_connected,
                msg,
                chatbot,
                conversation_id,
                backend_url,
                api_token,
                provider,
                model_name,
                temperature,
                max_tokens,
            ],
            outputs=[chatbot, tool_calls_state],
        ).then(
            fn=lambda tool_calls_data: (
                tool_calls_data is not None,  # Show the popup if we have tool calls
                *prepare_tool_calls(tool_calls_data),
            )
            if tool_calls_data is not None
            else (False, [], []),
            inputs=[tool_calls_state],
            outputs=[tool_call_popup, tool_calls_list, tool_calls_state],
        ).then(
            fn=lambda: "",  # Clear the message input
            outputs=[msg],
        )

        # Submit message with Enter key
        msg.submit(
            fn=send_message_wrapper,
            inputs=[
                is_connected,
                msg,
                chatbot,
                conversation_id,
                backend_url,
                api_token,
                provider,
                model_name,
                temperature,
                max_tokens,
            ],
            outputs=[chatbot, tool_calls_state],
        ).then(
            fn=lambda tool_calls_data: (
                tool_calls_data is not None,  # Show the popup if we have tool calls
                *prepare_tool_calls(tool_calls_data),
            )
            if tool_calls_data is not None
            else (False, [], []),
            inputs=[tool_calls_state],
            outputs=[tool_call_popup, tool_calls_list, tool_calls_state],
        ).then(
            fn=lambda: "",  # Clear the message input
            outputs=[msg],
        )

        # Permit tool call
        permit_btn.click(
            fn=lambda df, tool_calls: get_selected_tool_calls(df),
            inputs=[tool_calls_list, tool_calls_state],
            outputs=[tool_calls_state],
        ).then(
            fn=lambda connected, *args: permit_tool_call_wrapper(*args) if connected else args[0],
            inputs=[
                is_connected,
                chatbot,
                conversation_id,
                tool_calls_state,
                always_permit,
                backend_url,
                api_token,
            ],
            outputs=[chatbot],
        ).then(
            fn=lambda: (False, []),  # Hide the popup and clear tool calls
            outputs=[tool_call_popup, tool_calls_state],
        )

        # Permit all tool calls
        permit_all_btn.click(
            fn=lambda: True,  # Set always_permit to True
            outputs=[always_permit],
        ).then(
            fn=lambda connected, *args: permit_tool_call_wrapper(*args) if connected else args[0],
            inputs=[
                is_connected,
                chatbot,
                conversation_id,
                tool_calls_state,
                always_permit,
                backend_url,
                api_token,
            ],
            outputs=[chatbot],
        ).then(
            fn=lambda: (False, [], False),  # Hide the popup, clear tool calls, reset always_permit
            outputs=[tool_call_popup, tool_calls_state, always_permit],
        )

        # Cancel tool call
        cancel_btn.click(
            fn=lambda: (False, []),  # Hide the popup and clear tool calls
            outputs=[tool_call_popup, tool_calls_state],
        )

        # Refresh button
        refresh_btn.click(
            fn=refresh_conversations,
            inputs=[backend_url, api_token],
            outputs=[conversation_list, conversation_ids, connection_status, is_connected],
        )

    return conversation_page
