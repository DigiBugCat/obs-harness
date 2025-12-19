"""ElevenLabs WebSocket TTS streaming integration.

DEPRECATED: This module is kept for backwards compatibility.
Import from obs_harness.tts instead:

    from obs_harness.tts import ElevenLabsWSClient, ElevenLabsWSError
    from obs_harness.tts import WordTiming, AudioChunkWithTiming
"""

# Re-export everything from the new location for backwards compatibility
from .tts.elevenlabs_ws import (
    ElevenLabsWSClient,
    ElevenLabsWSError,
    ParseResult,
    parse_alignment_to_words,
)
from .tts.provider import (
    WordTiming,
    AudioChunkWithTiming,
)

__all__ = [
    "ElevenLabsWSClient",
    "ElevenLabsWSError",
    "WordTiming",
    "AudioChunkWithTiming",
    "ParseResult",
    "parse_alignment_to_words",
]
