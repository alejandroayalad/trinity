"""Explicit environment loading for trusted connector and storage code."""

from dataclasses import dataclass, field
import os
import re
from urllib.parse import urlsplit

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


@dataclass(frozen=True)
class S3Settings:
    """Hold trusted storage routing, never credentials or client-supplied paths.

    Use an existing private bucket and a nonempty relative prefix. Credentials
    come from the SDK provider when the adapter is explicitly constructed.
    Construction checks syntax; it cannot prove bucket permissions or privacy.
    repr=False keeps infrastructure locations out of incidental object output.
    """

    bucket: str = field(repr=False)
    prefix: str = field(repr=False)
    region: str = field(repr=False)
    endpoint_url: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        from trinity.contracts.manifest import safe_relative_path

        try:
            # Support ordinary DNS bucket names, not ARNs or directory buckets.
            # Restrict this slice to an explicit, reviewable S3 configuration.
            if (type(self.bucket) is not str
                    or re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", self.bucket) is None
                    or ".." in self.bucket or ".-" in self.bucket or "-." in self.bucket
                    or re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", self.bucket)
                    or self.bucket.endswith(("--x-s3", "--ol-s3", ".mrap"))):
                raise ValueError
            safe_relative_path(self.prefix)
            if (len(self.prefix.encode("utf-8")) > 512
                    or type(self.region) is not str
                    or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)+", self.region) is None):
                raise ValueError
            if self.endpoint_url is not None:
                endpoint = urlsplit(self.endpoint_url)
                # HTTPS avoids sending SDK authorization over plain text.
                # A local alternative must also supply a trusted TLS endpoint.
                if (endpoint.scheme != "https" or not endpoint.hostname
                        or endpoint.username is not None or endpoint.password is not None
                        or endpoint.query or endpoint.fragment
                        or endpoint.path not in ("", "/")
                        or "?" in self.endpoint_url or "#" in self.endpoint_url
                        or any(char.isspace() or ord(char) < 32 for char in self.endpoint_url)):
                    raise ValueError
                endpoint.port  # Validate a supplied port without retaining it.
        except (ValueError, TypeError, AttributeError):
            raise ConfigurationError("Invalid trusted S3 configuration.") from None


def load_s3_settings() -> S3Settings:
    """Load explicit storage routing at invocation; do not read a .env file.

    Missing or invalid settings raise a safe error. This function makes no
    network requests and does not resolve credentials or create a bucket.
    """
    try:
        return S3Settings(
            bucket=os.environ["TRINITY_S3_BUCKET"], prefix=os.environ["TRINITY_S3_PREFIX"],
            region=os.environ["TRINITY_S3_REGION"],
            endpoint_url=os.environ.get("TRINITY_S3_ENDPOINT_URL"),
        )
    except (KeyError, ConfigurationError):
        raise ConfigurationError("Set valid trusted TRINITY_S3 settings.") from None


class ApiSettings(BaseSettings):
    """Read API-only PostgreSQL configuration without loading connector secrets."""

    model_config = SettingsConfigDict(
        case_sensitive=True, env_file=None, hide_input_in_errors=True, frozen=True,
    )
    database_url: SecretStr = Field(validation_alias="TRINITY_DATABASE_URL", repr=False)

    @field_validator("database_url")
    @classmethod
    def require_database_url(cls, value: SecretStr) -> SecretStr:
        url = urlsplit(value.get_secret_value())
        if url.scheme not in ("postgres", "postgresql") or not url.path.strip("/"):
            raise ValueError("Invalid PostgreSQL URL")
        return value


def load_api_settings() -> ApiSettings:
    """Load API settings and hide all invalid secret-bearing input."""
    try:
        return ApiSettings()
    except (ValidationError, ValueError):
        raise ConfigurationError("Set a valid TRINITY_DATABASE_URL in the process environment.") from None
