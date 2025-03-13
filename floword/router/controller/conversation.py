from __future__ import annotations

import dataclasses
import json
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, get_args

from fastapi import Depends, HTTPException, status
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponsePart,
    ModelResponseStreamEvent,
    ToolCallPart,
)
from pydantic_ai.models import Model
from pydantic_ai.usage import Usage
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from floword.config import Config, get_config
from floword.dbutils import get_db_session, open_db_session
from floword.llms.mcp_agent import ConversationError, MCPAgent
from floword.llms.models import ModelInitParams, get_default_model, init_model
from floword.log import logger
from floword.mcp.manager import MCPManager, get_mcp_manager
from floword.orm import Conversation
from floword.router.api.params import (
    ChatRequest,
    ConversionInfo,
    NewConversation,
    PermitCallToolRequest,
    QueryConversations,
    RedactableCompletion,
    RetryRequest,
)
from floword.users import User


class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def dataclass_to_dict(obj: Any) -> dict:
    """
    Convert a dataclass instance to a dictionary, handling nested dataclasses and datetime objects.
    """
    if dataclasses.is_dataclass(obj):
        result = {}
        for field in dataclasses.fields(obj):
            value = getattr(obj, field.name)
            if dataclasses.is_dataclass(value):
                result[field.name] = dataclass_to_dict(value)
            elif isinstance(value, list):
                result[field.name] = [
                    dataclass_to_dict(item) if dataclasses.is_dataclass(item) else item for item in value
                ]
            elif isinstance(value, dict):
                result[field.name] = {
                    k: dataclass_to_dict(v) if dataclasses.is_dataclass(v) else v for k, v in value.items()
                }
            elif isinstance(value, datetime):
                result[field.name] = value.isoformat()
            else:
                result[field.name] = value
        return result
    return obj


def _to_one_model_message(message: dict, concrete_types: type[ModelMessage]) -> ModelMessage:
    for t in concrete_types:
        if message.get("kind") != t.kind:
            continue
        message["parts"] = _to_parts(message["parts"])
        return t(**message)
    raise ValueError(f"Unknown message: {message}")


def _to_parts(parts: list[dict | None]) -> list[ModelResponsePart | ModelRequestPart]:
    if parts is None:
        return None

    concrete_types = [
        *get_args(get_args(ModelRequestPart)[0]),
        *get_args(get_args(ModelResponsePart)[0]),
    ]
    return [_to_one_part(part, concrete_types) for part in parts]


def _to_one_part(part: dict | None, concrete_types: list[type[ModelRequestPart | ModelResponsePart]]):
    if part is None:
        return None

    for t in concrete_types:
        if part.get("part_kind") != t.part_kind:
            continue
        return t(**part)
    raise ValueError(f"Unknown part: {part}")


def to_model_messages(messages: list[dict | None]) -> list[ModelMessage]:
    if messages is None:
        return None

    concrete_types = list(get_args(get_args(ModelMessage)[0]))
    return [_to_one_model_message(message, concrete_types) for message in messages]


def get_conversation_controller(
    session: AsyncSession = Depends(get_db_session),
    config: Config = Depends(get_config),
    mcp_manager: MCPManager = Depends(get_mcp_manager),
    default_model=Depends(get_default_model),
) -> ConversationController:
    return ConversationController(session, config, mcp_manager, default_model)


class ConversationController:
    def __init__(
        self,
        session: AsyncSession,
        config: Config,
        mcp_manager: MCPManager,
        default_model: Model | None,
    ) -> None:
        self.session = session
        self.config = config
        self.mcp_manager = mcp_manager

        self.default_model = default_model

    @property
    def default_system_prompt(self) -> str | None:
        return self.config.default_conversation_system_prompt

    def get_model(self, params: RedactableCompletion) -> Model:
        model = (
            init_model(
                ModelInitParams(
                    provider=params.llm_config.provider or self.config.default_model_provider,
                    model_name=params.llm_config.model_name or self.config.default_model_name,
                    model_kwargs=params.llm_config.model_kwargs or json.loads(self.config.default_model_kwargs or "{}"),
                )
            )
            if params.llm_config
            else self.default_model
        )

        if not model:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Can not find model, please specify llm_config or set default_model",
            )
        return model

    async def create_conversation(self, user: User) -> NewConversation:
        c = Conversation(
            user_id=user.user_id,
        )
        self.session.add(c)
        await self.session.commit()
        await self.session.refresh(c)
        return NewConversation(conversation_id=c.conversation_id)

    async def get_conversations(
        self, user: User, limit: int, offset: int, order_by: str, order: str
    ) -> QueryConversations:
        statements = select(Conversation).where(Conversation.user_id == user.user_id)
        if order not in ["asc", "desc"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order must be 'asc' or 'desc'",
            )
        if order_by not in ["created_at", "updated_at"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order by must be 'created_at' or 'updated_at'",
            )

        if order_by == "created_at":
            statements = statements.order_by(
                Conversation.created_at if order == "asc" else Conversation.created_at.desc()
            )
        elif order_by == "updated_at":
            statements = statements.order_by(
                Conversation.updated_at if order == "asc" else Conversation.updated_at.desc()
            )

        result = await self.session.execute(statements.limit(limit).offset(offset))
        conversations = result.scalars().all()

        return QueryConversations(
            datas=[
                ConversionInfo(
                    conversation_id=c.conversation_id,
                    title=c.title,
                    messages=None,
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                    usage=c.usage or Usage(),
                )
                for c in conversations
            ],
            limit=limit,
            offset=offset,
            has_more=len(conversations) == limit,
        )

    async def get_conversation_info(self, user: User, conversation_id: str) -> ConversionInfo:
        result = await self.session.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))
        conversation = result.scalars().one_or_none()
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        if conversation.user_id != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return ConversionInfo(
            conversation_id=conversation.conversation_id,
            title=conversation.title,
            messages=conversation.messages or [],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            usage=conversation.usage or Usage(),
        )

    async def _update_conversation(self, conversation_id: str, messages: list[ModelMessage], usage: Usage):
        # Convert dataclasses to dictionaries
        messages_dict = [dataclass_to_dict(message) for message in messages]
        usage_dict = dataclass_to_dict(usage)

        # Use a new session for this update to avoid transaction state conflicts during streaming
        async with open_db_session(self.config) as session:
            await session.execute(
                update(Conversation)
                .where(Conversation.conversation_id == conversation_id)
                .values(messages=messages_dict, usage=usage_dict)
            )
            # Session will be committed in the context manager

    async def chat(
        self, user: User, conversation_id: str, params: ChatRequest
    ) -> AsyncIterator[ModelResponseStreamEvent | ModelRequest]:
        result = await self.session.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))
        conversation = result.scalars().one_or_none()
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        if conversation.user_id != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        agent = MCPAgent(
            model=self.get_model(params),
            mcp_manager=self.mcp_manager,
            system_prompt=params.system_prompt or self.default_system_prompt,
            last_conversation=params.redacted_messages or to_model_messages(conversation.messages),
            usage=Usage(**(conversation.usage or {})),
        )
        try:
            async for part in agent.chat_stream(
                params.prompt,
                model_settings=params.llm_model_settings,
            ):
                yield {"data": json.dumps(dataclass_to_dict(part))}
                await self._update_conversation(conversation_id, agent.all_messages(), agent.usage())
            index_bias = 0
            while params.auto_permit and any(isinstance(p, ToolCallPart) for p in agent.last_response().parts):
                logger.info("Auto-permiting tool calls...")
                async for part in agent.run_tool_stream(
                    model_settings=params.llm_model_settings,
                    execute_all_tool_calls=True,
                ):
                    if not isinstance(part, ModelRequest):
                        part.index += index_bias
                    yield {"data": json.dumps(dataclass_to_dict(part))}
                await self._update_conversation(conversation_id, agent.all_messages(), agent.usage())
        except ConversationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

        await self._update_conversation(conversation_id, agent.all_messages(), agent.usage())

    async def retry_conversation(
        self, user: User, conversation_id: str, params: RetryRequest
    ) -> AsyncIterator[ModelResponseStreamEvent | ModelRequest]:
        result = await self.session.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))
        conversation = result.scalars().one_or_none()
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        if conversation.user_id != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        agent = MCPAgent(
            model=self.get_model(params),
            mcp_manager=self.mcp_manager,
            system_prompt=self.default_system_prompt,
            last_conversation=params.redacted_messages or to_model_messages(conversation.messages),
            usage=Usage(**(conversation.usage or {})),
        )

        try:
            async for part in agent.retry_stream(model_settings=params.llm_model_settings):
                yield {"data": json.dumps(dataclass_to_dict(part))}
        except ConversationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

        await self._update_conversation(conversation_id, agent.all_messages(), agent.usage())

    async def permit_call_tool(
        self,
        user: User,
        conversation_id: str,
        params: PermitCallToolRequest,
        agent: MCPAgent | None = None,
    ) -> AsyncIterator[ModelResponseStreamEvent | ModelRequest]:
        result = await self.session.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))
        conversation = result.scalars().one_or_none()
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        if conversation.user_id != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        agent = agent or MCPAgent(
            model=self.get_model(params),
            mcp_manager=self.mcp_manager,
            system_prompt=self.default_system_prompt,
            last_conversation=params.redacted_messages or to_model_messages(conversation.messages),
            usage=Usage(**(conversation.usage or {})),
        )

        try:
            async for part in agent.run_tool_stream(
                model_settings=params.llm_model_settings,
                execute_all_tool_calls=params.execute_all_tool_calls,
                execute_tool_call_ids=params.execute_tool_call_ids,
                execute_tool_call_part=params.execute_tool_call_part,
            ):
                yield {"data": json.dumps(dataclass_to_dict(part))}
        except ConversationError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
        await self._update_conversation(conversation_id, agent.all_messages(), agent.usage())

    async def delete_conversation(self, user: User, conversation_id: str) -> None:
        result = await self.session.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))
        conversation = result.scalars().one_or_none()
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        if conversation.user_id != user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

        await self.session.execute(delete(Conversation).where(Conversation.conversation_id == conversation_id))
        await self.session.commit()
        return
