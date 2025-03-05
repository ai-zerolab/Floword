from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from floword.dbutils import get_db_session
from floword.orm import Conversation
from floword.router.api.params import NewConversation
from floword.users import User


def get_conversation_controller(
    session: AsyncSession = Depends(get_db_session),
) -> ConversationController:
    return ConversationController(session)


class ConversationController:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_conversation(self, user: User) -> NewConversation:
        c = Conversation(
            user_id=user.user_id,
        )
        self.session.add(c)
        await self.session.commit()
        await self.session.refresh(c)
        return NewConversation(conversation_id=c.conversation_id)
