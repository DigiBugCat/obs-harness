"""ElevenLabs TTS integration for OBS Harness."""

import base64
import json
import os
from dataclasses import dataclass
from typing import AsyncIterator

import httpx

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


class ElevenLabsError(Exception):
    """Error from ElevenLabs API."""

    pass


@dataclass
class WordTiming:
    """Timing information for a single word."""

    word: str
    start_time: float  # seconds from audio start
    end_time: float


@dataclass
class TTSChunkWithTiming:
    """A TTS audio chunk with optional word timing data."""

    audio: bytes  # PCM audio data
    words: list[WordTiming]  # Words in this chunk with timing


def parse_alignment_to_words(
    characters: list[str],
    start_times: list[float],
    end_times: list[float],
) -> list[WordTiming]:
    """Convert character-level alignment to word-level timing.

    Args:
        characters: List of individual characters
        start_times: Start time for each character in seconds
        end_times: End time for each character in seconds

    Returns:
        List of WordTiming objects, one per word
    """
    if not characters:
        return []

    words = []
    current_word = ""
    word_start = None

    for i, char in enumerate(characters):
        if char.isspace():
            # End of word
            if current_word:
                words.append(WordTiming(
                    word=current_word,
                    start_time=word_start,
                    end_time=end_times[i - 1] if i > 0 else start_times[i],
                ))
                current_word = ""
                word_start = None
        else:
            # Part of a word
            if word_start is None:
                word_start = start_times[i]
            current_word += char

    # Don't forget the last word
    if current_word:
        words.append(WordTiming(
            word=current_word,
            start_time=word_start,
            end_time=end_times[-1] if end_times else 0,
        ))

    return words


class ElevenLabsClient:
    """Async client for ElevenLabs TTS API with streaming support."""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize the client.

        Args:
            api_key: ElevenLabs API key. If not provided, reads from
                     ELEVENLABS_API_KEY environment variable.

        Raises:
            ValueError: If no API key is provided or found in environment.
        """
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ElevenLabs API key not provided. Set ELEVENLABS_API_KEY environment variable."
            )
        self._client = httpx.AsyncClient(
            base_url=ELEVENLABS_API_URL,
            headers={"xi-api-key": self.api_key},
            timeout=30.0,
        )

    async def stream_tts(
        self,
        voice_id: str,
        text: str,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
    ) -> AsyncIterator[bytes]:
        """Stream TTS audio as PCM chunks.

        Args:
            voice_id: ElevenLabs voice ID to use.
            text: Text to convert to speech.
            model_id: ElevenLabs model to use.
            output_format: Audio output format (pcm_24000 for 24kHz 16-bit PCM).

        Yields:
            Raw PCM audio bytes in chunks.

        Raises:
            ElevenLabsError: If the API request fails.
        """
        try:
            async with self._client.stream(
                "POST",
                f"/text-to-speech/{voice_id}/stream",
                json={
                    "text": text,
                    "model_id": model_id,
                },
                params={
                    "output_format": output_format,
                },
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise ElevenLabsError(
                        f"ElevenLabs API error {response.status_code}: {error_text.decode()}"
                    )
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    yield chunk
        except httpx.HTTPError as e:
            raise ElevenLabsError(f"HTTP error during TTS streaming: {e}") from e

    async def stream_tts_with_timestamps(
        self,
        voice_id: str,
        text: str,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        speed: float = 1.0,
    ) -> AsyncIterator[TTSChunkWithTiming]:
        """Stream TTS audio with word-level timing data.

        Uses the stream-with-timestamps endpoint to get alignment data.

        Args:
            voice_id: ElevenLabs voice ID to use.
            text: Text to convert to speech.
            model_id: ElevenLabs model to use.
            output_format: Audio output format.
            stability: Voice stability (0-1).
            similarity_boost: Voice similarity boost (0-1).
            style: Voice style (0-1).
            speed: Speech speed (0.5-2.0).

        Yields:
            TTSChunkWithTiming objects containing audio and word timing.

        Raises:
            ElevenLabsError: If the API request fails.
        """
        try:
            async with self._client.stream(
                "POST",
                f"/text-to-speech/{voice_id}/stream-with-timestamps",
                json={
                    "text": text,
                    "model_id": model_id,
                    "voice_settings": {
                        "stability": stability,
                        "similarity_boost": similarity_boost,
                        "style": style,
                        "speed": speed,
                    },
                },
                params={
                    "output_format": output_format,
                },
            ) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise ElevenLabsError(
                        f"ElevenLabs API error {response.status_code}: {error_text.decode()}"
                    )

                # Response is newline-delimited JSON
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk

                    # Process complete JSON objects
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Extract audio (base64 encoded)
                        audio_b64 = data.get("audio_base64", "")
                        audio_bytes = base64.b64decode(audio_b64) if audio_b64 else b""

                        # Extract alignment and convert to word timing
                        words = []
                        alignment = data.get("alignment") or data.get("normalized_alignment")
                        if alignment:
                            chars = alignment.get("characters", [])
                            starts = alignment.get("character_start_times_seconds", [])
                            ends = alignment.get("character_end_times_seconds", [])
                            words = parse_alignment_to_words(chars, starts, ends)

                        if audio_bytes or words:
                            yield TTSChunkWithTiming(audio=audio_bytes, words=words)

        except httpx.HTTPError as e:
            raise ElevenLabsError(f"HTTP error during TTS streaming: {e}") from e

    async def get_voices(self) -> list[dict]:
        """Get list of available voices.

        Returns:
            List of voice dictionaries with id, name, etc.
        """
        response = await self._client.get("/voices")
        response.raise_for_status()
        data = response.json()
        return data.get("voices", [])

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "ElevenLabsClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


def estimate_tts_duration_ms(text: str, words_per_minute: int = 150) -> int:
    """Estimate TTS audio duration based on word count.

    Args:
        text: The text to be spoken.
        words_per_minute: Average speaking rate (default 150 WPM).

    Returns:
        Estimated duration in milliseconds.
    """
    word_count = len(text.split())
    # words / (words/min) = minutes -> * 60 * 1000 = milliseconds
    duration_ms = int((word_count / words_per_minute) * 60 * 1000)
    # Minimum 1 second, maximum 5 minutes
    return max(1000, min(duration_ms, 300000))
