import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    Text,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import declarative_base  # noqa: F811

Base = declarative_base()


class Conversation(Base):
    __tablename__ = "conversations"

    id_ = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Text, nullable=False)
    title = Column(
        Text, nullable=False, default=lambda: f"New Conversation {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    conversation_id = Column(Text, unique=True, index=True, default=lambda: uuid.uuid4().hex, nullable=False)
    messages = Column(JSON, nullable=True)
    usage = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
