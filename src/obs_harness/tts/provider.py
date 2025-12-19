"""TTS provider abstraction layer.

This module defines the protocol and factory for TTS providers,
allowing the system to swap between ElevenLabs, Cartesia, and
future providers.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, AsyncIterator

from pydantic import BaseModel, Field


class TTSProviderType(str, Enum):
    """Supported TTS providers."""

    ELEVENLABS = "elevenlabs"
    CARTESIA = "cartesia"


# -----------------------------------------------------------------------------
# Shared data structures (used by all providers)
# -----------------------------------------------------------------------------


@dataclass
class WordTiming:
    """Timing information for a single word."""

    word: str
    start_time: float  # seconds from audio start
    end_time: float


@dataclass
class AudioChunkWithTiming:
    """Audio chunk with optional word timing."""

    audio: bytes
    words: list[WordTiming]


# -----------------------------------------------------------------------------
# Provider settings schemas (for JSON blob validation)
# -----------------------------------------------------------------------------


class ElevenLabsSettings(BaseModel):
    """ElevenLabs-specific voice settings."""

    voice_id: str = Field(min_length=1)  # Voice ID is required
    model_id: str = "eleven_multilingual_v2"
    stability: float = Field(default=0.5, ge=0.0, le=1.0)
    similarity_boost: float = Field(default=0.75, ge=0.0, le=1.0)
    style: float = Field(default=0.0, ge=0.0, le=1.0)
    speed: float = Field(default=1.0, ge=0.7, le=1.2)


class CartesiaSettings(BaseModel):
    """Cartesia-specific voice settings."""

    voice_id: str = Field(min_length=1)  # Voice ID is required
    model_id: str = "sonic-2024-12-12"  # Sonic latest (not "sonic-3")
    language: str = "en"
    speed: float = Field(default=1.0, ge=0.6, le=1.5)  # Cartesia valid range: 0.6-1.5
    emotion: str | None = None  # Optional emotion control


# -----------------------------------------------------------------------------
# TTS Provider Protocol
# -----------------------------------------------------------------------------


class TTSProviderClient(Protocol):
    """Protocol for TTS provider WebSocket clients.

    Both ElevenLabs and Cartesia implement this interface.
    """

    async def connect(self, **settings: Any) -> None:
        """Connect to TTS WebSocket and initialize with voice settings.

        Args:
            **settings: Provider-specific voice settings
        """
        ...

    async def send_text(self, text: str, flush: bool = False) -> None:
        """Send text chunk to be converted to speech.

        Args:
            text: Text to convert
            flush: Force generation of buffered text
        """
        ...

    async def close_input(self) -> None:
        """Signal end of text input (EOS)."""
        ...

    async def iter_audio_with_timing(self) -> AsyncIterator[AudioChunkWithTiming]:
        """Iterate over received audio chunks with word timing.

        Yields:
            AudioChunkWithTiming with PCM audio and word timing
        """
        ...

    async def close(self) -> None:
        """Close WebSocket connection and cleanup."""
        ...


# -----------------------------------------------------------------------------
# Factory function
# -----------------------------------------------------------------------------


def create_tts_client(
    provider: TTSProviderType,
    settings: dict[str, Any],
) -> TTSProviderClient:
    """Create a TTS client for the specified provider.

    Args:
        provider: The TTS provider type
        settings: Provider-specific settings dict

    Returns:
        Configured TTS client implementing TTSProviderClient

    Raises:
        ValueError: If provider is not supported
    """
    if provider == TTSProviderType.ELEVENLABS:
        from .elevenlabs_ws import ElevenLabsWSClient

        validated = ElevenLabsSettings(**settings)
        return ElevenLabsWSClient(
            voice_id=validated.voice_id,
            model_id=validated.model_id,
            sync_alignment=True,
        )
    elif provider == TTSProviderType.CARTESIA:
        from .cartesia_ws import CartesiaWSClient

        validated = CartesiaSettings(**settings)
        return CartesiaWSClient(
            voice_id=validated.voice_id,
            model_id=validated.model_id,
            language=validated.language,
        )
    else:
        raise ValueError(f"Unsupported TTS provider: {provider}")


def get_connect_kwargs(
    provider: TTSProviderType,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Extract connect() kwargs from settings for a provider.

    Args:
        provider: The TTS provider type
        settings: Provider-specific settings dict

    Returns:
        Dict of kwargs to pass to client.connect()
    """
    if provider == TTSProviderType.ELEVENLABS:
        validated = ElevenLabsSettings(**settings)
        return {
            "stability": validated.stability,
            "similarity_boost": validated.similarity_boost,
            "style": validated.style,
            "speed": validated.speed,
        }
    elif provider == TTSProviderType.CARTESIA:
        validated = CartesiaSettings(**settings)
        return {
            "speed": validated.speed,
            "emotion": validated.emotion,
        }
    else:
        return {}
