"""Kokoro HTTP TTS streaming integration.

Kokoro is a self-hosted TTS model via Kokoro-FastAPI.
See: https://github.com/remsky/Kokoro-FastAPI
"""

import asyncio
import base64
import logging
from typing import AsyncIterator

import httpx

from ..config import settings
from .provider import AudioChunkWithTiming, WordTiming

logger = logging.getLogger(__name__)


class KokoroError(Exception):
    """Error from Kokoro API."""

    pass


class KokoroClient:
    """HTTP client for Kokoro-FastAPI streaming TTS.

    Implements the TTSProviderClient protocol for compatibility
    with the unified TTS pipeline.

    Unlike WebSocket-based providers, Kokoro uses HTTP streaming
    via the OpenAI-compatible /v1/audio/speech endpoint.
    """

    def __init__(
        self,
        voice: str = "af_heart",
        base_url: str | None = None,
        sample_rate: int = 24000,
    ) -> None:
        """Initialize Kokoro client.

        Args:
            voice: Kokoro voice ID (e.g., "af_heart", "bf_emma")
            base_url: Kokoro-FastAPI base URL (falls back to config)
            sample_rate: Audio sample rate in Hz
        """
        self.voice = voice
        self.base_url = base_url or settings.kokoro_base_url
        self.sample_rate = sample_rate

        self._client: httpx.AsyncClient | None = None
        self._chunk_queue: asyncio.Queue[AudioChunkWithTiming | None] | None = None
        self._closed = False
        self._text_buffer: list[str] = []
        self._stream_task: asyncio.Task | None = None

        # Voice settings (set during connect)
        self._speed: float = 1.0

    async def connect(
        self,
        speed: float = 1.0,
        **kwargs,  # Ignore unknown settings for protocol compatibility
    ) -> None:
        """Initialize the HTTP client.

        Args:
            speed: Speech speed multiplier (0.5-2.0)
        """
        self._speed = speed
        self._closed = False
        self._text_buffer = []
        self._chunk_queue = asyncio.Queue()

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
        )

    async def send_text(self, text: str, flush: bool = False) -> None:
        """Buffer text for TTS generation.

        Args:
            text: Text to convert to speech
            flush: If True, immediately start generation (not used for Kokoro)
        """
        if self._closed:
            raise KokoroError("Client is closed.")

        self._text_buffer.append(text)

    async def close_input(self) -> None:
        """Signal end of input and start TTS generation.

        For Kokoro, we batch all text and generate at once since
        it uses HTTP rather than streaming WebSocket input.
        """
        if not self._client or self._closed:
            return

        full_text = "".join(self._text_buffer)
        if not full_text.strip():
            await self._chunk_queue.put(None)
            return

        # Start streaming in background task
        self._stream_task = asyncio.create_task(
            self._stream_audio(full_text)
        )

    async def _stream_audio(self, text: str) -> None:
        """Stream audio from Kokoro-FastAPI.

        Uses the /v1/audio/speech endpoint with streaming response.
        """
        try:
            # Request PCM audio for streaming
            response = await self._client.post(
                "/v1/audio/speech",
                json={
                    "model": "kokoro",
                    "input": text,
                    "voice": self.voice,
                    "response_format": "pcm",
                    "speed": self._speed,
                },
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Kokoro error: {response.status_code} - {error_text}")
                await self._chunk_queue.put(None)
                raise KokoroError(f"Kokoro API error: {response.status_code}")

            # Stream audio chunks
            audio_data = response.content
            chunk_size = 4096  # ~85ms at 24kHz

            for i in range(0, len(audio_data), chunk_size):
                if self._closed:
                    break
                chunk = audio_data[i:i + chunk_size]
                await self._chunk_queue.put(AudioChunkWithTiming(
                    audio=chunk,
                    words=[],  # No word timing in streaming mode
                ))

            await self._chunk_queue.put(None)

        except httpx.RequestError as e:
            logger.error(f"Kokoro request error: {e}")
            await self._chunk_queue.put(None)
            raise KokoroError(f"Connection error: {e}")

    async def _generate_with_timing(self, text: str) -> None:
        """Generate audio with word-level timestamps.

        Uses the /dev/captioned_speech endpoint for word timing.
        This is non-streaming but provides accurate timing data.
        """
        try:
            response = await self._client.post(
                "/dev/captioned_speech",
                json={
                    "model": "kokoro",
                    "input": text,
                    "voice": self.voice,
                    "speed": self._speed,
                },
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(f"Kokoro captioned error: {response.status_code}")
                await self._chunk_queue.put(None)
                raise KokoroError(f"Kokoro API error: {response.status_code}")

            data = response.json()
            audio_b64 = data.get("audio", "")
            timestamps = data.get("timestamps", [])

            audio_bytes = base64.b64decode(audio_b64) if audio_b64 else b""

            # Convert timestamps to WordTiming objects
            words = []
            for ts in timestamps:
                words.append(WordTiming(
                    word=ts.get("word", ""),
                    start_time=ts.get("start", 0.0),
                    end_time=ts.get("end", 0.0),
                ))

            # Send all audio with timing in one chunk
            await self._chunk_queue.put(AudioChunkWithTiming(
                audio=audio_bytes,
                words=words,
            ))
            await self._chunk_queue.put(None)

        except httpx.RequestError as e:
            logger.error(f"Kokoro captioned request error: {e}")
            await self._chunk_queue.put(None)
            raise KokoroError(f"Connection error: {e}")

    async def iter_audio_with_timing(self) -> AsyncIterator[AudioChunkWithTiming]:
        """Iterate over audio chunks with timing.

        Yields:
            AudioChunkWithTiming objects containing audio and word timing.
        """
        while True:
            chunk = await self._chunk_queue.get()
            if chunk is None:
                break
            yield chunk

    async def close(self) -> None:
        """Close HTTP client."""
        self._closed = True

        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass

        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "KokoroClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @classmethod
    async def get_voices(cls, base_url: str | None = None) -> list[dict]:
        """Get list of available Kokoro voices.

        Args:
            base_url: Kokoro-FastAPI base URL (falls back to config)

        Returns:
            List of voice dictionaries with id and name.
        """
        url = base_url or settings.kokoro_base_url
        async with httpx.AsyncClient(
            base_url=url,
            timeout=httpx.Timeout(30.0, connect=10.0),
        ) as client:
            try:
                response = await client.get("/v1/audio/voices")
                if response.status_code != 200:
                    raise KokoroError(f"Failed to get voices: {response.status_code}")

                data = response.json()
                voices = data.get("voices", [])

                # Transform to consistent format
                # Kokoro API returns list of strings like ["af_alloy", "af_heart", ...]
                result = []
                for v in voices:
                    if isinstance(v, str):
                        result.append({"id": v, "name": v})
                    else:
                        result.append({
                            "id": v.get("voice_id", v.get("id", "")),
                            "name": v.get("name", v.get("voice_id", ""))
                        })
                return result
            except httpx.RequestError as e:
                raise KokoroError(f"Connection error: {e}")
