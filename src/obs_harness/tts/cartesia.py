"""Cartesia REST API client for voices and models."""

import os
from typing import Any

import httpx

CARTESIA_API_URL = "https://api.cartesia.ai"
CARTESIA_VERSION = "2024-06-10"


class CartesiaError(Exception):
    """Error from Cartesia API."""

    pass


class CartesiaClient:
    """Async client for Cartesia REST API."""

    def __init__(self, api_key: str | None = None) -> None:
        """Initialize Cartesia REST client.

        Args:
            api_key: Cartesia API key (falls back to CARTESIA_API_KEY env var)
        """
        self.api_key = api_key or os.environ.get("CARTESIA_API_KEY")
        if not self.api_key:
            raise ValueError("Cartesia API key not provided.")

        self._client = httpx.AsyncClient(
            base_url=CARTESIA_API_URL,
            headers={
                "X-API-Key": self.api_key,
                "Cartesia-Version": CARTESIA_VERSION,
            },
            timeout=30.0,
        )

    async def get_voices(self) -> list[dict[str, Any]]:
        """Get list of available voices.

        Returns:
            List of voice dictionaries with id, name, description, etc.
        """
        try:
            response = await self._client.get("/voices")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise CartesiaError(f"Failed to get voices: {e}") from e

    async def get_voice(self, voice_id: str) -> dict[str, Any]:
        """Get details for a specific voice.

        Args:
            voice_id: Cartesia voice ID

        Returns:
            Voice dictionary with id, name, description, language, etc.
        """
        try:
            response = await self._client.get(f"/voices/{voice_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise CartesiaError(f"Failed to get voice {voice_id}: {e}") from e

    async def get_models(self) -> list[dict[str, Any]]:
        """Get list of available TTS models.

        Note: Cartesia doesn't have a public models endpoint,
        so we return a static list of known models.

        Returns:
            List of model dictionaries with model_id, name, description.
        """
        # Cartesia models are not exposed via API, return known models
        return [
            {
                "model_id": "sonic-2024-12-12",
                "name": "Sonic",
                "description": "Latest generation TTS model with low latency and high quality",
                "languages": [
                    "en", "es", "fr", "de", "it", "pt", "pl", "zh", "ja", "ko",
                    "nl", "sv", "tr", "ru", "hi",
                ],
                "supports_timestamps": True,
            },
            {
                "model_id": "sonic-english",
                "name": "Sonic English",
                "description": "English-optimized TTS model",
                "languages": ["en"],
                "supports_timestamps": True,
            },
            {
                "model_id": "sonic-multilingual",
                "name": "Sonic Multilingual",
                "description": "Multilingual TTS model supporting 15+ languages",
                "languages": [
                    "en", "es", "fr", "de", "it", "pt", "pl", "zh", "ja", "ko",
                    "nl", "sv", "tr", "ru", "hi",
                ],
                "supports_timestamps": True,
            },
        ]

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "CartesiaClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
