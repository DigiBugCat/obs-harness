"""ElevenLabs TTS integration for OBS Harness."""

import os
from typing import AsyncIterator

import httpx

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"


class ElevenLabsError(Exception):
    """Error from ElevenLabs API."""

    pass


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
