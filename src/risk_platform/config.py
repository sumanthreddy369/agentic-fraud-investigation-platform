from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RISK_", env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://risk_local:risk_local@localhost:55432/risk_platform"
    )
    api_token: SecretStr = SecretStr("")
    operator_id: str = Field(default="local-investigator", min_length=1, max_length=200)
    operator_role: Literal["investigator", "reviewer", "auditor"] = "investigator"
    allowed_domains: set[str] = {"ieee_cis", "home_credit", "elliptic"}
    max_body_bytes: int = Field(default=65536, ge=1024, le=1048576)
    max_header_bytes: int = Field(default=16384, ge=1024, le=65536)
    body_timeout_seconds: float = Field(default=5, gt=0, le=30)
    requests_per_minute: int = Field(default=120, ge=1, le=10000)
    rate_limit_max_clients: int = Field(default=1024, ge=1, le=10000)
    max_concurrent_requests: int = Field(default=20, ge=1, le=100)
    model_timeout_seconds: float = Field(default=5, gt=0, le=30)
    model_failure_threshold: int = Field(default=3, ge=1, le=10)
    model_cooldown_seconds: float = Field(default=30, gt=0, le=300)
    scoring_enabled: bool = True
    writes_enabled: bool = True
    docs_enabled: bool = True
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]", "test"]
    # Fail closed: shared environments need an OIDC implementation in a later increment.
    environment: Literal["local", "test"] = "local"

    @field_validator("api_token")
    @classmethod
    def token_length(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value() and len(value.get_secret_value()) < 32:
            raise ValueError("API token must be empty (disabled) or at least 32 characters")
        return value

    @field_validator("allowed_domains")
    @classmethod
    def known_domains(cls, value: set[str]) -> set[str]:
        if not value <= {"ieee_cis", "home_credit", "elliptic"}:
            raise ValueError("Unknown allowed domain")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def exact_hosts(cls, value: list[str]) -> list[str]:
        if not value or any("*" in host or not host for host in value):
            raise ValueError("Use explicit trusted hosts; wildcards are not allowed")
        return value
