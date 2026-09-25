from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RISK_", env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://risk_local:risk_local@localhost:55432/risk_platform"
    )
    api_token: SecretStr = SecretStr("")
    operator_id: str = "local-investigator"
    # Fail closed: shared environments need an OIDC implementation in a later increment.
    environment: Literal["local", "test"] = "local"

    @field_validator("api_token")
    @classmethod
    def token_length(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value() and len(value.get_secret_value()) < 32:
            raise ValueError("API token must be empty (disabled) or at least 32 characters")
        return value
