from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sse_starlette import EventSourceResponse
from starlette.types import Receive, Scope, Send

from floword.config import get_config
from floword.log import logger

c = get_config()
if c.redis_url:
    from floword.router.streamer.redis import PersistentStreamer, StreamData
else:
    from floword.router.streamer.memory import (
        PersistentStreamer,
        StreamData,
    )


async def process_stream(source_iterator: AsyncIterator[Any], stream_data: StreamData) -> None:
    """
    Process a source iterator and add events to a stream.
    This function should be called as a background task.
    """
    try:
        async for event in source_iterator:
            await stream_data.add_event(event)
    except Exception as e:
        logger.exception(f"Error processing stream: {e}")
    finally:
        await stream_data.mark_completed()
        logger.info("Stream completed")


class PersistentEventSourceResponse(EventSourceResponse):
    """
    An EventSourceResponse that uses a persistent stream.
    """

    _cleanup_task = None

    def __init__(
        self,
        streamer: PersistentStreamer,
        stream_id: str,
        stream_data: StreamData,
        start_index: int = 0,
        status_code: int = 200,
        ping: bool = False,
        ping_message_factory=None,
        **kwargs,
    ):
        self.streamer = streamer
        self.stream_id = stream_id
        self.stream_data = stream_data
        self.start_index = start_index
        self.status_code = status_code
        self.ping = ping
        self.ping_message_factory = ping_message_factory
        self.kwargs = kwargs

        async def event_generator():
            try:
                async for event in self.stream_data.stream_events(self.start_index):
                    yield event
            except Exception as e:
                logger.exception(f"Error streaming events for {self.stream_id}: {e}")

        super().__init__(
            content=event_generator(),
            status_code=status_code,
            ping=ping,
            ping_message_factory=ping_message_factory,
            **kwargs,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Override the __call__ method to handle client disconnects.
        """
        # Start a background task to process the stream
        try:
            await super().__call__(scope, receive, send)
        except Exception as e:
            logger.exception(f"Error in PersistentEventSourceResponse: {e}")
        finally:
            # If the stream is completed, we can delete it
            try:
                stream_data = await self.streamer.get_stream(self.stream_id)
                if await stream_data.is_completed():
                    logger.info(f"Cleaning up completed stream: {self.stream_id}")
                    await self.streamer.delete_stream(self.stream_id)
            except ValueError:
                pass  # Stream was already deleted
