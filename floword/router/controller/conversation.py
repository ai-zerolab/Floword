from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status
from pydantic_ai.messages import ModelResponseStreamEvent
from pydantic_ai.models import Model
from pydantic_ai.usage import Usage
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from floword.config import Config, get_config
from floword.dbutils import get_db_session
from floword.llms.mcp_agent import MCPAgent
from floword.llms.models import ModelInitParams, get_default_model, init_model
from floword.mcp.manager import MCPManager, get_mcp_manager
from floword.orm import Conversation
from floword.router.api.params import (
    ChatRequest,
    ConversionInfo,
    NewConversation,
    PermitCallToolRequest,
    QueryConversations,
    RedactableCompletion,
)
from floword.users import User


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
                    model_kwargs=params.llm_config.model_kwargs or self.config.default_model_kwargs,
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

    async def chat(
        self, user: User, conversation_id: str, params: ChatRequest
    ) -> AsyncIterator[ModelResponseStreamEvent]:
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
            last_conversation=params.redacted_messages or conversation.messages,
            usage=conversation.usage or Usage(),
        )

        async for part in agent.chat_stream(params.prompt):
            yield part

        await self.session.execute(
            update(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .values(
                messages=agent.all_messages(),
                usage=agent.usage(),
            )
        )
        await self.session.commit()
        return

    async def permit_call_tool(
        self, user: User, conversation_id: str, params: PermitCallToolRequest
    ) -> AsyncIterator[ModelResponseStreamEvent]:
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
            last_conversation=params.redacted_messages or conversation.messages,
            usage=conversation.usage or Usage(),
        )

        async for part in agent.run_tool_stream(params.prompt):
            yield part

        await self.session.execute(
            update(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .values(
                messages=agent.all_messages(),
                usage=agent.usage(),
            )
        )
        await self.session.commit()
        return

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
