from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_HERE = Path(__file__).parent


def get_config() -> Config:
    return Config()


DEFAULT_CONVERSATION_SYSTEM_PROMPT = (_HERE / "prompts" / "system-conversation.md").read_text()

DEFAULT_WORKFLOW_SYSTEM_PROMPT = (_HERE / "prompts" / "system-workflow.md").read_text()


class Config(BaseSettings):
    """
    Complex types like list, set, dict, and sub-models are populated from the environment by treating the environment variable's value as a JSON-encoded string.
    """

    jwt_secret_token: str | None = None
    allow_anonymous: bool = True

    sqlite_file_path: str = (Path.cwd() / "floword.sqlite").expanduser().resolve().absolute().as_posix()
    use_postgres: bool = False
    pg_user: str | None = "postgres"
    pg_password: str | None = "postgres"
    pg_host: str | None = "localhost"
    pg_port: int | None = 5432
    pg_database: str | None = "floword"
    redis_url: str | None = None

    default_model_provider: str | None = "openai"
    default_model_name: str | None = None
    default_model_kwargs: str | None = None

    default_conversation_system_prompt: str = DEFAULT_CONVERSATION_SYSTEM_PROMPT
    default_workflow_system_prompt: str = DEFAULT_WORKFLOW_SYSTEM_PROMPT
    mcp_config_path: str = (Path.cwd() / "./mcp.json").expanduser().resolve().absolute().as_posix()

    model_config = SettingsConfigDict(env_prefix="floword_", case_sensitive=False, frozen=True, env_file=".env")

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
            sqlite_file_path = Path(self.sqlite_file_path).expanduser().resolve().absolute().as_posix()
            if async_mode:
                return f"sqlite+aiosqlite:///{sqlite_file_path}"
            else:
                return f"sqlite+pysqlite:///{sqlite_file_path}"
