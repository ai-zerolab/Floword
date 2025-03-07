"""Message processor for the Floword UI."""

import json
from typing import Any, Dict, List, Optional, Tuple, Union

from floword.ui.models import ToolCall


class MessageProcessor:
    """Processor for chat messages and SSE events."""

    def __init__(self):
        """Initialize the message processor."""
        self.current_message: Dict[int, Dict[str, Any]] = {}
        self.pending_tool_calls: List[ToolCall] = []

    def process_event(self, event: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[List[ToolCall]]]:
        """Process an SSE event and return a complete message if available.

        Args:
            event: The SSE event to process.

        Returns:
            A tuple of (message, tool_calls) where message is a complete message if available,
            and tool_calls is a list of tool calls if available.
        """
        if "data" not in event:
            return None, None

        data = event["data"]

        # Handle ping events
        if "ping" in data:
            return None, None

        # Handle request events (user messages)
        if "kind" in data and data["kind"] == "request":
            # This is a user message, we don't need to process it
            return None, None

        # Handle streaming events
        if "event_kind" in data:
            event_kind = data["event_kind"]

            if event_kind == "part_start":
                index = data["index"]
                part = data["part"]
                part_kind = part["part_kind"]

                if part_kind == "text":
                    self.current_message[index] = {
                        "role": "assistant",
                        "content": part["content"],
                    }
                elif part_kind == "tool-call":
                    tool_call = ToolCall(
                        tool_name=part["tool_name"],
                        args=part["args"],
                        tool_call_id=part["tool_call_id"],
                    )
                    self.pending_tool_calls.append(tool_call)
                    # Return tool calls if we have any
                    if self.pending_tool_calls:
                        return None, self.pending_tool_calls

            elif event_kind == "part_delta":
                index = data["index"]
                delta = data["delta"]
                delta_kind = delta["part_delta_kind"]

                if delta_kind == "text" and "content_delta" in delta:
                    if index not in self.current_message:
                        self.current_message[index] = {
                            "role": "assistant",
                            "content": "",
                        }
                    self.current_message[index]["content"] += delta["content_delta"]

                elif delta_kind == "tool_call" and len(self.pending_tool_calls) > 0:
                    tool_call = self.pending_tool_calls[-1]
                    if "args_delta" in delta and delta["args_delta"]:
                        tool_call.args += delta["args_delta"]
                    # Return tool calls if we have any
                    if self.pending_tool_calls:
                        return None, self.pending_tool_calls

            # Return the current message for the UI to display
            if self.current_message:
                # For simplicity, just return the first message
                for index in sorted(self.current_message.keys()):
                    return self.current_message[index], None

        return None, None

    def get_tool_calls(self) -> List[ToolCall]:
        """Get the pending tool calls.

        Returns:
            The pending tool calls.
        """
        return self.pending_tool_calls

    def clear_tool_calls(self) -> None:
        """Clear the pending tool calls."""
        self.pending_tool_calls = []

    def clear(self) -> None:
        """Clear the processor state."""
        self.current_message = {}
        self.pending_tool_calls = []

    def get_current_message(self) -> Optional[Dict[str, Any]]:
        """Get the current message.

        Returns:
            The current message, or None if there is no current message.
        """
        if not self.current_message:
            return None

        # For simplicity, just return the first message
        for index in sorted(self.current_message.keys()):
            return self.current_message[index]

        return None
