"""Chat pipeline orchestrating LLM -> TTS -> Browser streaming."""

import logging
import time
from dataclasses import dataclass
from typing import AsyncIterator

from .openrouter import OpenRouterClient
from .tts_pipeline import TTSStreamer

logger = logging.getLogger(__name__)


@dataclass
class ChatPipelineConfig:
    """Configuration for chat pipeline (LLM settings only)."""

    system_prompt: str
    model: str = "anthropic/claude-sonnet-4.5"
    provider: str | list[str] | None = None  # OpenRouter provider routing
    temperature: float = 0.7
    max_tokens: int = 1024
    twitch_chat_context: str | None = None  # Recent Twitch chat to inject
    conversation_history: list[dict] | None = None  # Past messages for memory
    images: list[dict] | None = None  # Images for vision: [{data, media_type}]


class ChatPipeline:
    """Orchestrates LLM streaming -> TTS -> Browser audio + text.

    This pipeline:
    1. Builds LLM messages (system prompt, history, twitch context)
    2. Creates async generator for LLM tokens
    3. Delegates TTS streaming to TTSStreamer
    """

    def __init__(
        self,
        config: ChatPipelineConfig,
        tts_streamer: TTSStreamer,
    ):
        """Initialize the chat pipeline.

        Args:
            config: LLM configuration (system prompt, model, etc.)
            tts_streamer: Unified TTS streamer for audio + text
        """
        self.config = config
        self._tts_streamer = tts_streamer
        self._cancelled = False

    async def run(self, user_message: str) -> str:
        """Execute the full pipeline.

        Args:
            user_message: The user's message to send to the LLM

        Returns:
            The complete response text from the LLM
        """
        start_time = time.time()
        msg_preview = user_message[:40] + "..." if len(user_message) > 40 else user_message
        logger.debug(f"Pipeline starting - model={self.config.model}, message=\"{msg_preview}\"")

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

        # Build user message - multimodal if images present
        if self.config.images:
            content: list[dict] = [{"type": "text", "text": user_message}]
            for img in self.config.images:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{img['media_type']};base64,{img['data']}"}
                })
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_message})

        # Create LLM client (kept alive to access usage after streaming)
        llm_client = OpenRouterClient()

        # Create async generator that yields LLM tokens
        async def llm_tokens() -> AsyncIterator[str]:
            async for token in llm_client.stream_chat(
                messages=messages,
                model=self.config.model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                provider=self.config.provider,
            ):
                if self._cancelled:
                    break
                yield token

        try:
            # Delegate to TTSStreamer with token iterator
            result = await self._tts_streamer.stream(llm_tokens())

            # Log with model, token usage, and cost
            elapsed = time.time() - start_time
            usage = llm_client.last_usage
            model_short = self.config.model.split("/")[-1]  # e.g., "claude-sonnet-4" from "anthropic/claude-sonnet-4"

            if usage:
                cost_str = f"${usage.cost:.4f}" if usage.cost else "?"
                tokens_str = f"{usage.prompt_tokens}+{usage.completion_tokens} tokens"
                if self._cancelled:
                    logger.info(f"LLM cancelled - {model_short} - {tokens_str} - {cost_str}")
                else:
                    logger.info(f"LLM complete - {model_short} - {tokens_str} - {cost_str} in {elapsed:.2f}s")
            else:
                if self._cancelled:
                    logger.info(f"LLM cancelled - {model_short}")
                else:
                    logger.info(f"LLM complete - {model_short} - {len(result)} chars in {elapsed:.2f}s")

            return result
        finally:
            await llm_client.close()

    async def cancel(self) -> None:
        """Cancel the pipeline - stops LLM and TTS immediately."""
        self._cancelled = True
        await self._tts_streamer.cancel()

    def get_spoken_text(self) -> str:
        """Get the text that was actually spoken (converted to audio)."""
        return self._tts_streamer.get_spoken_text()
