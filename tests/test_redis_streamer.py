import asyncio
import json
import socket
from datetime import time

import docker
import pytest
import redis.asyncio as redis

from floword.router.streamer.redis import PersistentStreamer


@pytest.fixture(scope="session")
def event_loop(event_loop_policy):
    # Needed to work with asyncpg
    loop = event_loop_policy.new_event_loop()
    yield loop
    loop.close()


def get_port():
    # Get an unoccupied port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def docker_client():
    try:
        client = docker.from_env()
        client.ping()
    except:
        pytest.skip("Docker is not available")

    return client


@pytest.fixture(scope="session")
def redis_port(docker_client: docker.DockerClient):
    redis_port = get_port()
    container = None
    try:
        container = docker_client.containers.run(
            "redis",
            detach=True,
            ports={"6379": redis_port},
            remove=True,
            environment={},
        )
        while True:
            # Check if Redis is ready
            try:
                r = container.exec_run("redis-cli ping")
                assert r.exit_code == 0
                assert b"PONG" in r.output
            except Exception:
                time.sleep(0.5)
            else:
                break
        yield redis_port
    finally:
        if container:
            container.stop()


@pytest.fixture(autouse=True)
def patch_env(monkeypatch, redis_port):
    redis_url = f"redis://localhost:{redis_port}"
    monkeypatch.setenv("FLOWORD_REDIS_URL", redis_url)
    PersistentStreamer._instance = None
    return redis_url


@pytest.fixture
async def redis_client(patch_env):
    # Create a new Redis client for each test
    client = redis.from_url(patch_env)

    # Ensure Redis is working by pinging it
    await client.ping()

    # Clear any existing data
    await client.flushall()

    try:
        yield client
    finally:
        # Clean up after the test
        try:
            await client.flushall()
            await client.aclose()
        except Exception:
            pass  # Ignore errors during cleanup


@pytest.mark.asyncio
async def test_create_stream(redis_client):
    """Test creating a stream."""
    streamer = PersistentStreamer.get_instance()
    stream_id = "test-stream"

    # Create a stream
    stream_data = await streamer.create_stream(stream_id)

    # Wait for task
    await asyncio.sleep(0.5)
    # Verify the stream exists
    assert await streamer.has_stream(stream_id)

    # Verify the stream metadata exists
    meta = await redis_client.hgetall(f"stream:{stream_id}:meta")
    assert meta
    assert b"created_at" in meta
    assert b"completed" in meta
    assert meta[b"completed"] == b"0"


@pytest.mark.asyncio
async def test_add_event(redis_client):
    """Test adding events to a stream."""
    streamer = PersistentStreamer.get_instance()
    stream_id = "test-stream-events"

    # Create a stream
    stream_data = await streamer.create_stream(stream_id)

    # Add events
    event1 = {"message": "Hello"}
    event2 = {"message": "World"}
    await stream_data.add_event(event1)
    await stream_data.add_event(event2)

    # Verify events were added to Redis stream
    stream_key = f"stream:{stream_id}"
    messages = await redis_client.xrange(stream_key)
    assert len(messages) == 2

    # Verify event content
    _, data1 = messages[0]
    _, data2 = messages[1]
    assert json.loads(data1[b"data"].decode("utf-8")) == event1
    assert json.loads(data2[b"data"].decode("utf-8")) == event2


@pytest.mark.asyncio
async def test_stream_events(redis_client):
    """Test streaming events from a stream."""
    streamer = PersistentStreamer.get_instance()
    stream_id = "test-stream-streaming"

    # Create a stream
    stream_data = await streamer.create_stream(stream_id)

    # Add events
    events = [{"message": f"Event {i}"} for i in range(5)]
    for event in events:
        await stream_data.add_event(event)

    # Stream events
    received_events = []
    async for event in stream_data.stream_events():
        received_events.append(event)
        if len(received_events) == len(events):
            # Mark completed to end the stream
            await stream_data.mark_completed()

    # Verify received events
    assert received_events == events


@pytest.mark.asyncio
async def test_mark_completed_with_ttl(redis_client):
    """Test marking a stream as completed with TTL."""
    streamer = PersistentStreamer.get_instance()
    stream_id = "test-stream-ttl"

    # Create a stream
    stream_data = await streamer.create_stream(stream_id)

    # Add an event to ensure the stream exists
    await stream_data.add_event({"message": "Test event"})

    # Wait a bit to ensure the metadata is set
    await asyncio.sleep(0.1)

    # Mark as completed with a short TTL
    ttl = 2  # 2 seconds
    await stream_data.mark_completed(ttl)

    # Verify stream is marked as completed
    assert await stream_data.is_completed()

    # Verify TTL is set
    stream_key = f"stream:{stream_id}"
    meta_key = f"stream:{stream_id}:meta"
    assert await redis_client.ttl(stream_key) <= ttl
    assert await redis_client.ttl(meta_key) <= ttl

    # Wait for TTL to expire
    await asyncio.sleep(ttl + 1)

    # Verify keys are gone
    assert not await redis_client.exists(stream_key)
    assert not await redis_client.exists(meta_key)


@pytest.mark.asyncio
async def test_metadata(redis_client):
    """Test stream metadata."""
    streamer = PersistentStreamer.get_instance()
    stream_id = "test-stream-metadata"

    # Create a stream with metadata
    metadata = {"user_id": "test-user", "conversation_id": "test-conversation"}
    stream_data = await streamer.create_stream(stream_id, metadata)

    # Wait a bit for the async task to complete
    await asyncio.sleep(0.1)

    # Verify metadata was stored
    meta_key = f"stream:{stream_id}:meta"
    stored_metadata = await redis_client.hgetall(meta_key)

    # Check custom metadata
    assert stored_metadata[b"user_id"] == b"test-user"
    assert stored_metadata[b"conversation_id"] == b"test-conversation"

    # Check default metadata
    assert b"created_at" in stored_metadata
    assert b"updated_at" in stored_metadata
    assert stored_metadata[b"completed"] == b"0"


@pytest.mark.asyncio
async def test_auto_cleanup(redis_client):
    """Test auto cleanup of completed streams."""
    streamer = PersistentStreamer.get_instance()

    # Create streams
    stream1 = await streamer.create_stream("cleanup-test-1")
    stream2 = await streamer.create_stream("cleanup-test-2")

    # Add events to ensure the streams exist
    await stream1.add_event({"message": "Test event 1"})
    await stream2.add_event({"message": "Test event 2"})

    # Wait a bit to ensure the metadata is set
    await asyncio.sleep(0.1)

    # Mark one as completed with no TTL (0)
    await stream1.mark_completed(0)

    # Verify stream is marked as completed
    assert await stream1.is_completed()

    # Run cleanup directly to avoid timing issues
    await streamer.cleanup_completed_streams()

    # Verify completed stream was deleted
    assert not await streamer.has_stream("cleanup-test-1")
    # Verify non-completed stream still exists
    assert await streamer.has_stream("cleanup-test-2")


@pytest.mark.asyncio
async def test_nonexistent_stream(redis_client):
    """Test handling of non-existent streams."""
    streamer = PersistentStreamer.get_instance()

    # Try to get a non-existent stream
    with pytest.raises(ValueError):
        await streamer.get_stream("non-existent-stream")

    # Verify has_stream returns False
    assert not await streamer.has_stream("non-existent-stream")


@pytest.mark.asyncio
async def test_reconnection(redis_client):
    """Test reconnection to a stream after disconnection."""
    streamer = PersistentStreamer.get_instance()
    stream_id = "reconnection-test"

    # Create a stream
    stream_data = await streamer.create_stream(stream_id)

    # Add some events
    events = [{"message": f"Event {i}"} for i in range(3)]
    for event in events:
        await stream_data.add_event(event)

    # Start streaming but disconnect after 2 events
    received_events = []
    async for event in stream_data.stream_events():
        received_events.append(event)
        if len(received_events) == 2:
            break

    # Verify we received 2 events
    assert len(received_events) == 2
    assert received_events == events[:2]

    # Add more events
    more_events = [{"message": f"More Event {i}"} for i in range(3)]
    for event in more_events:
        await stream_data.add_event(event)

    # Reconnect and get all events from the beginning
    all_received_events = []
    async for event in stream_data.stream_events():
        all_received_events.append(event)
        if len(all_received_events) == len(events) + len(more_events):
            await stream_data.mark_completed()

    # Verify we received all events
    assert all_received_events == events + more_events
