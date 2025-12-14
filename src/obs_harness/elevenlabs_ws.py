"""ElevenLabs WebSocket TTS streaming integration."""

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass
from typing import AsyncIterator

import websockets

logger = logging.getLogger(__name__)

ELEVENLABS_WS_URL = "wss://api.elevenlabs.io/v1/text-to-speech"


class ElevenLabsWSError(Exception):
    """Error from ElevenLabs WebSocket API."""

    pass


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


@dataclass
class ParseResult:
    """Result from parsing alignment with potential incomplete word."""

    words: list[WordTiming]  # Complete words
    pending: dict | None  # Incomplete word at end: {"word": str, "start_ms": int, "end_ms": int}


def parse_alignment_to_words(
    chars: list[str],
    start_times_ms: list[int],
    durations_ms: list[int],
    pending_word: dict | None = None,
) -> ParseResult:
    """Convert character-level alignment to word-level timing.

    Handles words split across chunk boundaries by accepting and returning
    pending incomplete words.

    Punctuation is attached to the preceding word (e.g., "hello!" is one word).

    Args:
        chars: List of individual characters
        start_times_ms: Start time for each character in milliseconds
        durations_ms: Duration for each character in milliseconds
        pending_word: Incomplete word from previous chunk (optional)

    Returns:
        ParseResult with complete words and any new pending incomplete word
    """
    if not chars:
        return ParseResult(words=[], pending=pending_word)

    words = []
    current_word = ""
    word_start_ms = None
    word_end_ms = None

    # Check if first char continues a word from previous chunk
    first_char_continues_word = not chars[0].isspace() if chars else False

    # If we have a pending word and first char continues it, start with pending
    if pending_word and first_char_continues_word:
        current_word = pending_word["word"]
        word_start_ms = pending_word["start_ms"]
        word_end_ms = pending_word["end_ms"]
        pending_word = None  # Consumed
    elif pending_word:
        # Pending word is complete (next chunk starts with space/new word)
        words.append(WordTiming(
            word=pending_word["word"],
            start_time=pending_word["start_ms"] / 1000.0,
            end_time=pending_word["end_ms"] / 1000.0,
        ))
        pending_word = None

    for i, char in enumerate(chars):
        if char.isspace():
            # End of word - save if we have one
            if current_word and word_start_ms is not None:
                words.append(WordTiming(
                    word=current_word,
                    start_time=word_start_ms / 1000.0,
                    end_time=word_end_ms / 1000.0,
                ))
                current_word = ""
                word_start_ms = None
                word_end_ms = None
        else:
            # Part of a word (letters, numbers, or punctuation)
            if word_start_ms is None:
                word_start_ms = start_times_ms[i]
            current_word += char
            # Update end time to include this character
            word_end_ms = start_times_ms[i] + (durations_ms[i] if i < len(durations_ms) else 0)

    # Check if chunk ends mid-word (no trailing space)
    ends_mid_word = current_word and (not chars or not chars[-1].isspace())

    if ends_mid_word and current_word and word_start_ms is not None:
        # This word might continue in the next chunk - mark as pending
        new_pending = {
            "word": current_word,
            "start_ms": word_start_ms,
            "end_ms": word_end_ms,
        }
        return ParseResult(
            words=[w for w in words if any(c.isalnum() for c in w.word)],
            pending=new_pending,
        )
    elif current_word and word_start_ms is not None:
        # Word ended with the chunk (trailing space) - it's complete
        words.append(WordTiming(
            word=current_word,
            start_time=word_start_ms / 1000.0,
            end_time=word_end_ms / 1000.0,
        ))

    # Filter out punctuation-only "words" (e.g., standalone "!" or "?")
    words = [w for w in words if any(c.isalnum() for c in w.word)]

    return ParseResult(words=words, pending=None)


class ElevenLabsWSClient:
    """WebSocket client for ElevenLabs streaming TTS.

    Allows sending text chunks as they arrive and receiving audio chunks back,
    enabling lower latency than HTTP streaming for real-time use cases.
    """

    def __init__(
        self,
        voice_id: str,
        api_key: str | None = None,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = "pcm_24000",
        sync_alignment: bool = True,
    ) -> None:
        self.voice_id = voice_id
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ElevenLabs API key not provided.")

        self.model_id = model_id
        self.output_format = output_format
        self.sync_alignment = sync_alignment
        self._ws = None
        self._receive_task = None
        self._chunk_queue: asyncio.Queue[AudioChunkWithTiming | None] = asyncio.Queue()
        self._initialized = False
        self._closed = False
        # Buffer for incomplete word at chunk boundary
        self._pending_word: dict | None = None  # {"word": str, "start_ms": int, "end_ms": int}

    @property
    def ws_url(self) -> str:
        """Construct the WebSocket URL with parameters."""
        url = (
            f"{ELEVENLABS_WS_URL}/{self.voice_id}/stream-input"
            f"?model_id={self.model_id}&output_format={self.output_format}"
        )
        if self.sync_alignment:
            url += "&sync_alignment=true"
        return url

    async def connect(
        self,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        speed: float = 1.0,
        max_retries: int = 3,
    ) -> None:
        """Connect to ElevenLabs WebSocket and initialize stream.

        Args:
            stability: Voice stability (0-1)
            similarity_boost: Voice similarity boost (0-1)
            style: Voice style (0-1)
            speed: Speech speed (0.5-2.0)
            max_retries: Number of connection attempts before failing

        Raises:
            ElevenLabsWSError: If connection fails after retries.
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                # Reset pending word state on new connection
                self._pending_word = None

                self._ws = await websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                )

                # Send initialization message (BOS - Beginning of Stream)
                init_message = {
                    "text": " ",  # Required initial text (space is minimal)
                    "voice_settings": {
                        "stability": stability,
                        "similarity_boost": similarity_boost,
                        "style": style,
                        "speed": speed,
                    },
                    "generation_config": {
                        # Chunk length schedule determines buffering before generation
                        # Lower values = lower latency but potentially lower quality
                        "chunk_length_schedule": [120, 160, 250, 290],
                    },
                    "xi-api-key": self.api_key,
                }
                await self._ws.send(json.dumps(init_message))
                self._initialized = True

                # Start background receiver task
                self._receive_task = asyncio.create_task(self._receive_loop())
                return  # Success

            except Exception as e:
                last_error = e
                if self._ws:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None

                if attempt < max_retries - 1:
                    delay = 1.0 * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"ElevenLabs WS connection failed (attempt {attempt + 1}): {e}, retrying in {delay}s...")
                    await asyncio.sleep(delay)

        raise ElevenLabsWSError(f"Failed to connect after {max_retries} attempts: {last_error}")

    async def _receive_loop(self) -> None:
        """Background task to receive audio chunks from WebSocket."""
        try:
            async for message in self._ws:
                if self._closed:
                    break

                data = json.loads(message)

                # Check for final message
                if data.get("isFinal"):
                    # Flush any pending word before signaling end
                    if self._pending_word:
                        final_word = WordTiming(
                            word=self._pending_word["word"],
                            start_time=self._pending_word["start_ms"] / 1000.0,
                            end_time=self._pending_word["end_ms"] / 1000.0,
                        )
                        # Only emit if it has alphanumeric content
                        if any(c.isalnum() for c in final_word.word):
                            logger.debug(f"Final pending word: {final_word.word}")
                            await self._chunk_queue.put(AudioChunkWithTiming(
                                audio=b"",
                                words=[final_word],
                            ))
                        self._pending_word = None
                    await self._chunk_queue.put(None)  # Signal end
                    break

                # Extract audio data (base64 encoded)
                audio_b64 = data.get("audio")
                audio_bytes = base64.b64decode(audio_b64) if audio_b64 else b""

                # Extract alignment data if present
                words = []
                alignment = data.get("alignment") or data.get("normalizedAlignment")
                if alignment:
                    chars = alignment.get("chars", [])
                    start_times = alignment.get("charStartTimesMs", [])
                    durations = alignment.get("charDurationsMs", [])
                    logger.debug(f"Alignment: chars={''.join(chars)}, start_times={start_times[:5]}...")
                    if chars and start_times:
                        result = parse_alignment_to_words(chars, start_times, durations, self._pending_word)
                        words = result.words
                        self._pending_word = result.pending
                        if result.pending:
                            logger.debug(f"Pending word buffered: '{result.pending['word']}'")
                        logger.debug(f"Parsed words: {[(w.word, w.start_time) for w in words]}")

                if audio_bytes or words:
                    await self._chunk_queue.put(AudioChunkWithTiming(
                        audio=audio_bytes,
                        words=words,
                    ))

        except websockets.exceptions.ConnectionClosed:
            # Connection closed, signal end
            await self._chunk_queue.put(None)
        except Exception as e:
            await self._chunk_queue.put(None)
            if not self._closed:
                raise ElevenLabsWSError(f"Receive error: {e}")

    async def send_text(self, text: str, flush: bool = False) -> None:
        """Send text chunk to be converted to speech.

        Args:
            text: Text to convert to speech
            flush: If True, forces generation of buffered text
        """
        if not self._initialized:
            raise ElevenLabsWSError("Not connected. Call connect() first.")

        message = {
            "text": text,
            "try_trigger_generation": True,
        }
        if flush:
            message["flush"] = True

        await self._ws.send(json.dumps(message))

    async def close_input(self) -> None:
        """Signal end of text input (EOS - End of Stream).

        After calling this, no more text can be sent, and the server
        will finish generating any remaining audio.
        """
        if self._ws and self._initialized:
            # Send empty text to signal end of input
            await self._ws.send(json.dumps({"text": ""}))

    async def iter_audio(self) -> AsyncIterator[bytes]:
        """Iterate over received audio chunks (audio only, no timing).

        Yields:
            PCM audio bytes as they are received.
        """
        async for chunk in self.iter_audio_with_timing():
            if chunk.audio:
                yield chunk.audio

    async def iter_audio_with_timing(self) -> AsyncIterator[AudioChunkWithTiming]:
        """Iterate over received audio chunks with word timing.

        Yields:
            AudioChunkWithTiming objects containing audio and word timing.
        """
        while True:
            chunk = await self._chunk_queue.get()
            if chunk is None:
                break
            yield chunk

    async def close(self) -> None:
        """Close WebSocket connection and cleanup."""
        self._closed = True

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._ws:
            await self._ws.close()

    async def __aenter__(self) -> "ElevenLabsWSClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
