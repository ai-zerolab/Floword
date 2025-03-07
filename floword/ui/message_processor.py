"""Message processor for the Floword UI."""

import json
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic_ai.messages import ToolReturnPart

from floword.ui.models.conversation import ConversationState, Message, MessageRole, ToolCall, ToolCallStatus
from floword.log import logger


class MessageProcessor:
    """Processor for chat messages and SSE events."""

    def __init__(self, conversation_state: Optional[ConversationState] = None):
        """Initialize the message processor.

        Args:
            conversation_state: Optional conversation state to use.
        """
        self.conversation_state = conversation_state or ConversationState()
        self.current_message_parts: Dict[int, Dict[str, Any]] = {}
        self.current_tool_calls: Dict[str, ToolCall] = {}

    def process_event(self, event: Dict[str, Any]) -> Tuple[bool, bool]:
        """Process an SSE event and update the conversation state.

        Args:
            event: The SSE event to process.

        Returns:
            A tuple of (message_updated, tool_calls_updated).
        """
        logger.debug(f"processing event {event}")
        data = event

        message_updated = False
        tool_calls_updated = False
        # Handle request events (user messages)
        if "kind" in data and data["kind"] == "request":
            # This is a user message, we don't need to process it
            tool_call_responsed = False
            for part in data["parts"]:
                if part["part_kind"] == "tool-return":
                    part = ToolReturnPart(**part)
                    self.conversation_state.add_tool_return(part)
                    tool_call_responsed = True
            if tool_call_responsed:
                self._update_conversation_from_parts()
                self.conversation_state.add_assistant_message()
            return True, tool_call_responsed

        # Handle streaming events
        if "event_kind" in data:
            event_kind = data["event_kind"]

            if event_kind == "part_start":
                index = data["index"]
                part = data["part"]
                part_kind = part["part_kind"]

                if part_kind == "text":
                    self.current_message_parts[index] = {
                        "role": "assistant",
                        "content": part["content"],
                    }
                    # Update the conversation state immediately
                    self._update_conversation_from_parts()
                    message_updated = True

                elif part_kind == "tool-call":
                    tool_call = ToolCall(
                        tool_name=part["tool_name"],
                        args=part["args"],
                        tool_call_id=part["tool_call_id"],
                        status=ToolCallStatus.PENDING,
                    )
                    self.current_tool_calls[tool_call.tool_call_id] = tool_call
                    self.conversation_state.add_tool_call(tool_call)
                    tool_calls_updated = True

            elif event_kind == "part_delta":
                index = data["index"]
                delta = data["delta"]
                delta_kind = delta["part_delta_kind"]

                if delta_kind == "text" and "content_delta" in delta:
                    if index not in self.current_message_parts:
                        self.current_message_parts[index] = {
                            "role": "assistant",
                            "content": "",
                        }
                    self.current_message_parts[index]["content"] += delta["content_delta"]
                    # Update the conversation state immediately
                    self._update_conversation_from_parts()
                    message_updated = True

                elif delta_kind == "tool_call" and "args_delta" in delta and delta["args_delta"]:
                    tool_call_id = delta["tool_call_id"]
                    if tool_call_id in self.current_tool_calls:
                        tool_call = self.current_tool_calls[tool_call_id]
                        tool_call.args += delta["args_delta"]
                        tool_calls_updated = True

        return message_updated, tool_calls_updated

    def _update_conversation_from_parts(self) -> None:
        """Update the conversation state from all current message parts."""
        if not self.current_message_parts:
            return

        # Combine all text parts if there are multiple
        combined_content = ""
        for index in sorted(self.current_message_parts.keys()):
            part = self.current_message_parts[index]
            if part["role"] == "assistant":
                combined_content += part["content"]
        # Update the conversation state
        if combined_content:
            # Check if we already have an assistant message
            if self.conversation_state.messages and self.conversation_state.messages[-1].role == MessageRole.ASSISTANT:
                # Update the existing message
                self.conversation_state.messages[-1].content = combined_content
            else:
                # Add a new message
                self.conversation_state.add_assistant_message(combined_content)

    def get_tool_calls(self) -> List[ToolCall]:
        """Get the current tool calls.

        Returns:
            The current tool calls.
        """
        return list(self.current_tool_calls.values())

    def clear(self) -> None:
        """Clear the processor state."""
        self.current_message_parts = {}
        self.current_tool_calls = {}

    def get_final_message(self) -> Optional[str]:
        """Get the final message content.

        Returns:
            The final message content, or None if there is no message.
        """
        if not self.current_message_parts:
            return None

        # Combine all text parts if there are multiple
        combined_content = ""
        for index in sorted(self.current_message_parts.keys()):
            part = self.current_message_parts[index]
            if part["role"] == "assistant":
                combined_content += part["content"]

        return combined_content if combined_content else None
