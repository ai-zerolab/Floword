"""Conversation models for the Floword UI."""

from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Tool call model."""

    tool_name: str
    args: str
    tool_call_id: str


class ConversationState(BaseModel):
    """Conversation state model."""

    conversation_id: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    pending_tool_calls: list[ToolCall] = Field(default_factory=list)
    always_permit_tools: bool = False
