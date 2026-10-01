from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "APP_"
MAX_READY_DEADLINE_SECONDS = 3.0

_NATS_URL = re.compile(r"^nats://[A-Za-z0-9.-]+(:[0-9]{1,5})?$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    http_host: str = "127.0.0.1"
    http_port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    db_host: str = Field(min_length=1)
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = Field(min_length=1)
    db_user: str = Field(min_length=1)
    db_password: SecretStr = Field(min_length=8)

    nats_url: str
    nats_user: str = Field(min_length=1)
    nats_password: SecretStr = Field(min_length=8)

    ready_timeout_seconds: float = Field(default=2.5, gt=0, le=MAX_READY_DEADLINE_SECONDS)

    auth_jwks_file: Path = Path("/run/auth/jwks.json")
    auth_issuer: str = Field(default="recon-dev-idp", min_length=1)
    auth_audience: str = Field(default="recon-api", min_length=1)

    @field_validator("nats_url")
    @classmethod
    def _nats_url_without_credentials(cls, value: str) -> str:
        if not _NATS_URL.fullmatch(value):
            raise ValueError(
                "must look like nats://host:port and must not embed credentials; "
                "use APP_NATS_USER / APP_NATS_PASSWORD"
            )
        return value


class ConfigurationError(Exception):
    """Invalid configuration. Carries field names and reasons, never input values."""

    def __init__(self, problems: list[tuple[str, str]]) -> None:
        self.problems = problems
        super().__init__("invalid configuration: " + ", ".join(f for f, _ in problems))


SECRET_FIELDS = frozenset({"db_password", "nats_password"})


def _field(loc: tuple[int | str, ...]) -> str:
    return str(loc[0]) if loc else "<root>"


def _problem(field: str, error_type: str, message: str) -> str:
    if field in SECRET_FIELDS and error_type != "missing":
        # Validator messages can reveal properties of the value (e.g. its length).
        return "invalid secret value (minimum 8 characters)"
    return message


def load_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = []
        for error in exc.errors(include_input=False, include_url=False, include_context=False):
            field = _field(error["loc"])
            problems.append(
                (f"{ENV_PREFIX}{field.upper()}", _problem(field, error["type"], error["msg"]))
            )
        raise ConfigurationError(problems) from None
