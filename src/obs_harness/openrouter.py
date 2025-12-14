"""OpenRouter LLM integration with streaming support."""

import json
import os
from typing import AsyncIterator

import httpx
from httpx_sse import aconnect_sse

OPENROUTER_API_URL = "https://openrouter.ai/api/v1"


class OpenRouterError(Exception):
    """Error from OpenRouter API."""

    pass


class OpenRouterClient:
    """Async client for OpenRouter API with streaming support."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key not provided.")

        self._client = httpx.AsyncClient(
            base_url=OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=120.0,  # LLM responses can be slow
        )

    async def stream_chat(
        self,
        messages: list[dict],
        model: str = "anthropic/claude-sonnet-4.5",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """Stream chat completion tokens.

        Yields:
            Text content tokens as they arrive.
        """
        async with aconnect_sse(
            self._client,
            "POST",
            "/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "stream": True,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        ) as event_source:
            async for event in event_source.aiter_sse():
                if event.data == "[DONE]":
                    break
                if event.data.startswith(":"):
                    continue  # OpenRouter keep-alive comment

                try:
                    data = json.loads(event.data)
                    if "error" in data:
                        raise OpenRouterError(
                            data["error"].get("message", "Unknown error")
                        )

                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "OpenRouterClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
