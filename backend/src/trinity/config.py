"""Explicit environment loading for trusted EIA connector code."""

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(ValueError):
    """A safe configuration error that contains no secret values."""


class EIASettings(BaseSettings):
    """EIA credentials; construction reads the process environment."""

    # Read the exact environment variable name, not a local .env file.
    # Hide rejected values in validation errors and prevent later field replacement.
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=None,
        hide_input_in_errors=True,
        frozen=True,
    )

    # SecretStr masks normal output. Trusted request code must explicitly unwrap it.
    eia_api_key: SecretStr = Field(validation_alias="EIA_API_KEY")

    # Pydantic runs this class-level validator after converting the input to SecretStr.
    @field_validator("eia_api_key")
    @classmethod
    def require_nonblank_key(cls, value: SecretStr) -> SecretStr:
        """Reject whitespace-only keys without changing the supplied secret."""
        # Use stripping only to detect blanks; preserve the original credential bytes.
        if not value.get_secret_value().strip():
            raise ValueError("EIA_API_KEY must not be blank")
        return value


def load_eia_settings() -> EIASettings:
    """Load current environment values without caching or exposing credentials.

    Trusted connector code calls this before an EIA operation. Build fresh settings
    from EIA_API_KEY and return the key in a masked SecretStr field.
    Raise ConfigurationError for missing, blank, or invalid settings.
    This checks local configuration only; it does not verify the key with EIA.
    Package imports and the HTTP health endpoint do not require credentials.
    """
    try:
        return EIASettings()
    except ValidationError:
        # Replace Pydantic's details with safe guidance. "from None" hides the
        # original validation exception when Python displays the traceback.
        raise ConfigurationError(
            "Set EIA_API_KEY to a non-empty value in the process environment."
        ) from None
