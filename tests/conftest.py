from __future__ import annotations

import os

os.environ["LOGURU_LEVEL"] = "DEBUG"

import socket
import time
from collections.abc import Generator, Iterable
from uuid import uuid4

import docker
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from floword.app import app as APP
from floword.cli import clear, migrate
from floword.config import get_config
from floword.dbutils import open_db_session

TEST_DB_SETTINGS = {
    "FLOWORD_USE_POSTGRES": "true",
    "FLOWORD_PG_USER": "postgres",
    "FLOWORD_PG_PASSWORD": "postgres",
    "FLOWORD_PG_HOST": "localhost",
    "FLOWORD_PG_DATABASE": "floword",
}


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


@pytest.fixture
def case_id():
    return uuid4().hex


@pytest.fixture(scope="session")
def pg_port(docker_client: docker.DockerClient):
    pg_port = get_port()
    container = None
    try:
        container = docker_client.containers.run(
            "postgres:16",
            detach=True,
            ports={"5432": pg_port},
            remove=True,
            environment={
                "POSTGRES_USER": "postgres",
                "POSTGRES_PASSWORD": "postgres",
                "POSTGRES_DB": "floword",
            },
        )
        while True:
            # Execute `pg_isready -U postgres` in the container
            try:
                # Pg is ready
                r = container.exec_run("pg_isready -U postgres")
                assert r.exit_code == 0
                assert b"accepting connections" in r.output
                # Try to connect db
                engine = create_engine(f"postgresql+psycopg://postgres:postgres@localhost:{pg_port}/floword")
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception:
                time.sleep(0.5)
            else:
                break
        yield pg_port
    finally:
        if container:
            container.stop()


@pytest.fixture(
    params=[
        "sqlite",
        "postgres",
    ]
)
def db_env(request, pg_port, tmp_path) -> Generator[Iterable[tuple[str, str]], None, None]:
    sqlite_path = tmp_path / "floword.sqlite"
    if request.param == "sqlite":
        yield [
            ("FLOWORD_USE_POSTGRES", "false"),
            ("FLOWORD_SQLITE_FILE_PATH", str(sqlite_path)),
        ]
    elif request.param == "postgres":
        envs = list(TEST_DB_SETTINGS.items())
        yield [
            *envs,
            ("FLOWORD_PG_PORT", str(pg_port)),
        ]


@pytest.fixture
def app(monkeypatch, db_env):
    for env, value in db_env:
        monkeypatch.setenv(env, value)
    runner = CliRunner()
    result = runner.invoke(
        migrate,
        env=dict(db_env),
    )
    assert result.exit_code == 0
    # Drop all before testing
    result = runner.invoke(
        clear,
        ["--yes"],
        env=dict(db_env),
    )
    assert result.exit_code == 0

    # Dependencies injection mock
    APP.dependency_overrides = {}
    yield APP


@pytest.fixture
def client_header():
    config = get_config()
    headers = {}

    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"

    return headers


@pytest.fixture
def client(app, client_header):
    with TestClient(
        app,
        headers=client_header,
    ) as client:
        yield client


@pytest.fixture
async def db_session(app):
    async with open_db_session(get_config()) as session:
        yield session
