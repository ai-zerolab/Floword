from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Generic, TypeVar

from floword.log import logger

T = TypeVar("T")


class StreamData(Generic[T]):
    """
    Stores stream data and provides methods to access it.
    """

    def __init__(self, max_size: int = 1024 * 1024):
        self.events: deque[T] = deque(maxlen=max_size)
        self.completed: bool = False
        self.created_at: datetime = datetime.now()
        self._event_added = asyncio.Event()

    async def add_event(self, event: T) -> None:
        """Add an event to the stream."""
        self.events.append(event)
        self._event_added.set()
        self._event_added = asyncio.Event()

    async def is_completed(self) -> bool:
        """Check if the stream is completed."""
        return self.completed

    async def mark_completed(self) -> None:
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

    async def create_stream(self, stream_id: str) -> StreamData:
        """Create a new stream with the given ID."""
        if stream_id in self.streams:
            raise ValueError(f"Stream with ID {stream_id} already exists")

        self.streams[stream_id] = StreamData()
        return self.streams[stream_id]

    async def get_stream(self, stream_id: str) -> StreamData:
        """Get a stream by ID."""
        if stream_id not in self.streams:
            raise ValueError(f"Stream with ID {stream_id} not found")

        return self.streams[stream_id]

    async def get_streams(self) -> dict[str, StreamData]:
        """Get all streams."""
        return self.streams

    async def delete_stream(self, stream_id: str) -> None:
        """Delete a stream by ID."""
        if stream_id in self.streams:
            del self.streams[stream_id]

    async def has_stream(self, stream_id: str) -> bool:
        """Check if a stream with the given ID exists."""
        return stream_id in self.streams

    @classmethod
    @asynccontextmanager
    async def auto_cleanup(cls, cleanup_interval: int = 1):
        """
        Start a background task that periodically cleans up completed streams.

        Args:
            cleanup_interval: Time in seconds between cleanup runs

        Returns:
            An async context manager that cancels the cleanup task when exiting
        """
        # Create a cancellation event
        cancel_event = asyncio.Event()

        # Define the cleanup task
        async def cleanup_task():
            try:
                while not cancel_event.is_set():
                    # Wait for the specified interval or until cancelled
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(cancel_event.wait(), timeout=cleanup_interval)

                    # If cancelled, exit
                    if cancel_event.is_set():
                        break

                    # Clean up completed streams
                    streamer = cls.get_instance()
                    for stream_id, stream_data in list((await streamer.get_streams()).items()):
                        if await stream_data.is_completed():
                            logger.info(f"Cleaning up completed stream: {stream_id}")
                            await streamer.delete_stream(stream_id)
            except Exception as e:
                logger.exception(f"Error in stream cleanup task: {e}")

        # Start the cleanup task
        cls._cleanup_task = asyncio.create_task(cleanup_task())

        try:
            # Yield control back to the caller
            yield
        finally:
            # Signal the task to stop
            cancel_event.set()
            # Wait for the task to complete
            if cls._cleanup_task:
                try:
                    await asyncio.wait_for(cls._cleanup_task, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Stream cleanup task did not complete in time")
