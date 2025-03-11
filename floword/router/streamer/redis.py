from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Generic, TypeVar

import redis.asyncio as redis

from floword.config import get_config
from floword.log import logger

T = TypeVar("T")


class StreamData(Generic[T]):
    """
    Stores stream data and provides methods to access it using Redis streams.
    """

    def __init__(
        self,
        stream_id: str,
        redis_client: redis.Redis | None = None,
        metadata: dict | None = None,
        *,
        init_metadata: bool = False,
    ):
        """
        Initialize a new StreamData instance.

        Args:
            stream_id: The ID of the stream
            redis_client: Redis client to use (if None, one will be created)
            metadata: Optional metadata to store with the stream
        """
        if not redis_client:
            c = get_config()
            redis_client = redis.from_url(c.redis_url)
        self.redis_client = redis_client
        self.stream_id = stream_id
        self.stream_key = f"stream:{stream_id}"
        self.meta_key = f"stream:{stream_id}:meta"

        # Initialize metadata if not provided
        if init_metadata:
            metadata = metadata or {}
            now = datetime.now().isoformat()
            default_metadata = {
                "created_at": now,
                "updated_at": now,
                "completed": "0",
                "completed_at": "",
            }

            # Merge default with provided metadata
            merged_metadata = {**default_metadata, **metadata}

            # Store metadata in Redis
            asyncio.create_task(self._set_metadata(merged_metadata))  # noqa: RUF006

    async def _set_metadata(self, metadata: dict) -> None:
        """Set metadata for the stream."""
        await self.redis_client.hset(self.meta_key, mapping=metadata)

    async def _get_metadata(self) -> dict:
        """Get metadata for the stream."""
        metadata = await self.redis_client.hgetall(self.meta_key)
        return {k.decode("utf-8"): v.decode("utf-8") for k, v in metadata.items()}

    async def add_event(self, event: T) -> None:
        """Add an event to the stream."""
        # Serialize the event (assuming it's JSON serializable)
        event_data = {"data": json.dumps(event)}

        # Add to Redis stream
        await self.redis_client.xadd(self.stream_key, event_data)

        # Update metadata
        await self.redis_client.hset(self.meta_key, "updated_at", datetime.now().isoformat())

    async def is_completed(self) -> bool:
        """Check if the stream is completed."""
        completed = await self.redis_client.hget(self.meta_key, "completed")
        # If completed is None, the key doesn't exist
        if completed is None:
            return False
        return completed == b"1"

    async def mark_completed(self, ttl: int = 3600) -> None:
        """
        Mark the stream as completed and set TTL.

        Args:
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        now = datetime.now().isoformat()

        # Ensure the metadata exists before updating it
        if not await self.redis_client.exists(self.meta_key):
            # Initialize metadata if it doesn't exist
            default_metadata = {
                "created_at": now,
                "updated_at": now,
                "completed": "0",
                "completed_at": "",
            }
            await self._set_metadata(default_metadata)

        # Update the metadata to mark as completed
        await self.redis_client.hset(self.meta_key, "completed", "1")
        await self.redis_client.hset(self.meta_key, "completed_at", now)
        await self.redis_client.hset(self.meta_key, "updated_at", now)

        # Set TTL on both the stream and metadata
        # Only set TTL if it's greater than 0
        if ttl > 0:
            await self.redis_client.expire(self.stream_key, ttl)
            await self.redis_client.expire(self.meta_key, ttl)

    async def stream_events(self, start_index: int = 0) -> AsyncIterator[T]:
        """
        Stream events from Redis.

        Args:
            start_index: Index to start streaming from (0 for beginning)

        Yields:
            Events from the stream
        """
        # Convert start_index to Redis stream ID format
        # Redis stream IDs are in format "timestamp-sequence"
        # For simplicity, we'll use "0-0" as the starting ID if start_index is 0
        last_id = "0-0" if start_index == 0 else await self._get_id_by_index(start_index)

        while True:
            # Read new messages from the stream
            response = await self.redis_client.xread({self.stream_key: last_id}, count=10)

            if not response:  # No new messages
                if await self.is_completed():
                    break  # Stream is completed, exit

                # Wait for new messages or completion
                await asyncio.sleep(0.1)
                continue

            # Process messages
            for _stream_name, messages in response:
                for message_id, data in messages:
                    last_id = message_id  # Update last_id for next iteration
                    # Deserialize and yield the event
                    yield json.loads(data[b"data"].decode("utf-8"))

    async def _get_id_by_index(self, index: int) -> str:
        """Convert a numeric index to a Redis stream ID."""
        # This is a simplified implementation
        # In a real-world scenario, you might want to store a mapping
        # between indices and Redis stream IDs
        if index <= 0:
            return "0-0"

        # Get all messages and find the one at the specified index
        messages = await self.redis_client.xrange(self.stream_key)
        if index >= len(messages):
            # If index is out of range, return the last message ID
            return messages[-1][0].decode("utf-8") if messages else "0-0"

        # Return the ID of the message at the specified index
        return messages[index][0].decode("utf-8")


class PersistentStreamer:
    """
    Singleton class that manages persistent streams using Redis.
    """

    _instance: PersistentStreamer | None = None
    _cleanup_task: asyncio.Task | None = None

    @classmethod
    def get_instance(cls) -> PersistentStreamer:
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = PersistentStreamer()
        return cls._instance

    def __init__(self):
        c = get_config()
        self.redis_client = redis.from_url(c.redis_url)
        self.streams_key = "streams"  # Set to track all stream IDs
        self.ttl = 3600  # Default TTL for completed streams (1 hour)

    async def create_stream(self, stream_id: str, metadata: dict | None = None) -> StreamData:
        """Create a new stream with the given ID."""
        if await self.has_stream(stream_id):
            raise ValueError(f"Stream with ID {stream_id} already exists")

        # Add to set of streams
        await self.redis_client.sadd(self.streams_key, stream_id)

        # Create stream with metadata
        stream_data = StreamData(stream_id, self.redis_client, metadata, init_metadata=True)
        return stream_data

    async def get_stream(self, stream_id: str) -> StreamData:
        """Get a stream by ID."""
        if not await self.has_stream(stream_id):
            raise ValueError(f"Stream with ID {stream_id} not found")

        return StreamData(stream_id, self.redis_client)

    async def get_streams(self) -> dict[str, StreamData]:
        """Get all streams."""
        stream_ids = await self.redis_client.smembers(self.streams_key)
        return {
            stream_id.decode("utf-8"): StreamData(stream_id.decode("utf-8"), self.redis_client)
            for stream_id in stream_ids
        }

    async def delete_stream(self, stream_id: str) -> None:
        """Delete a stream by ID."""
        # Delete the stream and metadata
        stream_key = f"stream:{stream_id}"
        meta_key = f"stream:{stream_id}:meta"

        # Remove from Redis
        await self.redis_client.delete(stream_key, meta_key)

        # Remove from set of streams
        await self.redis_client.srem(self.streams_key, stream_id)

    async def has_stream(self, stream_id: str) -> bool:
        """Check if a stream with the given ID exists."""
        # Check if the stream exists in Redis
        meta_key = f"stream:{stream_id}:meta"

        # Check if the metadata exists (more reliable than checking the stream key)
        exists = await self.redis_client.exists(meta_key)
        logger.debug(f"Stream {stream_id} exists: {exists}")

        if exists:
            # Check if the stream is completed
            try:
                stream_data = StreamData(stream_id, self.redis_client)
                if await stream_data.is_completed():
                    # If completed, remove it and return False
                    logger.info(f"Stream {stream_id} is completed, removing it")
                    await self.delete_stream(stream_id)
                    return False
            except Exception as e:
                logger.exception(f"Error checking if stream {stream_id} is completed: {e}")

            # Make sure it's in the streams set
            await self.redis_client.sadd(self.streams_key, stream_id)
            return True

        # Check if it's in the streams set
        is_member = await self.redis_client.sismember(self.streams_key, stream_id)
        logger.debug(f"Stream {stream_id} in streams set: {is_member}")

        if is_member and not exists:
            # Remove from streams set if metadata doesn't exist
            await self.redis_client.srem(self.streams_key, stream_id)
            return False

        return bool(is_member)

    async def cleanup_completed_streams(self) -> None:
        """Clean up all completed streams."""
        streams = await self.get_streams()
        for stream_id, stream_data in streams.items():
            try:
                if await stream_data.is_completed():
                    logger.info(f"Cleaning up completed stream: {stream_id}")
                    await self.delete_stream(stream_id)
            except Exception as e:
                logger.exception(f"Error cleaning up stream {stream_id}: {e}")

    @classmethod
    @asynccontextmanager
    async def auto_cleanup(cls, cleanup_interval: int = 60):
        """
        Start a background task that periodically cleans up completed streams.

        Args:
            cleanup_interval: Time in seconds between cleanup runs

        Returns:
            An async context manager that cancels the cleanup task when exiting
        """
        # Create a cancellation event
        cancel_event = asyncio.Event()
        streamer = cls.get_instance()

        # Define the cleanup task
        async def cleanup_task():
            try:
                # Run cleanup immediately once
                await streamer.cleanup_completed_streams()

                # Then run periodically
                while not cancel_event.is_set():
                    # Wait for the specified interval or until cancelled
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(cancel_event.wait(), timeout=cleanup_interval)

                    # If cancelled, exit
                    if cancel_event.is_set():
                        break

                    # Clean up completed streams
                    await streamer.cleanup_completed_streams()
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
