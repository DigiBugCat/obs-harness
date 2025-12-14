"""Chat pipeline orchestrating LLM -> TTS -> Browser streaming."""

import asyncio
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

from .elevenlabs import ElevenLabsClient, WordTiming
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
    2. Buffers tokens until sentence boundaries
    3. Sends complete sentences to ElevenLabs TTS with timestamps
    4. Forwards audio chunks + word timing to browser
    5. Browser reveals words synced to audio playback
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
        send_word_timing: Callable[[list[dict]], Awaitable[bool]] | None = None,
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
            send_word_timing: Callback to send word timing data to browser
        """
        self.config = config
        self._send_text_start = send_text_start
        self._send_text_chunk = send_text_chunk
        self._send_text_end = send_text_end
        self._send_audio_start = send_audio_start
        self._send_audio_chunk = send_audio_chunk
        self._send_audio_end = send_audio_end
        self._send_word_timing = send_word_timing

        self._sentence_buffer = ""
        self._full_response = ""
        self._cancelled = False
        self._audio_time_offset = 0.0  # Accumulated audio time across sentences

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

        # Start text stream to browser (for word-synced reveal)
        if self.config.show_text:
            await self._send_text_start()

        # Queue for sentences to be processed by TTS
        sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()

        async with OpenRouterClient() as llm_client:
            async with ElevenLabsClient() as tts_client:
                # Start audio stream to browser
                await self._send_audio_start()

                # Start TTS processing task
                tts_task = asyncio.create_task(
                    self._process_tts_queue(tts_client, sentence_queue)
                )

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

                        # Check for sentence boundary
                        if SENTENCE_END.search(self._sentence_buffer):
                            # Queue sentence for TTS processing
                            await sentence_queue.put(self._sentence_buffer)
                            self._sentence_buffer = ""

                    # Flush remaining buffer
                    if self._sentence_buffer:
                        await sentence_queue.put(self._sentence_buffer)

                    # Signal end of sentences
                    await sentence_queue.put(None)

                except Exception as e:
                    await sentence_queue.put(None)
                    raise e

                finally:
                    # Wait for TTS to finish
                    await tts_task

        # End streams
        await self._send_audio_end()
        if self.config.show_text:
            await self._send_text_end()

        return self._full_response

    async def _process_tts_queue(
        self,
        tts_client: ElevenLabsClient,
        sentence_queue: asyncio.Queue[str | None],
    ) -> None:
        """Process sentences from queue through TTS with timestamps.

        Args:
            tts_client: The ElevenLabs client
            sentence_queue: Queue of sentences to process
        """
        while True:
            sentence = await sentence_queue.get()
            if sentence is None:
                break

            if self._cancelled:
                continue

            try:
                # Track the max end time for this sentence to update offset
                sentence_max_time = 0.0

                async for chunk in tts_client.stream_tts_with_timestamps(
                    voice_id=self.config.voice_id,
                    text=sentence,
                    stability=self.config.voice_stability,
                    similarity_boost=self.config.voice_similarity_boost,
                    style=self.config.voice_style,
                    speed=self.config.voice_speed,
                ):
                    if self._cancelled:
                        break

                    # Send audio to browser
                    if chunk.audio:
                        await self._send_audio_chunk(chunk.audio)

                    # Send word timing to browser (with offset applied)
                    if chunk.words and self._send_word_timing and self.config.show_text:
                        # Apply time offset and track max time
                        adjusted_words = []
                        for word in chunk.words:
                            adjusted_words.append({
                                "word": word.word,
                                "start": word.start_time + self._audio_time_offset,
                                "end": word.end_time + self._audio_time_offset,
                            })
                            sentence_max_time = max(
                                sentence_max_time,
                                word.end_time
                            )

                        await self._send_word_timing(adjusted_words)

                # Update offset for next sentence
                self._audio_time_offset += sentence_max_time

            except Exception as e:
                print(f"TTS error for sentence: {e}")
                # Continue with next sentence

    def cancel(self) -> None:
        """Cancel the pipeline gracefully."""
        self._cancelled = True
