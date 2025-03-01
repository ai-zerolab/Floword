from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from functools import cache
except ImportError:
    pass

_HERE = Path(__file__).parent.resolve()


def get_config() -> Config:
    return Config()


class Config(BaseSettings):
    use_postgres: bool = False
    token: str | None = None

    sqlite_file_path: str = (_HERE / ".." / "floword.sqlite").resolve().as_posix()
    pg_user: str | None = "postgres"
    pg_password: str | None = "postgres"
    pg_host: str | None = "localhost"
    pg_port: int | None = 5432
    pg_database: str | None = "floword"

    mcp_config_path: str = (_HERE / "./mcp.json").resolve().as_posix()

    model_config = SettingsConfigDict(env_prefix="floword_", case_sensitive=False, frozen=True)

    def get_db_url(self, async_mode: bool = True) -> str:
        if self.use_postgres:
            if not all([
                self.pg_user,
                self.pg_password,
                self.pg_host,
                self.pg_port,
                self.pg_database,
            ]):
                raise ValueError("PostgreSQL configuration is incomplete")
            return f"postgresql+psycopg://{self.pg_user}:{self.pg_password}@{self.pg_host}:{self.pg_port}/{self.pg_database}"
        else:
            if not self.sqlite_file_path:
                raise ValueError("SQLite file path is not configured")
            sqlite_file_path = Path(self.sqlite_file_path).expanduser().resolve().as_posix()
            if async_mode:
                return f"sqlite+aiosqlite:///{sqlite_file_path}"
            else:
                return f"sqlite+pysqlite:///{sqlite_file_path}"
