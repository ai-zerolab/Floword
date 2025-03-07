"""Conversation models for the Floword UI."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field
from pydantic_ai.messages import ToolReturnPart


class MessageRole(str, Enum):
    """Message role enum."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ToolCallStatus(str, Enum):
    """Tool call status enum."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class ToolCall(BaseModel):
    """Tool call model."""

    tool_name: str
    args: str
    tool_call_id: str
    status: ToolCallStatus = ToolCallStatus.PENDING
    selected: bool = True  # For UI selection
    result: Any = None


class Message(BaseModel):
    """Chat message model."""

    role: MessageRole
    content: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)
    tool_calls: List[ToolCall] = Field(default_factory=list)


class ConversationState(BaseModel):
    """Conversation state model."""

    conversation_id: Optional[str] = None
    title: str = "Untitled"
    messages: List[Message] = Field(default_factory=list)
    pending_tool_calls: List[ToolCall] = Field(default_factory=list)
    always_permit_tools: bool = False
    is_loading: bool = False
    error: Optional[str] = None

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation.

        Args:
            content: The message content.
        """
        self.messages.append(
            Message(
                role=MessageRole.USER,
                content=content,
            )
        )

    def add_assistant_message(self, content: str = "", tool_calls: List[ToolCall] = None) -> None:
        """Add an assistant message to the conversation.

        Args:
            content: The message content.
        """
        self.messages.append(Message(role=MessageRole.ASSISTANT, content=content, tool_calls=tool_calls or []))

    def update_last_assistant_message(self, content: str) -> None:
        """Update the last assistant message in the conversation.

        Args:
            content: The new message content.
        """
        for i in range(len(self.messages) - 1, -1, -1):
            if self.messages[i].role == MessageRole.ASSISTANT:
                self.messages[i].content = content
                return

        # If no assistant message found, add a new one
        self.add_assistant_message(content)

    def add_tool_call(self, tool_call: ToolCall) -> None:
        """Add a tool call to the conversation.

        Args:
            tool_call: The tool call to add.
        """
        self.pending_tool_calls.append(tool_call)

        # Also add to the last assistant message's tool calls
        if self.messages and self.messages[-1].role == MessageRole.ASSISTANT:
            self.messages[-1].tool_calls.append(tool_call)

    def add_tool_return(self, tool_return: ToolReturnPart) -> None:
        """Add a tool return to the conversation.

        Args:
            tool_return: The tool return to add.
        """
        # Update the last assistant message's tool calls
        if self.messages and self.messages[-1].role == MessageRole.ASSISTANT:
            for tc in self.messages[-1].tool_calls:
                if tc.tool_call_id == tool_return.tool_call_id:
                    tc.status = ToolCallStatus.COMPLETED
                    tc.result = tool_return.content

    def clear_pending_tool_calls(self) -> None:
        """Clear pending tool calls."""
        self.pending_tool_calls = []

    def to_gradio_history(self) -> List[Dict[str, Any]]:
        """Convert the conversation to Gradio chatbot history format.

        Returns:
            The conversation history in Gradio format.
        """
        history = []
        for msg in self.messages:
            if msg.role in [MessageRole.USER, MessageRole.ASSISTANT]:
                message_dict = {"role": msg.role.value, "content": msg.content}
                history.append(message_dict)

                # Add metadata for tool calls
                if msg.tool_calls and msg.role == MessageRole.ASSISTANT:
                    message_dict = {"role": msg.role.value, "content": ""}
                    for tc in msg.tool_calls:
                        message_dict["metadata"] = {
                            "title": f"🛠️ {'Requesting' if not tc.result else 'Done'} tool call: {tc.tool_name} Arguments: {tc.args}",
                            "log": tc.model_dump_json(),
                            "is_tool_call": True,  # Add this flag
                        }

                        history.append(message_dict)
        return history

    def from_api_messages(self, messages: List[Dict[str, Any]]) -> None:
        """Update the conversation from API messages.

        Args:
            messages: The messages from the API.
        """
        self.messages = []

        for msg in messages:
            # Handle the new API format
            if "parts" in msg and "kind" in msg:
                parts = msg.get("parts", [])
                kind = msg.get("kind", "")

                for part in parts:
                    part_kind = part.get("part_kind", "")
                    content = part.get("content", "")

                    if part_kind == "user-prompt":
                        self.add_user_message(content)
                    elif part_kind == "system-prompt":
                        self.messages.append(
                            Message(
                                role=MessageRole.SYSTEM,
                                content=content,
                            )
                        )
                    elif part_kind == "text" and kind == "response":
                        self.add_assistant_message(content)
                    elif part_kind == "tool-call":
                        # Process tool calls
                        tool_name = part.get("tool_name", "")
                        args = part.get("args", "")
                        tool_call_id = part.get("tool_call_id", "")

                        if tool_name and tool_call_id:
                            tool_call = ToolCall(
                                tool_name=tool_name,
                                args=args,
                                tool_call_id=tool_call_id,
                                status=ToolCallStatus.COMPLETED,  # It's completed since it's from history
                            )

                            # Add to the last assistant message
                            if self.messages and self.messages[-1].role == MessageRole.ASSISTANT:
                                self.messages[-1].tool_calls.append(tool_call)
                    elif part_kind == "tool-return":
                        tool_call_id = part.get("tool_call_id", "")
                        content = part.get("content", "")

                        if tool_call_id:
                            for tc in self.messages[-1].tool_calls:
                                if tc.tool_call_id == tool_call_id:
                                    tc.status = ToolCallStatus.COMPLETED
                                    tc.result = content

            # Handle the old API format for backward compatibility
            else:
                role = msg.get("role", "")
                content = msg.get("content", "")

                if role == "user":
                    self.add_user_message(content)
                elif role == "assistant":
                    self.add_assistant_message(content)
                elif role == "system":
                    self.messages.append(
                        Message(
                            role=MessageRole.SYSTEM,
                            content=content,
                        )
                    )
