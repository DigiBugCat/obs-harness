"""Centralized configuration for OBS Harness.

All environment variables are validated at import time.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Keys (optional - validated at usage time based on TTS provider)
    openrouter_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    cartesia_api_key: str | None = None

    # Kokoro TTS (self-hosted, no API key required)
    kokoro_base_url: str = Field(default="http://kokoro:8880")

    # Twitch OAuth
    twitch_client_id: str = Field(default="h1x5odjr6qy1m8sesgev1p9wcssz63")
    twitch_client_secret: str | None = None
    twitch_redirect_uri: str = Field(default="http://localhost:8080/auth/callback")

    # Auth - comma-separated list of allowed Twitch user IDs
    allowed_twitch_ids: str = Field(default="")

    # Feature flags
    dev_mode: bool = Field(default=False)  # Enables dev login button on login page

    @property
    def allowed_twitch_ids_set(self) -> set[str]:
        """Parse allowed Twitch IDs into a set."""
        if not self.allowed_twitch_ids:
            return set()
        return {tid.strip() for tid in self.allowed_twitch_ids.split(",") if tid.strip()}

    def has_elevenlabs(self) -> bool:
        """Check if ElevenLabs API key is configured."""
        return bool(self.elevenlabs_api_key)

    def has_cartesia(self) -> bool:
        """Check if Cartesia API key is configured."""
        return bool(self.cartesia_api_key)

    def has_openrouter(self) -> bool:
        """Check if OpenRouter API key is configured."""
        return bool(self.openrouter_api_key)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()


# Convenience export for direct access
settings = get_settings()
