"""Backend configuration models for the Floword UI."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class BackendMode(str, Enum):
    """Backend mode enum."""

    LOCAL = "local"
    REMOTE = "remote"


class BackendConfig(BaseModel):
    """Backend configuration model."""

    mode: BackendMode = BackendMode.LOCAL
    port: int = 9772  # Default port
    api_url: str = "http://localhost:9772"
    api_token: str | None = None
    env_vars: dict[str, str] = Field(default_factory=dict)
