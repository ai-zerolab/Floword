"""Tool call popup component for the Floword UI."""

from collections.abc import AsyncIterable
from typing import Any, Dict, List, Optional, Tuple

import gradio as gr

from floword.ui.api_client import FlowordAPIClient
from floword.ui.message_processor import MessageProcessor


# Global state
message_processor = MessageProcessor()


async def permit_tool_call(
    history: List[Dict[str, Any]],
    conversation_id: str,
    selected_tool_calls: List[str],
    always_permit: bool,
    url: str,
    token: Optional[str] = None,
) -> AsyncIterable[List[Dict[str, Any]]]:
    """Permit tool calls.

    Args:
        history: The conversation history.
        conversation_id: The ID of the conversation.
        selected_tool_calls: The IDs of the selected tool calls to permit.
        always_permit: Whether to always permit tool calls.
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        The updated conversation history.
    """
    if not conversation_id:
        raise gr.Error("No conversation selected. Please create a new conversation first.")

    # Clear the message processor
    message_processor.clear()

    # Create the API client
    client = FlowordAPIClient(url, token)

    try:
        # Stream the response
        async for event in client.permit_tool_call(
            conversation_id,
            execute_all=always_permit,
            tool_call_ids=selected_tool_calls if not always_permit else None,
        ):
            # Process the event
            message_update, tool_calls = message_processor.process_event(event)

            # If we have tool calls, we need to permit them again
            if tool_calls:
                # This shouldn't happen, but just in case
                continue

            # If we have a message update, add it to the history
            if message_update:
                # Check if we already have an assistant message
                if history and history[-1]["role"] == "assistant":
                    # Update the existing message
                    history[-1] = message_update
                else:
                    # Add a new message
                    history.append(message_update)

                # Yield the updated history
                yield history

        # Get the final message
        final_message = message_processor.get_current_message()
        if final_message:
            # Check if we already have an assistant message
            if history and history[-1]["role"] == "assistant":
                # Update the existing message
                history[-1] = final_message
            else:
                # Add a new message
                history.append(final_message)

        await client.close()
        yield history
    except Exception as e:
        await client.close()
        raise gr.Error(f"Failed to permit tool call: {str(e)}")


# Wrapper function to handle async permit_tool_call
async def permit_tool_call_wrapper(
    history: List[Dict[str, Any]],
    conversation_id: str,
    selected_tool_calls: List[str],
    always_permit: bool,
    url: str,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Wrapper for permit_tool_call to handle async generator.

    Args:
        history: The conversation history.
        conversation_id: The ID of the conversation.
        selected_tool_calls: The IDs of the selected tool calls to permit.
        always_permit: Whether to always permit tool calls.
        url: The URL of the backend.
        token: Optional API token.

    Returns:
        The updated conversation history.
    """
    # Create a copy of the history to avoid modifying the original
    history_copy = list(history)

    # Consume the generator
    async for updated_history in permit_tool_call(
        history_copy,
        conversation_id,
        selected_tool_calls,
        always_permit,
        url,
        token,
    ):
        history_copy = updated_history

    return history_copy


def create_tool_call_popup() -> Tuple[gr.Group, gr.Dataframe, gr.Checkbox, gr.Button, gr.Button, gr.Button]:
    """Create the tool call popup component.

    Returns:
        A tuple of (popup, tool_calls_list, always_permit, permit_btn, permit_all_btn, cancel_btn).
    """
    with gr.Group(visible=False) as tool_call_popup:
        gr.Markdown("### Tool Calls")

        tool_calls_list = gr.Dataframe(
            headers=["ID", "Tool Name", "Arguments", "Selected"],
            datatype=["str", "str", "str", "bool"],
            row_count=5,
            col_count=(4, "fixed"),
            interactive=True,
        )

        with gr.Row():
            always_permit = gr.Checkbox(label="Always permit tool calls", value=False)
            permit_btn = gr.Button("Permit Selected", variant="primary")
            permit_all_btn = gr.Button("Permit All", variant="secondary")
            cancel_btn = gr.Button("Cancel")

    return tool_call_popup, tool_calls_list, always_permit, permit_btn, permit_all_btn, cancel_btn


def prepare_tool_calls(tool_calls_data: Optional[List[Dict[str, Any]]]) -> Tuple[List[List[Any]], List[str]]:
    """Prepare tool calls for display.

    Args:
        tool_calls_data: The tool calls data.

    Returns:
        A tuple of (tool_calls_list, tool_call_ids).
    """
    if not tool_calls_data:
        return [], []

    # Prepare the tool calls for display
    tool_calls_list = []
    tool_call_ids = []
    for tc in tool_calls_data:
        tool_calls_list.append([
            tc["tool_call_id"],
            tc["tool_name"],
            tc["args"],
            True,  # Selected by default
        ])
        tool_call_ids.append(tc["tool_call_id"])

    return tool_calls_list, tool_call_ids


def get_selected_tool_calls(df: List[List[Any]]) -> List[str]:
    """Get selected tool call IDs from the dataframe.

    Args:
        df: The dataframe.

    Returns:
        The selected tool call IDs.
    """
    selected_ids = []
    for row in df:
        if len(row) >= 4 and row[3]:  # If selected
            selected_ids.append(row[0])  # Add the ID
    return selected_ids
