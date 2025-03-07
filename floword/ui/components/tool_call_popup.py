"""Tool call popup component for the Floword UI."""

from typing import Any, Dict, List, Optional, Tuple, Callable

import gradio as gr

from floword.ui.models.conversation import ConversationState, ToolCall, ToolCallStatus
from floword.log import logger


class ToolCallPopup:
    """Tool call popup component."""

    def __init__(self, conversation_state: Optional[ConversationState] = None):
        """Initialize the tool call popup.

        Args:
            conversation_state: Optional conversation state to use.
        """
        self.conversation_state = conversation_state or ConversationState()

    def create_popup(self) -> Tuple[gr.Group, gr.Dataframe, gr.Button, gr.Button, gr.Button]:
        """Create the tool call popup component.

        Returns:
            A tuple of (popup, tool_calls_list, permit_btn, permit_all_btn, cancel_btn).
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
                permit_btn = gr.Button("Permit Selected", variant="primary")
                permit_all_btn = gr.Button("Permit All", variant="secondary")
                cancel_btn = gr.Button("Cancel")

        return tool_call_popup, tool_calls_list, permit_btn, permit_all_btn, cancel_btn

    def prepare_tool_calls(self) -> Tuple[List[List[Any]], List[str]]:
        """Prepare tool calls for display.

        Returns:
            A tuple of (tool_calls_list, tool_call_ids).
        """
        if not self.conversation_state.pending_tool_calls:
            return [], []

        # Prepare the tool calls for display
        tool_calls_list = []
        tool_call_ids = []
        for tc in self.conversation_state.pending_tool_calls:
            tool_calls_list.append([
                tc.tool_call_id,
                tc.tool_name,
                tc.args,
                tc.selected,  # Selected by default
            ])
            tool_call_ids.append(tc.tool_call_id)

        return tool_calls_list, tool_call_ids

    def get_selected_tool_calls(self, df: List[List[Any]]) -> List[str]:
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

    def update_tool_call_selection(self, df: List[List[Any]]) -> None:
        """Update the tool call selection in the conversation state.

        Args:
            df: The dataframe.
        """
        # Create a mapping of tool call IDs to selection status
        selection_map = {row[0]: row[3] for row in df if len(row) >= 4}

        # Update the selection status in the conversation state
        for tc in self.conversation_state.pending_tool_calls:
            if tc.tool_call_id in selection_map:
                tc.selected = selection_map[tc.tool_call_id]


# Create a global tool call popup for use in the UI
tool_call_popup = ToolCallPopup()


def create_tool_call_popup() -> Tuple[gr.Group, gr.Dataframe, gr.Button, gr.Button, gr.Button]:
    """Create the tool call popup component.

    Returns:
        A tuple of (popup, tool_calls_list, permit_btn, permit_all_btn, cancel_btn).
    """
    return tool_call_popup.create_popup()


def prepare_tool_calls(tool_calls_data: Optional[List[Dict[str, Any]]]) -> Tuple[List[List[Any]], List[str]]:
    """Prepare tool calls for display.

    Args:
        tool_calls_data: The tool calls data.

    Returns:
        A tuple of (tool_calls_list, tool_call_ids).
    """
    if not tool_calls_data:
        return [], []

    # Update the conversation state with the tool calls
    tool_call_popup.conversation_state.clear_pending_tool_calls()
    for tc_data in tool_calls_data:
        tool_call = ToolCall(
            tool_name=tc_data["tool_name"],
            args=tc_data["args"],
            tool_call_id=tc_data["tool_call_id"],
            status=ToolCallStatus.PENDING,
            selected=True,
        )
        tool_call_popup.conversation_state.add_tool_call(tool_call)

    # Prepare the tool calls for display
    return tool_call_popup.prepare_tool_calls()


def get_selected_tool_calls(df: List[List[Any]], tool_calls_state: List[Dict[str, Any]]) -> List[str]:
    """Get selected tool call IDs from the dataframe.

    Args:
        df: The dataframe.
        tool_calls_state: The tool calls state.

    Returns:
        The selected tool call IDs.
    """
    selected_ids = []

    # First try to get selected IDs from the dataframe
    for row in df:
        if len(row) >= 4 and row[3]:  # If selected
            selected_ids.append(row[0])  # Add the ID

    # If that didn't work, try to get them from the tool calls state
    if not selected_ids and tool_calls_state:
        selected_ids = [tc["tool_call_id"] for tc in tool_calls_state if tc.get("selected", True)]

    return selected_ids
