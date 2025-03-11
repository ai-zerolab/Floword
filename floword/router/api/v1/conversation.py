import asyncio

from fastapi import APIRouter, Depends, HTTPException, Response, status

from floword.router.api.params import (
    ChatRequest,
    ConversionInfo,
    ConversionInfoResponse,
    NewConversation,
    PermitCallToolRequest,
    QueryConversations,
    RetryRequest,
)
from floword.router.controller.conversation import (
    ConversationController,
    get_conversation_controller,
)
from floword.router.streamer import (
    PersistentEventSourceResponse,
    PersistentStreamer,
    process_stream,
)
from floword.users import User, get_current_user

router = APIRouter(
    tags=["conversation"],
    prefix="/api/v1/conversation",
)


@router.post("/generate-title/{conversation_id}")
async def generate_title(
    conversation_id: str,
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
) -> ConversionInfo:
    # TODO: Update conversation and auto gen title from messages
    raise NotImplementedError


@router.post("/update/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
) -> ConversionInfo:
    # TODO: Update conversation and auto gen title from messages
    raise NotImplementedError


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
) -> ConversionInfoResponse:
    """
    If stream is in progress, return is_streaming=True
    Client can use resume endpoint to continue the stream.

    If resume endpoint response is empty, it means stream is completed,
    client needs to refetch the info,
    """

    streamer = PersistentStreamer.get_instance()
    stream_id = get_conversation_stream_id(conversation_id, user.user_id)
    info = await conversation_controller.get_conversation_info(user, conversation_id)
    return ConversionInfoResponse.from_info(info, await streamer.has_stream(stream_id))


def get_conversation_stream_id(conversation_id: str, user_id: str) -> str:
    """Get a consistent stream ID for a conversation."""
    return f"conversation_{conversation_id}_{user_id}"


@router.post("/chat/{conversation_id}")
async def chat(
    conversation_id: str,
    params: ChatRequest,
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
) -> PersistentEventSourceResponse:
    """
    SSE, first data part is ModelRequest for prompt.

    Then each data part is ModelResponseStreamEvent. Client need to handle it.
    """
    streamer = PersistentStreamer.get_instance()
    stream_id = get_conversation_stream_id(conversation_id, user.user_id)

    if await streamer.has_stream(stream_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A stream is already in progress for this conversation",
        )

    # Create a new stream and start processing in the background
    stream_data = await streamer.create_stream(stream_id)
    # Start background task to process the stream
    asyncio.create_task(process_stream(conversation_controller.chat(user, conversation_id, params), stream_data))  # noqa: RUF006

    # Create and initialize the response
    response = PersistentEventSourceResponse(
        streamer=streamer,
        stream_id=stream_id,
        stream_data=stream_data,
        ping=True,
    )
    return response


@router.post("/permit-call-tool/{conversation_id}")
async def run(
    conversation_id: str,
    params: PermitCallToolRequest,
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
) -> PersistentEventSourceResponse:
    """
    SSE, first data part is ModelRequest for tool.

    Then each data part is ModelResponseStreamEvent. Client need to handle it.
    """
    streamer = PersistentStreamer.get_instance()
    stream_id = get_conversation_stream_id(conversation_id, user.user_id)

    if await streamer.has_stream(stream_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A stream is already in progress for this conversation",
        )

    # Create a new stream and start processing in the background
    stream_data = await streamer.create_stream(stream_id)
    # Start background task to process the stream
    asyncio.create_task(  # noqa: RUF006
        process_stream(
            conversation_controller.permit_call_tool(user, conversation_id, params),
            stream_data,
        )
    )

    # Create and initialize the response
    response = PersistentEventSourceResponse(
        streamer=streamer,
        stream_id=stream_id,
        stream_data=stream_data,
        ping=True,
    )
    return response


@router.post("/retry/{conversation_id}")
async def retry_conversation(
    conversation_id: str,
    params: RetryRequest,
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
) -> PersistentEventSourceResponse:
    streamer = PersistentStreamer.get_instance()
    stream_id = get_conversation_stream_id(conversation_id, user.user_id)

    if await streamer.has_stream(stream_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A stream is already in progress for this conversation",
        )

    # Create a new stream and start processing in the background
    stream_data = await streamer.create_stream(stream_id)
    # Start background task to process the stream
    asyncio.create_task(  # noqa: RUF006
        process_stream(
            conversation_controller.retry_conversation(user, conversation_id, params),
            stream_data,
        )
    )

    # Create and initialize the response
    response = PersistentEventSourceResponse(
        streamer=streamer,
        stream_id=stream_id,
        stream_data=stream_data,
        ping=True,
    )
    return response


@router.post("/resume/{conversation_id}")
async def resume_stream(
    conversation_id: str,
    user: User = Depends(get_current_user),
) -> PersistentEventSourceResponse:
    """
    Resume a stream that was previously started.
    This allows clients to reconnect and get all events that were streamed while they were disconnected.
    """
    streamer = PersistentStreamer.get_instance()
    stream_id = get_conversation_stream_id(conversation_id, user.user_id)

    if not await streamer.has_stream(stream_id):
        # If the stream doesn't exist, return an empty response
        # This could happen if the stream was completed and deleted
        # or if the stream was never created
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    stream_data = await streamer.get_stream(stream_id)
    # Create and initialize the response
    response = PersistentEventSourceResponse(
        streamer=streamer,
        stream_id=stream_id,
        start_index=0,
        stream_data=stream_data,
        ping=True,
    )
    return response


@router.post("/delete/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    conversation_controller: ConversationController = Depends(get_conversation_controller),
) -> Response:
    await conversation_controller.delete_conversation(user, conversation_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
