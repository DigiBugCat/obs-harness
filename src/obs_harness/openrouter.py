"""OpenRouter LLM integration with streaming support."""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import AsyncIterator

import httpx
from httpx_sse import aconnect_sse

logger = logging.getLogger(__name__)


@dataclass
class StreamUsage:
    """Usage statistics from a streaming completion."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float | None = None  # USD cost if available

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
        self.last_usage: StreamUsage | None = None  # Populated after streaming

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
                logger.warning(f"OpenRouter error (attempt {attempt + 1}): {e}, retrying in {delay}s...")
                await asyncio.sleep(delay)

            except httpx.HTTPError as e:
                last_error = OpenRouterError(f"HTTP error: {e}", retryable=True)
                if attempt == self.max_retries - 1:
                    raise last_error

                delay = self.retry_delay * (2 ** attempt)
                logger.warning(f"OpenRouter HTTP error (attempt {attempt + 1}): {e}, retrying in {delay}s...")
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
            "usage": {"include": True},  # Get cost in response
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

                    # Capture usage from final chunk (OpenRouter includes it in last event)
                    if "usage" in data:
                        usage = data["usage"]
                        self.last_usage = StreamUsage(
                            prompt_tokens=usage.get("prompt_tokens", 0),
                            completion_tokens=usage.get("completion_tokens", 0),
                            total_tokens=usage.get("total_tokens", 0),
                            cost=usage.get("cost"),  # USD cost
                        )

                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    async def chat(
        self,
        messages: list[dict],
        model: str = "anthropic/claude-sonnet-4.5",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        provider: str | list[str] | None = None,
        response_format: dict | None = None,
    ) -> str:
        """Non-streaming chat completion with optional structured output.

        Args:
            messages: List of chat messages
            model: Model identifier (e.g., "moonshotai/kimi-k2-0905")
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            provider: Provider routing (same as stream_chat)
            response_format: Optional response format for structured outputs.
                Example for JSON schema:
                {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response_name",
                        "strict": True,
                        "schema": { ... }
                    }
                }

        Returns:
            Complete response text.

        Raises:
            OpenRouterError: If the API request fails after retries.
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return await self._chat_attempt(
                    messages, model, temperature, max_tokens, provider, response_format
                )
            except OpenRouterError as e:
                last_error = e
                if not e.retryable or attempt == self.max_retries - 1:
                    raise

                delay = self.retry_delay * (2 ** attempt)
                logger.warning(f"OpenRouter error (attempt {attempt + 1}): {e}, retrying in {delay}s...")
                await asyncio.sleep(delay)

            except httpx.HTTPError as e:
                last_error = OpenRouterError(f"HTTP error: {e}", retryable=True)
                if attempt == self.max_retries - 1:
                    raise last_error

                delay = self.retry_delay * (2 ** attempt)
                logger.warning(f"OpenRouter HTTP error (attempt {attempt + 1}): {e}, retrying in {delay}s...")
                await asyncio.sleep(delay)

        if last_error:
            raise last_error
        raise OpenRouterError("Unknown error in chat()")

    async def _chat_attempt(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
        provider: str | list[str] | None,
        response_format: dict | None,
    ) -> str:
        """Single attempt at non-streaming chat completion."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "usage": {"include": True},
        }

        # Add provider routing if specified
        if provider:
            provider_order = [provider] if isinstance(provider, str) else provider
            payload["provider"] = {
                "order": provider_order,
                "allow_fallbacks": False,
            }

        # Add response format for structured outputs
        if response_format:
            payload["response_format"] = response_format

        response = await self._client.post("/chat/completions", json=payload)

        if response.status_code != 200:
            status = response.status_code
            retryable = status in RETRYABLE_STATUS_CODES
            raise OpenRouterError(
                f"API returned status {status}",
                status_code=status,
                retryable=retryable,
            )

        data = response.json()

        # Check for error in response
        if "error" in data:
            error_msg = data["error"].get("message", "Unknown error")
            error_code = data["error"].get("code")
            retryable = error_code in ("rate_limit_exceeded", "server_error")
            raise OpenRouterError(error_msg, retryable=retryable)

        # Capture usage
        if "usage" in data:
            usage = data["usage"]
            self.last_usage = StreamUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                cost=usage.get("cost"),
            )

        # Extract content
        choices = data.get("choices", [])
        if not choices:
            raise OpenRouterError("No choices in response")

        content = choices[0].get("message", {}).get("content", "")
        return content

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
