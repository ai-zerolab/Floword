"""Conversation list component for the Floword UI."""

from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from floword.ui.api_client import FlowordAPIClient


async def create_conversation(url: str, token: Optional[str] = None) -> Tuple[str, List[Tuple[str, str]]]:
    """Create a new conversation.

    Args:
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        A tuple of (conversation_id, updated_conversation_list).
    """
    client = FlowordAPIClient(url, token)
    try:
        conversation_id = await client.create_conversation()

        # Get the updated conversation list
        conversations = await client.get_conversations()
        conversation_list = []
        for conv in conversations["datas"]:
            conversation_list.append((conv["conversation_id"], conv["title"]))

        await client.close()
        return conversation_id, conversation_list
    except Exception as e:
        await client.close()
        raise gr.Error(f"Failed to create conversation: {str(e)}")


async def get_conversations(url: str, token: Optional[str] = None) -> List[Tuple[str, str]]:
    """Get the list of conversations.

    Args:
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        The list of conversations as (id, title) tuples.
    """
    client = FlowordAPIClient(url, token)
    try:
        conversations = await client.get_conversations()
        conversation_list = []
        for conv in conversations["datas"]:
            conversation_list.append((conv["conversation_id"], conv["title"]))

        await client.close()
        return conversation_list
    except Exception as e:
        await client.close()
        raise gr.Error(f"Failed to get conversations: {str(e)}")


async def load_conversation(conversation_id: str, url: str, token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load a conversation.

    Args:
        conversation_id: The ID of the conversation to load.
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        The conversation messages.
    """
    client = FlowordAPIClient(url, token)
    try:
        conversation = await client.get_conversation_info(conversation_id)
        await client.close()
        return conversation["messages"]
    except Exception as e:
        await client.close()
        raise gr.Error(f"Failed to load conversation: {str(e)}")


def create_conversation_list() -> Tuple[gr.Button, gr.Radio, gr.State]:
    """Create the conversation list component.

    Returns:
        A tuple of (new_chat_button, conversation_list, conversation_ids).
    """
    gr.Markdown("### Conversations")
    new_chat_btn = gr.Button("New Chat", variant="primary")

    # Use Radio component to display conversation titles
    conversation_list = gr.Radio(
        choices=[],
        label="Select a conversation",
        type="value",
        interactive=True,
    )

    # Hidden state to store conversation IDs
    conversation_ids = gr.State([])

    return new_chat_btn, conversation_list, conversation_ids
