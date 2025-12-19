"""Cartesia WebSocket TTS streaming integration."""

import asyncio
import base64
import json
import logging
import os
import uuid
from typing import AsyncIterator

import websockets

from .provider import AudioChunkWithTiming, WordTiming

logger = logging.getLogger(__name__)

CARTESIA_WS_URL = "wss://api.cartesia.ai/tts/websocket"
CARTESIA_VERSION = "2024-06-10"


class CartesiaWSError(Exception):
    """Error from Cartesia WebSocket API."""

    pass


class CartesiaWSClient:
    """WebSocket client for Cartesia streaming TTS.

    Implements the TTSProviderClient protocol for compatibility
    with the unified TTS pipeline.
    """

    def __init__(
        self,
        voice_id: str,
        api_key: str | None = None,
        model_id: str = "sonic-2024-12-12",
        language: str = "en",
        output_format: str = "pcm_s16le",
        sample_rate: int = 24000,
    ) -> None:
        """Initialize Cartesia WebSocket client.

        Args:
            voice_id: Cartesia voice ID
            api_key: Cartesia API key (falls back to CARTESIA_API_KEY env var)
            model_id: TTS model ID (default: sonic-2024-12-12)
            language: Language code (default: en)
            output_format: Audio encoding format
            sample_rate: Audio sample rate in Hz
        """
        self.voice_id = voice_id
        self.api_key = api_key or os.environ.get("CARTESIA_API_KEY")
        if not self.api_key:
            raise ValueError("Cartesia API key not provided.")

        self.model_id = model_id
        self.language = language
        self.output_format = output_format
        self.sample_rate = sample_rate

        self._ws = None
        self._receive_task = None
        self._chunk_queue: asyncio.Queue[AudioChunkWithTiming | None] = asyncio.Queue()
        self._context_id: str | None = None
        self._closed = False
        self._input_ended = False

        # Voice settings (set during connect)
        self._speed: float | None = None
        self._emotion: str | None = None

    @property
    def ws_url(self) -> str:
        """Construct WebSocket URL with auth."""
        return f"{CARTESIA_WS_URL}?cartesia_version={CARTESIA_VERSION}&api_key={self.api_key}"

    async def connect(
        self,
        speed: float | None = None,
        emotion: str | None = None,
        max_retries: int = 3,
        **kwargs,  # Ignore unknown settings for protocol compatibility
    ) -> None:
        """Connect to Cartesia WebSocket.

        Args:
            speed: Speech speed multiplier (optional)
            emotion: Emotion control (optional)
            max_retries: Number of connection attempts before failing
        """
        self._speed = speed
        self._emotion = emotion
        self._context_id = str(uuid.uuid4())
        self._input_ended = False

        last_error = None
        for attempt in range(max_retries):
            try:
                self._ws = await websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                )
                self._receive_task = asyncio.create_task(self._receive_loop())
                return
            except Exception as e:
                last_error = e
                if self._ws:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

                if attempt < max_retries - 1:
                    delay = 1.0 * (2 ** attempt)
                    logger.warning(f"Cartesia WS connection failed (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(delay)

        raise CartesiaWSError(f"Failed to connect after {max_retries} attempts: {last_error}")

    def _build_message(self, text: str, is_final: bool = False) -> dict:
        """Build a Cartesia WebSocket message.

        Args:
            text: Text to convert to speech
            is_final: Whether this is the final text chunk

        Returns:
            Message dict ready to be JSON-encoded
        """
        message = {
            "model_id": self.model_id,
            "transcript": text,
            "voice": {"mode": "id", "id": self.voice_id},
            "language": self.language,
            "context_id": self._context_id,
            "output_format": {
                "container": "raw",
                "encoding": self.output_format,
                "sample_rate": self.sample_rate,
            },
            "add_timestamps": True,
            "continue": not is_final,
        }

        # Add speed via generation_config (numeric 0.6-1.5)
        if self._speed is not None:
            # Clamp speed to Cartesia's valid range
            clamped_speed = max(0.6, min(1.5, self._speed))
            if clamped_speed != self._speed:
                logger.warning(f"Cartesia speed {self._speed} clamped to {clamped_speed} (valid: 0.6-1.5)")
            message["generation_config"] = {"speed": clamped_speed}

        # Add optional emotion controls (still uses __experimental_controls)
        if self._emotion is not None:
            message["voice"]["__experimental_controls"] = {"emotion": [self._emotion]}

        return message

    async def send_text(self, text: str, flush: bool = False) -> None:
        """Send text to Cartesia for TTS.

        Args:
            text: Text to convert to speech
            flush: If True, this is treated as final input for this generation
        """
        if not self._ws:
            raise CartesiaWSError("Not connected. Call connect() first.")

        if self._input_ended:
            raise CartesiaWSError("Input already ended. Cannot send more text.")

        message = self._build_message(text, is_final=flush)
        await self._ws.send(json.dumps(message))

    async def close_input(self) -> None:
        """Signal end of input by sending final message with continue=False."""
        if self._ws and self._context_id and not self._input_ended:
            self._input_ended = True
            # Send empty transcript with continue=False to finalize
            message = self._build_message("", is_final=True)
            await self._ws.send(json.dumps(message))

    async def _receive_loop(self) -> None:
        """Background task to receive audio from WebSocket."""
        pending_audio: list[bytes] = []
        pending_words: list[WordTiming] = []

        try:
            async for message in self._ws:
                if self._closed:
                    break

                data = json.loads(message)
                msg_type = data.get("type")
                context_id = data.get("context_id")

                # Only process messages for our context
                if context_id != self._context_id:
                    continue

                if msg_type == "chunk":
                    # Audio chunk
                    audio_b64 = data.get("data", "")
                    if audio_b64:
                        audio_bytes = base64.b64decode(audio_b64)
                        pending_audio.append(audio_bytes)

                        # Emit chunk if we have audio (even without timing yet)
                        # This keeps audio flowing with low latency
                        if pending_audio and not pending_words:
                            audio = b"".join(pending_audio)
                            await self._chunk_queue.put(AudioChunkWithTiming(
                                audio=audio,
                                words=[],
                            ))
                            pending_audio = []

                elif msg_type == "timestamps":
                    # Word timing data
                    ts_data = data.get("word_timestamps", {})
                    words = ts_data.get("words", [])
                    starts = ts_data.get("start", [])
                    ends = ts_data.get("end", [])

                    for word, start, end in zip(words, starts, ends):
                        pending_words.append(WordTiming(
                            word=word,
                            start_time=start,
                            end_time=end,
                        ))

                    # Emit chunk with accumulated audio and words
                    if pending_audio or pending_words:
                        audio = b"".join(pending_audio)
                        await self._chunk_queue.put(AudioChunkWithTiming(
                            audio=audio,
                            words=pending_words,
                        ))
                        pending_audio = []
                        pending_words = []

                elif msg_type == "done":
                    # Generation complete
                    # Flush any remaining audio
                    if pending_audio or pending_words:
                        await self._chunk_queue.put(AudioChunkWithTiming(
                            audio=b"".join(pending_audio),
                            words=pending_words,
                        ))
                    await self._chunk_queue.put(None)  # Signal end
                    break

                elif msg_type == "error":
                    error_msg = data.get("message", "Unknown error")
                    error_code = data.get("code", "unknown")
                    logger.error(f"Cartesia error [{error_code}]: {error_msg}")
                    await self._chunk_queue.put(None)
                    raise CartesiaWSError(f"[{error_code}] {error_msg}")

        except websockets.exceptions.ConnectionClosed:
            await self._chunk_queue.put(None)
        except Exception as e:
            await self._chunk_queue.put(None)
            if not self._closed:
                raise CartesiaWSError(f"Receive error: {e}")

    async def iter_audio(self) -> AsyncIterator[bytes]:
        """Iterate over received audio chunks (audio only, no timing).

        Yields:
            PCM audio bytes as they are received.
        """
        async for chunk in self.iter_audio_with_timing():
            if chunk.audio:
                yield chunk.audio

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
        """Close WebSocket connection."""
        self._closed = True

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()

    async def __aenter__(self) -> "CartesiaWSClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
