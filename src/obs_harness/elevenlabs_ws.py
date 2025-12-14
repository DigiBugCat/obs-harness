"""ElevenLabs WebSocket TTS streaming integration."""

import asyncio
import base64
import json
import os
from typing import AsyncIterator

import websockets

ELEVENLABS_WS_URL = "wss://api.elevenlabs.io/v1/text-to-speech"


class ElevenLabsWSError(Exception):
    """Error from ElevenLabs WebSocket API."""

    pass


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
    ) -> None:
        self.voice_id = voice_id
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise ValueError("ElevenLabs API key not provided.")

        self.model_id = model_id
        self.output_format = output_format
        self._ws = None
        self._receive_task = None
        self._audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._initialized = False
        self._closed = False

    @property
    def ws_url(self) -> str:
        """Construct the WebSocket URL with parameters."""
        return (
            f"{ELEVENLABS_WS_URL}/{self.voice_id}/stream-input"
            f"?model_id={self.model_id}&output_format={self.output_format}"
        )

    async def connect(
        self,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        speed: float = 1.0,
    ) -> None:
        """Connect to ElevenLabs WebSocket and initialize stream.

        Args:
            stability: Voice stability (0-1)
            similarity_boost: Voice similarity boost (0-1)
            style: Voice style (0-1)
            speed: Speech speed (0.5-2.0)
        """
        self._ws = await websockets.connect(self.ws_url)

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

    async def _receive_loop(self) -> None:
        """Background task to receive audio chunks from WebSocket."""
        try:
            async for message in self._ws:
                if self._closed:
                    break

                data = json.loads(message)

                # Check for final message
                if data.get("isFinal"):
                    await self._audio_queue.put(None)  # Signal end
                    break

                # Extract audio data (base64 encoded)
                audio_b64 = data.get("audio")
                if audio_b64:
                    audio_bytes = base64.b64decode(audio_b64)
                    await self._audio_queue.put(audio_bytes)

        except websockets.exceptions.ConnectionClosed:
            # Connection closed, signal end
            await self._audio_queue.put(None)
        except Exception as e:
            await self._audio_queue.put(None)
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
        """Iterate over received audio chunks.

        Yields:
            PCM audio bytes as they are received.
        """
        while True:
            chunk = await self._audio_queue.get()
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
