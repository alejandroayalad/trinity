"""Explicit environment loading for trusted EIA connector code."""

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(ValueError):
    """A safe configuration error that contains no secret values."""


class EIASettings(BaseSettings):
    """EIA credentials; construction reads the process environment."""

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        hide_input_in_errors=True,
        frozen=True,
    )

    eia_api_key: SecretStr = Field(validation_alias="EIA_API_KEY")

    @field_validator("eia_api_key")
    @classmethod
    def require_nonblank_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("EIA_API_KEY must not be blank")
        return value


def load_eia_settings() -> EIASettings:
    """Load current environment values without caching or exposing credentials.

    Call this from trusted connector/worker code before an EIA operation.
    Package imports and the HTTP health endpoint do not require credentials.
    """
    try:
        return EIASettings()
    except ValidationError:
        raise ConfigurationError(
            "Set EIA_API_KEY to a non-empty value in the process environment."
        ) from None
