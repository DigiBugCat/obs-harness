"""OpenRouter LLM integration with streaming support."""

import asyncio
import json
import os
from typing import AsyncIterator

import httpx
from httpx_sse import aconnect_sse

OPENROUTER_API_URL = "https://openrouter.ai/api/v1"

# Transient HTTP errors worth retrying
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class OpenRouterError(Exception):
    """Error from OpenRouter API."""

    def __init__(self, message: str, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class OpenRouterClient:
    """Async client for OpenRouter API with streaming support."""

    def __init__(
        self,
        api_key: str | None = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key not provided.")

        self.max_retries = max_retries
        self.retry_delay = retry_delay

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
        provider: str | list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat completion tokens.

        Args:
            messages: List of chat messages
            model: Model identifier (e.g., "anthropic/claude-sonnet-4.5")
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            provider: Provider routing - can be:
                - Single provider string (e.g., "Anthropic")
                - List of providers in preference order (e.g., ["Anthropic", "Google"])
                - None to use OpenRouter's default routing

        Yields:
            Text content tokens as they arrive.

        Raises:
            OpenRouterError: If the API request fails after retries.
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                async for token in self._stream_chat_attempt(
                    messages, model, temperature, max_tokens, provider
                ):
                    yield token
                return  # Success, exit retry loop

            except OpenRouterError as e:
                last_error = e
                if not e.retryable or attempt == self.max_retries - 1:
                    raise

                delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                print(f"OpenRouter error (attempt {attempt + 1}): {e}, retrying in {delay}s...")
                await asyncio.sleep(delay)

            except httpx.HTTPError as e:
                last_error = OpenRouterError(f"HTTP error: {e}", retryable=True)
                if attempt == self.max_retries - 1:
                    raise last_error

                delay = self.retry_delay * (2 ** attempt)
                print(f"OpenRouter HTTP error (attempt {attempt + 1}): {e}, retrying in {delay}s...")
                await asyncio.sleep(delay)

        if last_error:
            raise last_error

    async def _stream_chat_attempt(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
        provider: str | list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Single attempt at streaming chat completion."""
        # Build request payload
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        # Add provider routing if specified
        if provider:
            provider_order = [provider] if isinstance(provider, str) else provider
            payload["provider"] = {
                "order": provider_order,
                "allow_fallbacks": False,  # Strict provider selection
            }

        async with aconnect_sse(
            self._client,
            "POST",
            "/chat/completions",
            json=payload,
        ) as event_source:
            # Check response status
            if event_source.response.status_code != 200:
                status = event_source.response.status_code
                retryable = status in RETRYABLE_STATUS_CODES
                raise OpenRouterError(
                    f"API returned status {status}",
                    status_code=status,
                    retryable=retryable,
                )

            async for event in event_source.aiter_sse():
                if event.data == "[DONE]":
                    break
                if event.data.startswith(":"):
                    continue  # OpenRouter keep-alive comment

                try:
                    data = json.loads(event.data)
                    if "error" in data:
                        error_msg = data["error"].get("message", "Unknown error")
                        error_code = data["error"].get("code")
                        # Rate limits and server errors are retryable
                        retryable = error_code in ("rate_limit_exceeded", "server_error")
                        raise OpenRouterError(error_msg, retryable=retryable)

                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    async def get_model_providers(self, model: str) -> list[str]:
        """Get available providers for a model.

        Args:
            model: Model identifier (e.g., "anthropic/claude-sonnet-4.5")

        Returns:
            List of provider names that can serve this model.
        """
        try:
            response = await self._client.get(f"/models/{model}")
            if response.status_code != 200:
                return []

            data = response.json()
            # Extract provider names from the endpoint info
            endpoints = data.get("data", {}).get("endpoints", [])
            providers = []
            for endpoint in endpoints:
                provider = endpoint.get("provider_name") or endpoint.get("name")
                if provider and provider not in providers:
                    providers.append(provider)
            return providers

        except Exception:
            return []

    async def list_models(self) -> list[dict]:
        """List all available models.

        Returns:
            List of model info dictionaries.
        """
        try:
            response = await self._client.get("/models")
            if response.status_code != 200:
                return []

            data = response.json()
            return data.get("data", [])

        except Exception:
            return []

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "OpenRouterClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
