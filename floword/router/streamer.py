from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Generic, TypeVar

from sse_starlette.sse import EventSourceResponse
from starlette.types import Receive, Scope, Send

from floword.log import logger

T = TypeVar("T")


class StreamData(Generic[T]):
    """
    Stores stream data and provides methods to access it.
    """

    def __init__(self, max_size: int = 1000):
        self.events: deque[T] = deque(maxlen=max_size)
        self.completed: bool = False
        self.created_at: datetime = datetime.now()
        self._event_added = asyncio.Event()

    def add_event(self, event: T) -> None:
        """Add an event to the stream."""
        self.events.append(event)
        self._event_added.set()
        self._event_added = asyncio.Event()

    def get_events(self) -> list[T]:
        """Get all events in the stream."""
        return list(self.events)

    def is_completed(self) -> bool:
        """Check if the stream is completed."""
        return self.completed

    def mark_completed(self) -> None:
        """Mark the stream as completed."""
        self.completed = True
        self._event_added.set()  # Wake up any waiting consumers

    async def stream_events(self, start_index: int = 0) -> AsyncIterator[T]:
        """
        Stream events starting from the given index.
        Waits for new events if we've yielded all current events and the stream is not completed.
        """
        current_index = start_index

        while True:
            # Yield any available events
            while current_index < len(self.events):
                yield self.events[current_index]
                current_index += 1

            # If the stream is completed and we've yielded all events, we're done
            if self.completed:
                break

            # Wait for new events
            await self._event_added.wait()


class PersistentStreamer:
    """
    Singleton class that manages persistent streams.
    """

    _instance: PersistentStreamer | None = None

    @classmethod
    def get_instance(cls) -> PersistentStreamer:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = PersistentStreamer()
        return cls._instance

    def __init__(self):
        self.streams: dict[str, StreamData] = {}

    def create_stream(self, stream_id: str) -> StreamData:
        """Create a new stream with the given ID."""
        if stream_id in self.streams:
            raise ValueError(f"Stream with ID {stream_id} already exists")

        self.streams[stream_id] = StreamData()
        return self.streams[stream_id]

    def get_stream(self, stream_id: str) -> StreamData:
        """Get a stream by ID."""
        if stream_id not in self.streams:
            raise ValueError(f"Stream with ID {stream_id} not found")

        return self.streams[stream_id]

    def delete_stream(self, stream_id: str) -> None:
        """Delete a stream by ID."""
        if stream_id in self.streams:
            del self.streams[stream_id]

    def has_stream(self, stream_id: str) -> bool:
        """Check if a stream with the given ID exists."""
        return stream_id in self.streams


class PersistentEventSourceResponse(EventSourceResponse):
    """
    An EventSourceResponse that uses a persistent stream.
    """

    def __init__(
        self,
        streamer: PersistentStreamer,
        stream_id: str,
        start_index: int = 0,
        status_code: int = 200,
        ping: bool = False,
        ping_message_factory=None,
        **kwargs,
    ):
        self.streamer = streamer
        self.stream_id = stream_id
        self.start_index = start_index

        try:
            stream_data = streamer.get_stream(stream_id)
        except ValueError:
            stream_data = streamer.create_stream(stream_id)

        # Create an async generator that yields events from the stream
        async def event_generator():
            try:
                async for event in stream_data.stream_events(start_index):
                    yield event
            except Exception as e:
                logger.exception(f"Error streaming events for {stream_id}: {e}")

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
                stream_data = self.streamer.get_stream(self.stream_id)
                if stream_data.is_completed():
                    self.streamer.delete_stream(self.stream_id)
            except ValueError:
                pass  # Stream was already deleted


async def process_stream(source_iterator: AsyncIterator[Any], stream_data: StreamData) -> None:
    """
    Process a source iterator and add events to a stream.
    This function should be called as a background task.
    """
    try:
        async for event in source_iterator:
            stream_data.add_event(event)
    except Exception as e:
        logger.exception(f"Error processing stream: {e}")
    finally:
        stream_data.mark_completed()
