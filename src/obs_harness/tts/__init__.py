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
    KokoroSettings,
    create_tts_client,
    get_connect_kwargs,
)
from .elevenlabs_ws import ElevenLabsWSClient, ElevenLabsWSError
from .cartesia_ws import CartesiaWSClient, CartesiaWSError
from .cartesia import CartesiaClient, CartesiaError
from .kokoro import KokoroClient, KokoroError

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
    "KokoroSettings",
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
    # Kokoro client
    "KokoroClient",
    "KokoroError",
]
