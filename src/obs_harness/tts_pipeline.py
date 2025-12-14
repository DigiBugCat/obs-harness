"""Unified TTS streaming pipeline for browser audio + text synchronization."""

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable, Union

from .elevenlabs_ws import ElevenLabsWSClient, ElevenLabsWSError


@dataclass
class TTSStreamConfig:
    """Voice configuration for TTS streaming."""

    voice_id: str
    model_id: str = "eleven_multilingual_v2"
    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
    speed: float = 1.0


@dataclass
class TextDisplayConfig:
    """Text display settings for browser overlay."""

    font_family: str = "Arial"
    font_size: int = 48
    color: str = "#ffffff"
    stroke_color: str | None = None
    stroke_width: int = 0
    position_x: float = 0.5
    position_y: float = 0.5


class TTSStreamer:
    """Unified TTS streaming to browser with word-synced text.

    Handles the complete flow:
    1. text_stream_start (before audio, if show_text)
    2. stream_start (audio)
    3. Audio chunks + word timing interleaved
    4. stream_end
    5. text_stream_end (if show_text)

    Works with both:
    - Full text strings (Speak endpoint)
    - Async iterators (Chat endpoint with LLM streaming)
    """

    def __init__(
        self,
        tts_config: TTSStreamConfig,
        text_config: TextDisplayConfig,
        show_text: bool,
        # Browser callbacks
        send_text_start: Callable[[], Awaitable[bool]],
        send_text_end: Callable[[], Awaitable[bool]],
        send_audio_start: Callable[[], Awaitable[bool]],
        send_audio_chunk: Callable[[bytes], Awaitable[bool]],
        send_audio_end: Callable[[], Awaitable[bool]],
        send_word_timing: Callable[[list[dict]], Awaitable[bool]],
    ) -> None:
        """Initialize the TTS streamer.

        Args:
            tts_config: Voice configuration
            text_config: Text display settings
            show_text: Whether to show text overlay
            send_text_start: Callback to start text streaming on browser
            send_text_end: Callback to end text streaming on browser
            send_audio_start: Callback to start audio streaming on browser
            send_audio_chunk: Callback to send audio chunk to browser
            send_audio_end: Callback to end audio streaming on browser
            send_word_timing: Callback to send word timing data to browser
        """
        self._tts_config = tts_config
        self._text_config = text_config
        self._show_text = show_text

        self._send_text_start = send_text_start
        self._send_text_end = send_text_end
        self._send_audio_start = send_audio_start
        self._send_audio_chunk = send_audio_chunk
        self._send_audio_end = send_audio_end
        self._send_word_timing = send_word_timing

        self._cancelled = False
        self._spoken_text = ""  # Text that was actually converted to audio
        self._tts_client: ElevenLabsWSClient | None = None  # For cancellation
        self._receive_task: asyncio.Task | None = None

    async def stream(self, text_source: Union[str, AsyncIterator[str]]) -> str:
        """Stream TTS audio with word timing to browser.

        Args:
            text_source: Either a complete string or async iterator of tokens

        Returns:
            The complete text that was spoken

        Raises:
            ElevenLabsWSError: If TTS connection or streaming fails
        """
        text_started = False
        audio_started = False
        self._spoken_text = ""  # Reset for new stream

        try:
            # 1. Start text stream FIRST (required order for browser)
            if self._show_text:
                await self._send_text_start()
                text_started = True

            # 2. Create and connect TTS client
            self._tts_client = ElevenLabsWSClient(
                voice_id=self._tts_config.voice_id,
                model_id=self._tts_config.model_id,
                sync_alignment=True,
            )

            try:
                await self._tts_client.connect(
                    stability=self._tts_config.stability,
                    similarity_boost=self._tts_config.similarity_boost,
                    style=self._tts_config.style,
                    speed=self._tts_config.speed,
                )

                # 3. Start audio stream
                await self._send_audio_start()
                audio_started = True

                # 4. Start receive task for audio + word timing
                self._receive_task = asyncio.create_task(
                    self._receive_audio(self._tts_client)
                )

                # 5. Send text to TTS (string or iterator)
                if isinstance(text_source, str):
                    await self._tts_client.send_text(text_source)
                    full_text = text_source
                else:
                    full_text = ""
                    async for token in text_source:
                        if self._cancelled:
                            break
                        full_text += token
                        await self._tts_client.send_text(token)

                # 6. Close TTS input and wait for audio to finish
                if not self._cancelled:
                    await self._tts_client.close_input()
                    await self._receive_task

            finally:
                await self._tts_client.close()
                self._tts_client = None
                self._receive_task = None

            # 7. End streams (audio first, then text)
            await self._send_audio_end()
            audio_started = False

            if self._show_text:
                await self._send_text_end()
                text_started = False

            return full_text

        except Exception:
            # Cleanup on error
            if audio_started:
                await self._send_audio_end()
            if text_started:
                await self._send_text_end()
            raise

    async def _receive_audio(self, tts_client: ElevenLabsWSClient) -> None:
        """Receive audio and word timing from TTS WebSocket.

        Args:
            tts_client: The ElevenLabs WebSocket client
        """
        try:
            async for chunk in tts_client.iter_audio_with_timing():
                if self._cancelled:
                    break

                # Send word timing BEFORE audio so browser can sync
                if chunk.words:
                    # Accumulate spoken text (what was actually converted to audio)
                    for w in chunk.words:
                        if self._spoken_text and not self._spoken_text.endswith(" "):
                            self._spoken_text += " "
                        self._spoken_text += w.word

                    if self._show_text:
                        words_data = [
                            {
                                "word": w.word,
                                "start": w.start_time,
                                "end": w.end_time,
                            }
                            for w in chunk.words
                        ]
                        await self._send_word_timing(words_data)

                # Send audio to browser
                if chunk.audio:
                    await self._send_audio_chunk(chunk.audio)

        except Exception as e:
            print(f"TTS receive error: {e}")

    async def cancel(self) -> None:
        """Cancel the streaming - closes WebSocket immediately."""
        self._cancelled = True
        # Close the TTS WebSocket to stop receiving audio
        if self._tts_client:
            await self._tts_client.close()
        # Cancel the receive task
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

    def get_spoken_text(self) -> str:
        """Get the text that was actually spoken (converted to audio)."""
        return self._spoken_text
