from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from floword.router.api.params import (
    ChatRequest,
    ConversionInfo,
    NewConversation,
    PermitCallToolRequest,
    QueryConversations,
)
from floword.router.controller.conversation import (
    ConversationController,
    get_conversation_controller,
)
from floword.users import User, get_current_user

router = APIRouter(
    tags=["conversation"],
    prefix="/api/v1/conversation",
)


@router.post("/create")
async def create_conversation(
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
) -> NewConversation:
    return await conversation_controller.create_conversation(user)


@router.get("/list")
async def get_conversations(
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
    limit: int = 100,
    offset: int = 0,
    order_by: str = "created_at",
    order: str = "desc",
) -> QueryConversations:
    if order not in ["asc", "desc"]:
        raise ValueError("Order must be 'asc' or 'desc'")

    if order_by not in ["created_at", "updated_at"]:
        raise ValueError("Order by must be 'created_at' or 'updated_at'")

    return await conversation_controller.get_conversations(user, limit, offset, order_by, order)


@router.get("/info/{conversation_id}")
async def get_conversation_info(
    conversation_id: str,
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
) -> ConversionInfo:
    return await conversation_controller.get_conversation_info(user, conversation_id)


@router.post("/chat")
async def chat(
    params: ChatRequest,
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
) -> EventSourceResponse:
    pass


@router.post("/permit-call-tool")
async def run(
    params: PermitCallToolRequest,
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
) -> EventSourceResponse:
    pass
