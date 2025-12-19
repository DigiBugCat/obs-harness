"""TTS provider package.

This package provides a unified interface for TTS providers,
allowing the system to swap between ElevenLabs, Cartesia, and
future providers.
"""

from .provider import (
    TTSProviderType,
    TTSProviderClient,
    WordTiming,
    AudioChunkWithTiming,
    ElevenLabsSettings,
    CartesiaSettings,
    create_tts_client,
    get_connect_kwargs,
)
from .elevenlabs_ws import ElevenLabsWSClient, ElevenLabsWSError
from .cartesia_ws import CartesiaWSClient, CartesiaWSError
from .cartesia import CartesiaClient, CartesiaError

__all__ = [
    # Provider types and protocol
    "TTSProviderType",
    "TTSProviderClient",
    # Shared data structures
    "WordTiming",
    "AudioChunkWithTiming",
    # Settings schemas
    "ElevenLabsSettings",
    "CartesiaSettings",
    # Factory
    "create_tts_client",
    "get_connect_kwargs",
    # ElevenLabs client
    "ElevenLabsWSClient",
    "ElevenLabsWSError",
    # Cartesia clients
    "CartesiaWSClient",
    "CartesiaWSError",
    "CartesiaClient",
    "CartesiaError",
]
