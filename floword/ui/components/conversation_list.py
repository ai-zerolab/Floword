"""Conversation list component for the Floword UI."""

from typing import Any, Dict, List, Optional, Tuple, Callable

import gradio as gr

from floword.ui.api_client import APIError, FlowordAPIClient
from floword.ui.models.conversation import ConversationState

# Set up logging
from floword.log import logger


class ConversationList:
    """Conversation list component."""

    def __init__(self):
        """Initialize the conversation list."""
        self.conversations: List[Tuple[str, str]] = []  # (id, title) pairs

    def create_list(self) -> Tuple[gr.Button, gr.Dropdown, gr.State]:
        """Create the conversation list component.

        Returns:
            A tuple of (new_chat_button, conversation_list, conversation_ids).
        """
        gr.Markdown("### Conversations")
        new_chat_btn = gr.Button("New Chat", variant="primary")

        # Use Dropdown component to display conversation titles
        conversation_list = gr.Dropdown(
            choices=[],
            label="Select a conversation",
            interactive=True,
            allow_custom_value=False,
        )

        # Hidden state to store conversation IDs
        conversation_ids = gr.State([])

        return new_chat_btn, conversation_list, conversation_ids

    async def create_conversation(self, url: str, token: Optional[str] = None) -> Tuple[str, List[Tuple[str, str]]]:
        """Create a new conversation.

        Args:
            url: The URL of the backend.
            token: Optional API token.

        Returns:
            A tuple of (conversation_id, updated_conversation_list).

        Raises:
            APIError: If the conversation creation fails.
        """
        client = FlowordAPIClient(url, token)
        try:
            conversation_id = await client.create_conversation()

            # Get the updated conversation list
            self.conversations = await self.get_conversations(url, token)

            await client.close()
            return conversation_id, self.conversations
        except APIError as e:
            await client.close()
            logger.error(f"Failed to create conversation: {str(e)}")
            raise gr.Error(f"Failed to create conversation: {str(e)}")
        except Exception as e:
            await client.close()
            logger.exception(e)
            raise gr.Error(f"Failed to create conversation: {str(e)}")

    async def get_conversations(self, url: str, token: Optional[str] = None) -> List[Tuple[str, str]]:
        """Get the list of conversations.

        Args:
            url: The URL of the backend.
            token: Optional API token.

        Returns:
            The list of conversations as (id, title) tuples.

        Raises:
            APIError: If the request fails.
        """
        client = FlowordAPIClient(url, token)
        try:
            conversations_data = await client.get_conversations()
            conversation_list = []
            for conv in conversations_data["datas"]:
                conversation_list.append((conv["conversation_id"], conv["title"]))

            self.conversations = conversation_list
            await client.close()
            return conversation_list
        except APIError as e:
            await client.close()
            logger.error(f"Failed to get conversations: {str(e)}")
            raise gr.Error(f"Failed to get conversations: {str(e)}")
        except Exception as e:
            await client.close()
            logger.exception(e)
            raise gr.Error(f"Failed to get conversations: {str(e)}")

    async def load_conversation(self, conversation_id: str, url: str, token: Optional[str] = None) -> ConversationState:
        """Load a conversation.

        Args:
            conversation_id: The ID of the conversation to load.
            url: The URL of the backend.
            token: Optional API token.

        Returns:
            The conversation state.

        Raises:
            APIError: If the request fails.
        """
        client = FlowordAPIClient(url, token)
        try:
            conversation_data = await client.get_conversation_info(conversation_id)

            # Create a conversation state from the data
            conversation_state = ConversationState(
                conversation_id=conversation_id,
                title=next((title for cid, title in self.conversations if cid == conversation_id), "Untitled"),
            )
            conversation_state.from_api_messages(conversation_data["messages"])

            await client.close()
            return conversation_state
        except APIError as e:
            await client.close()
            logger.error(f"Failed to load conversation: {str(e)}")
            raise gr.Error(f"Failed to load conversation: {str(e)}")
        except Exception as e:
            await client.close()
            logger.exception(e)
            raise gr.Error(f"Failed to load conversation: {str(e)}")

    def find_conversation_id(self, selected_title: str) -> str:
        """Find the conversation ID for a selected title.

        Args:
            selected_title: The selected conversation title.

        Returns:
            The conversation ID.
        """
        for conv_id, title in self.conversations:
            if title == selected_title:
                return conv_id
        return ""

    def update_dropdown(self, selected_id: Optional[str] = None) -> Dict[str, Any]:
        """Update the conversation dropdown.

        Args:
            selected_id: Optional ID of the conversation to select.

        Returns:
            A Gradio update object for the dropdown.
        """
        titles = [title for _, title in self.conversations]

        if selected_id:
            selected_title = next((title for cid, title in self.conversations if cid == selected_id), None)
            return gr.update(choices=titles, value=selected_title)
        else:
            return gr.update(choices=titles, value=None)


# Create a global conversation list for use in the UI
conversation_list = ConversationList()


def create_conversation_list() -> Tuple[gr.Button, gr.Dropdown, gr.State]:
    """Create the conversation list component.

    Returns:
        A tuple of (new_chat_button, conversation_list, conversation_ids).
    """
    return conversation_list.create_list()


async def create_conversation(url: str, token: Optional[str] = None) -> Tuple[str, List[Tuple[str, str]]]:
    """Create a new conversation.

    Args:
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        A tuple of (conversation_id, updated_conversation_list).
    """
    return await conversation_list.create_conversation(url, token)


async def get_conversations(url: str, token: Optional[str] = None) -> List[Tuple[str, str]]:
    """Get the list of conversations.

    Args:
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        The list of conversations as (id, title) tuples.
    """
    return await conversation_list.get_conversations(url, token)


async def load_conversation(conversation_id: str, url: str, token: Optional[str] = None) -> List[Dict[str, str]]:
    """Load a conversation.

    Args:
        conversation_id: The ID of the conversation to load.
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        The conversation messages in Gradio format.
    """
    conversation_state = await conversation_list.load_conversation(conversation_id, url, token)
    return conversation_state.to_gradio_history()


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
