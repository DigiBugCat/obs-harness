"""Chat pipeline orchestrating LLM -> TTS -> Browser streaming."""

import asyncio
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from .elevenlabs_ws import ElevenLabsWSClient
from .openrouter import OpenRouterClient

# Sentence boundary pattern - matches end of sentences
SENTENCE_END = re.compile(r"[.!?]\s*$|[\n]")


@dataclass
class ChatPipelineConfig:
    """Configuration for chat pipeline."""

    character_name: str
    system_prompt: str
    voice_id: str
    channel: str
    model: str = "anthropic/claude-sonnet-4.5"
    temperature: float = 0.7
    max_tokens: int = 1024
    voice_stability: float = 0.5
    voice_similarity_boost: float = 0.75
    voice_style: float = 0.0
    voice_speed: float = 1.0
    show_text: bool = True
    twitch_chat_context: str | None = None  # Recent Twitch chat to inject
    conversation_history: list[dict] | None = None  # Past messages for memory


class ChatPipeline:
    """Orchestrates LLM streaming -> TTS -> Browser audio + text.

    This pipeline:
    1. Streams tokens from OpenRouter LLM
    2. Sends each token to browser for text display (progressive reveal)
    3. Buffers tokens until sentence boundaries
    4. Sends complete sentences to ElevenLabs WebSocket TTS
    5. Forwards audio chunks to browser for playback
    """

    def __init__(
        self,
        config: ChatPipelineConfig,
        send_text_start: Callable[[], Awaitable[bool]],
        send_text_chunk: Callable[[str], Awaitable[bool]],
        send_text_end: Callable[[], Awaitable[bool]],
        send_audio_start: Callable[[], Awaitable[bool]],
        send_audio_chunk: Callable[[bytes], Awaitable[bool]],
        send_audio_end: Callable[[], Awaitable[bool]],
    ):
        """Initialize the chat pipeline.

        Args:
            config: Pipeline configuration
            send_text_start: Callback to start text streaming on browser
            send_text_chunk: Callback to send text chunk to browser
            send_text_end: Callback to end text streaming on browser
            send_audio_start: Callback to start audio streaming on browser
            send_audio_chunk: Callback to send audio chunk to browser
            send_audio_end: Callback to end audio streaming on browser
        """
        self.config = config
        self._send_text_start = send_text_start
        self._send_text_chunk = send_text_chunk
        self._send_text_end = send_text_end
        self._send_audio_start = send_audio_start
        self._send_audio_chunk = send_audio_chunk
        self._send_audio_end = send_audio_end

        self._sentence_buffer = ""
        self._full_response = ""
        self._cancelled = False

    async def run(self, user_message: str) -> str:
        """Execute the full pipeline.

        Args:
            user_message: The user's message to send to the LLM

        Returns:
            The complete response text from the LLM
        """
        # Build system prompt with optional Twitch chat context
        system_content = self.config.system_prompt
        if self.config.twitch_chat_context:
            system_content = f"""{self.config.system_prompt}

---
Recent Twitch chat (you can see what viewers are saying):
{self.config.twitch_chat_context}"""

        # Build messages with optional conversation history
        messages = [{"role": "system", "content": system_content}]
        if self.config.conversation_history:
            messages.extend(self.config.conversation_history)
        messages.append({"role": "user", "content": user_message})

        # Start text stream to browser
        if self.config.show_text:
            await self._send_text_start()

        async with OpenRouterClient() as llm_client:
            async with ElevenLabsWSClient(self.config.voice_id) as tts_client:
                # Connect to ElevenLabs
                await tts_client.connect(
                    stability=self.config.voice_stability,
                    similarity_boost=self.config.voice_similarity_boost,
                    style=self.config.voice_style,
                    speed=self.config.voice_speed,
                )

                # Start audio stream to browser
                await self._send_audio_start()

                # Start audio forwarding task
                audio_task = asyncio.create_task(self._forward_audio(tts_client))

                # Process LLM tokens
                try:
                    async for token in llm_client.stream_chat(
                        messages=messages,
                        model=self.config.model,
                        temperature=self.config.temperature,
                        max_tokens=self.config.max_tokens,
                    ):
                        if self._cancelled:
                            break

                        self._full_response += token
                        self._sentence_buffer += token

                        # Send token to browser for text display
                        if self.config.show_text:
                            await self._send_text_chunk(token)

                        # Check for sentence boundary
                        if SENTENCE_END.search(self._sentence_buffer):
                            # Send complete sentence to TTS
                            await tts_client.send_text(self._sentence_buffer)
                            self._sentence_buffer = ""

                    # Flush remaining buffer
                    if self._sentence_buffer:
                        await tts_client.send_text(self._sentence_buffer, flush=True)

                    # Signal end of text input to TTS
                    await tts_client.close_input()

                except Exception as e:
                    # On error, still try to clean up
                    try:
                        await tts_client.close_input()
                    except Exception:
                        pass
                    raise e

                finally:
                    # Wait for audio to finish
                    await audio_task

        # End streams
        await self._send_audio_end()
        if self.config.show_text:
            await self._send_text_end()

        return self._full_response

    async def _forward_audio(self, tts_client: ElevenLabsWSClient) -> None:
        """Forward audio chunks from TTS to browser.

        Args:
            tts_client: The ElevenLabs WebSocket client to receive audio from
        """
        try:
            async for audio_chunk in tts_client.iter_audio():
                if self._cancelled:
                    break
                await self._send_audio_chunk(audio_chunk)
        except Exception:
            # Audio forwarding failed, but don't crash the pipeline
            pass

    def cancel(self) -> None:
        """Cancel the pipeline gracefully."""
        self._cancelled = True
