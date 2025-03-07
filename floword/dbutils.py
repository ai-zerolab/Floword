from __future__ import annotations

import os
from contextlib import asynccontextmanager, contextmanager

try:
    from functools import cache
except ImportError:
    from functools import lru_cache as cache

from collections.abc import AsyncGenerator
from glob import glob
from pathlib import Path
from subprocess import check_call
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import alembic.command
import alembic.config
from alembic.script import ScriptDirectory
from fastapi import Depends
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy import delete, exc, inspect, text
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as sqlalchemy_create_async_engine
from sqlalchemy.orm import Session

from floword.config import Config, get_config
from floword.log import logger
from floword.orm import Base

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_here = os.path.abspath(os.path.dirname(__file__))

ALEMBIC_INI_TEMPLATE_PATH = os.path.join(_here, "alembic.ini")
ALEMBIC_DIR = os.path.join(_here, "alembic")


def get_connect_args(db_url: str) -> dict:
    """
    Get connection arguments based on database URL.

    Parameters
    ----------
    db_url : str
        The SQLAlchemy database url

    Returns
    -------
    dict
        Connection arguments for the specified database
    """
    parsed_url = urlparse(db_url)
    scheme = parsed_url.scheme

    if scheme.startswith("sqlite"):
        # SQLite specific connect args
        return {
            "check_same_thread": False,  # Allow multiple threads to access the same connection
            "timeout": 30,  # Connection timeout in seconds
        }
    elif scheme.startswith("postgresql"):
        # PostgreSQL specific connect args
        return {
            # Application name for identification in database logs
            "application_name": "floword",
            # Statement timeout (in milliseconds) to prevent long-running queries
            # 30 seconds timeout
            "options": "-c statement_timeout=30000",
            # TCP keepalive settings
            "keepalives": 1,
            "keepalives_idle": 60,  # seconds before sending keepalive
            "keepalives_interval": 10,  # seconds between keepalives
            "keepalives_count": 5,  # max number of keepalive packets
            # SSL configuration (uncomment if needed)
            # 'sslmode': 'require',  # Options: disable, allow, prefer, require, verify-ca, verify-full
            # 'sslrootcert': '/path/to/ca.crt',
        }

    # Default empty dict for other database types
    return {}


def create_async_engine(url, **kwargs):
    """
    Create an async SQLAlchemy engine with appropriate connect_args and engine settings
    based on the database URL.

    Parameters
    ----------
    url : str
        The SQLAlchemy database url
    **kwargs : dict
        Additional keyword arguments to pass to sqlalchemy_create_async_engine

    Returns
    -------
    AsyncEngine
        SQLAlchemy async engine instance
    """
    connect_args = get_connect_args(url)
    engine_kwargs = {}

    # Common engine settings for all database types
    engine_kwargs.update({
        "echo": False,  # Set to True for SQL query logging
        # "pool_pre_ping": True,  # Verify connections before using them
    })

    parsed_url = urlparse(url)
    scheme = parsed_url.scheme

    if scheme.startswith("sqlite"):
        # SQLite specific engine settings
        engine_kwargs.update({
            "pool_recycle": 3600,  # Recycle connections after 1 hour
        })
    elif scheme.startswith("postgresql"):
        # PostgreSQL specific engine settings
        engine_kwargs.update({
            "pool_size": 5,  # Default connection pool size
            "max_overflow": 10,  # Allow up to 10 connections beyond pool_size
            "pool_timeout": 30,  # Timeout for getting a connection from the pool
            "pool_recycle": 1800,  # Recycle connections after 30 minutes
        })

    # Override with user-provided kwargs
    engine_kwargs.update(kwargs)

    return sqlalchemy_create_async_engine(url, connect_args=connect_args, **engine_kwargs)


def create_engine(url, **kwargs):
    """
    Create a SQLAlchemy engine with appropriate connect_args and engine settings
    based on the database URL.

    Parameters
    ----------
    url : str
        The SQLAlchemy database url
    **kwargs : dict
        Additional keyword arguments to pass to sqlalchemy_create_engine

    Returns
    -------
    Engine
        SQLAlchemy engine instance
    """
    connect_args = get_connect_args(url)
    engine_kwargs = {}

    # Common engine settings for all database types
    engine_kwargs.update({
        "echo": False,  # Set to True for SQL query logging
        # "pool_pre_ping": True,  # Verify connections before using them
    })

    parsed_url = urlparse(url)
    scheme = parsed_url.scheme

    if scheme.startswith("sqlite"):
        # SQLite specific engine settings
        engine_kwargs.update({
            "pool_recycle": 3600,  # Recycle connections after 1 hour
        })
    elif scheme.startswith("postgresql"):
        # PostgreSQL specific engine settings
        engine_kwargs.update({
            "pool_size": 5,  # Default connection pool size
            "max_overflow": 10,  # Allow up to 10 connections beyond pool_size
            "pool_timeout": 30,  # Timeout for getting a connection from the pool
            "pool_recycle": 1800,  # Recycle connections after 30 minutes
        })

    # Override with user-provided kwargs
    engine_kwargs.update(kwargs)

    return sqlalchemy_create_engine(url, connect_args=connect_args, **engine_kwargs)


def write_alembic_ini(alembic_ini="alembic.ini", db_url="sqlite:///floword.sqlite"):
    """Write a complete alembic.ini from our template.

    Parameters
    ----------
    alembic_ini : str
        path to the alembic.ini file that should be written.
    db_url : str
        The SQLAlchemy database url, e.g. `sqlite:///floword.sqlite`.
    """
    with open(ALEMBIC_INI_TEMPLATE_PATH) as f:
        alembic_ini_tpl = f.read()

    with open(alembic_ini, "w") as f:
        f.write(
            alembic_ini_tpl.format(
                alembic_dir=ALEMBIC_DIR,
                # If there are any %s in the URL, they should be replaced with %%, since ConfigParser
                # by default uses %() for substitution. You'll get %s in your URL when you have usernames
                # with special chars (such as '@') that need to be URL encoded. URL Encoding is done with %s.
                # YAY for nested templates?
                db_url=str(db_url).replace("%", "%%"),
            )
        )


@contextmanager
def _temp_alembic_ini(db_url):
    """Context manager for temporary alembic directory

    Temporarily write an alembic.ini file for use with alembic migration scripts.

    Context manager yields alembic.ini path.

    Parameters
    ----------
    db_url : str
        The SQLAlchemy database url, e.g. `sqlite:///floword.sqlite`.

    Returns
    -------
    alembic_ini: str
        The path to the temporary alembic.ini that we have created.
        This file will be cleaned up on exit from the context manager.
    """
    with TemporaryDirectory() as td:
        alembic_ini = os.path.join(td, "alembic.ini")
        write_alembic_ini(alembic_ini, db_url)
        yield alembic_ini


@contextmanager
def chdir(path):
    """Context manager to temporarily change directory"""
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)


def upgrade(db_url, revision="head"):
    """Upgrade the given database to revision.

    db_url: str
        The SQLAlchemy database url, e.g. `sqlite:///floword.sqlite`.
    revision: str [default: head]
        The alembic revision to upgrade to.
    """
    with _temp_alembic_ini(db_url) as alembic_ini:
        check_call(["alembic", "-c", alembic_ini, "upgrade", revision])


class DatabaseSchemaMismatch(Exception):
    pass


def _clear_revision(engine, url):
    inspector = inspect(engine)
    if inspector.has_table("alembic_version"):
        logger.info("Clearing alembic_version table")
        with engine.begin() as connection:
            connection.execute(text("delete from alembic_version"))

    with _temp_alembic_ini(url) as ini:
        cfg = alembic.config.Config(ini)
        scripts = ScriptDirectory.from_config(cfg)
        old_versions_files = Path(scripts.versions) / "*.py"
        # Remove *.py from old_versions
        for old_versions_file in glob(old_versions_files.as_posix()):
            os.remove(old_versions_file)

        alembic.command.revision(config=cfg, autogenerate=True, message="init")
    inspector = inspect(engine)

    # Check for alembic_version table (case-insensitive for SQLite compatibility)
    table_exists = False
    for table_name in inspector.get_table_names():
        if table_name.lower() == "alembic_version":
            table_exists = True
            break

    if table_exists:
        # Use explicit transaction management for better SQLite compatibility
        with engine.connect() as connection:
            # Start transaction
            trans = connection.begin()
            try:
                # Use parameterized query for better safety
                connection.execute(text("DELETE FROM alembic_version"))
                # Commit transaction
                trans.commit()
            except Exception as e:
                # Rollback on error
                trans.rollback()
                logger.error(f"Error clearing alembic_version table: {e}")
                raise

    # Create a fresh alembic environment
    with _temp_alembic_ini(url) as ini:
        cfg = alembic.config.Config(ini)

        # Ensure the versions directory exists and is empty
        scripts_dir = ScriptDirectory.from_config(cfg)
        versions_dir = Path(scripts_dir.versions)

        # Create versions directory if it doesn't exist
        if not versions_dir.exists():
            versions_dir.mkdir(parents=True, exist_ok=True)

        # Remove any existing version files
        for old_version_file in versions_dir.glob("*.py"):
            old_version_file.unlink()

        # Create a fresh initial revision
        try:
            # Use stamp to initialize the alembic_version table with a base revision
            alembic.command.stamp(cfg, "base")

            # Now create a new revision
            alembic.command.revision(cfg, autogenerate=True, message="init")
        except Exception as e:
            logger.error(f"Error during alembic revision creation: {e}")
            raise


def get_db_log_url(db_url):
    urlinfo = urlparse(db_url)
    if urlinfo.password:
        # avoid logging the database password
        urlinfo = urlinfo._replace(netloc=f"{urlinfo.username}:[redacted]@{urlinfo.hostname}:{urlinfo.port}")
        db_log_url = urlinfo.geturl()
    else:
        db_log_url = db_url
    return db_log_url


def init_and_migrate(db_url):
    """This is a dark magic function that upgrades the database in-place."""
    # run check-db-revision first

    db_log_url = get_db_log_url(db_url)
    logger.info(f"Initializing database: {db_log_url}")

    # Get database type from URL
    parsed_url = urlparse(db_url)
    scheme = parsed_url.scheme
    is_sqlite = scheme.startswith("sqlite")

    # Create engine with appropriate settings
    engine = create_engine(db_url)

    # For SQLite, enable foreign keys
    if is_sqlite:
        with engine.connect() as connection:
            connection.execute(text("PRAGMA foreign_keys = ON"))

    # Create all tables
    Base.metadata.create_all(engine)

    with chdir(_here):
        _clear_revision(engine, db_url)
        logger.info(f"Upgrading database: {db_log_url}")
        upgrade(db_url)


def remove_all_data(db_url):
    db_log_url = get_db_log_url(db_url)
    logger.info(f"Dropping database: {db_log_url}")
    engine = create_engine(db_url)
    for t in Base.metadata.tables.values():
        logger.info(f"Delete table data: {t}")
        with Session(engine) as session:
            session.execute(delete(t))
            session.commit()


@cache
def get_engine(config: Config):
    logger.info("Creating database engine")
    return create_async_engine(config.get_db_url())


@asynccontextmanager
async def init_engine(config: Config):
    engine = get_engine(config)
    yield
    await engine.dispose()
    logger.info("Database engine disposed")


def create_sessionmaker(config: Config):
    return async_sessionmaker(get_engine(config))


async def get_db_session(
    config: Config = Depends(get_config),
) -> AsyncGenerator[AsyncSession, None]:
    """
    For fastapi dependency injection
    """
    async with create_sessionmaker(config)() as session:
        try:
            yield session
            await session.commit()
        except exc.SQLAlchemyError:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def open_db_session(
    config: Config,
    engine_kwargs: dict[str, Any] | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """
    A helper function to open a database session

    NOTE: This is not optimized for performance as not reuse engine for polling connections
          Use get_db_session as Depend via fastapi dependency injection

    Parameters
    ----------
    config : Config
        Application configuration
    engine_kwargs : dict[str, Any] | None
        Additional keyword arguments to pass to create_async_engine

    Yields
    ------
    AsyncSession
        SQLAlchemy async session
    """
    db_url = config.get_db_url()
    engine = create_async_engine(db_url, **(engine_kwargs or {}))
    factory = async_sessionmaker(engine)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except exc.SQLAlchemyError:
            await session.rollback()
            raise
        finally:
            await session.close()
