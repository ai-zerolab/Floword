from __future__ import annotations

from datetime import datetime, timezone

from mcp import Tool
from pydantic import BaseModel, Field
from pydantic_ai.messages import ModelMessage, ToolCallPart
from pydantic_ai.usage import Usage

from floword.llms.models import ModelInitParams
from floword.mcp.manager import ServerName


class GetModelsResponse(BaseModel):
    providers: list[str]
    models: dict[str, list[str]]


class GetMcpServersResponse(BaseModel):
    activate_servers: dict[ServerName, list[Tool]]
    disabled_servers: list[str]
    failed_servers: dict[str, dict[str, str]]


class NewConversation(BaseModel):
    conversation_id: str


class QueryConversations(BaseModel):
    datas: list[ConversionInfo]
    limit: int
    offset: int
    has_more: bool


class ConversionInfo(BaseModel):
    conversation_id: str
    title: str
    messages: list[ModelMessage] | None = None
    usage: Usage
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConversionInfoResponse(ConversionInfo):
    is_streaming: bool = False

    @classmethod
    def from_info(cls, info: ConversionInfo, is_streaming: bool) -> ConversionInfoResponse:
        return cls(
            conversation_id=info.conversation_id,
            title=info.title,
            messages=info.messages,
            usage=info.usage,
            created_at=info.created_at,
            updated_at=info.updated_at,
            is_streaming=is_streaming,
        )


class RedactableCompletion(BaseModel):
    llm_config: ModelInitParams | None = None
    llm_model_settings: dict | None = None
    redacted_messages: list[ModelMessage] | None = None


class ChatRequest(RedactableCompletion):
    system_prompt: str | None = ""  # Only avaliable when starting a new conversation
    prompt: str
    auto_permit: bool = False


class RetryRequest(RedactableCompletion):
    pass


class PermitCallToolRequest(RedactableCompletion):
    execute_all_tool_calls: bool = False
    execute_tool_call_ids: list[str] | None = None
    execute_tool_call_part: list[ToolCallPart] | None = None
