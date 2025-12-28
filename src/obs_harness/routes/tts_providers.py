"""TTS provider API routes.

Handles ElevenLabs, Cartesia, and OpenRouter model/voice lookups.
"""

import struct

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from ..auth import require_auth
from ..config import settings
from ..elevenlabs import ElevenLabsClient, ElevenLabsError
from ..openrouter import OpenRouterClient

router = APIRouter(tags=["TTS Providers"])


# -------------------------------------------------------------------------
# OpenRouter API endpoints
# -------------------------------------------------------------------------


@router.get("/api/openrouter/models/{model:path}/providers")
async def get_model_providers(model: str, tenant_id: str = Depends(require_auth)) -> dict:
    """Get available providers for an OpenRouter model.

    Args:
        model: Model identifier (e.g., "anthropic/claude-sonnet-4.5")

    Returns:
        List of provider names that can serve this model.
    """
    if not settings.has_openrouter():
        return {"providers": []}

    async with OpenRouterClient() as client:
        providers = await client.get_model_providers(model)
        return {"providers": providers}


# -------------------------------------------------------------------------
# ElevenLabs API endpoints
# -------------------------------------------------------------------------


@router.get("/api/elevenlabs/models")
async def list_elevenlabs_models(tenant_id: str = Depends(require_auth)) -> list[dict]:
    """Get list of available ElevenLabs TTS models.

    Returns models that support text-to-speech with their capabilities.
    """
    try:
        async with ElevenLabsClient() as client:
            models = await client.get_models()
            # Filter to only TTS-capable models and return relevant info
            tts_models = []
            for m in models:
                if m.get("can_do_text_to_speech"):
                    tts_models.append({
                        "model_id": m.get("model_id"),
                        "name": m.get("name"),
                        "description": m.get("description"),
                        "languages": [
                            lang.get("language_id")
                            for lang in m.get("languages", [])
                        ],
                        "can_be_finetuned": m.get("can_be_finetuned", False),
                        "can_use_style": m.get("can_use_style", False),
                        "can_use_speaker_boost": m.get("can_use_speaker_boost", False),
                        "serves_pro_voices": m.get("serves_pro_voices", False),
                        "max_characters_request_free_user": m.get("max_characters_request_free_user"),
                        "max_characters_request_subscribed_user": m.get("max_characters_request_subscribed_user"),
                    })
            return tts_models
    except ElevenLabsError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/elevenlabs/voices")
async def list_elevenlabs_voices(tenant_id: str = Depends(require_auth)) -> list[dict]:
    """Get list of available ElevenLabs voices."""
    try:
        async with ElevenLabsClient() as client:
            voices = await client.get_voices()
            # Return simplified voice info
            return [
                {
                    "voice_id": v.get("voice_id"),
                    "name": v.get("name"),
                    "category": v.get("category"),
                    "description": v.get("description"),
                    "labels": v.get("labels", {}),
                    "preview_url": v.get("preview_url"),
                    "high_quality_base_model_ids": v.get("high_quality_base_model_ids", []),
                }
                for v in voices
            ]
    except ElevenLabsError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/elevenlabs/voices/{voice_id}")
async def get_elevenlabs_voice(voice_id: str, tenant_id: str = Depends(require_auth)) -> dict:
    """Get details for a specific ElevenLabs voice including compatible models."""
    try:
        async with ElevenLabsClient() as client:
            voice = await client.get_voice(voice_id)
            return {
                "voice_id": voice.get("voice_id"),
                "name": voice.get("name"),
                "category": voice.get("category"),
                "description": voice.get("description"),
                "labels": voice.get("labels", {}),
                "preview_url": voice.get("preview_url"),
                "high_quality_base_model_ids": voice.get("high_quality_base_model_ids", []),
                "settings": voice.get("settings", {}),
            }
    except ElevenLabsError as e:
        raise HTTPException(status_code=502, detail=str(e))


# -------------------------------------------------------------------------
# Cartesia API endpoints
# -------------------------------------------------------------------------


@router.get("/api/cartesia/models")
async def list_cartesia_models(tenant_id: str = Depends(require_auth)) -> list[dict]:
    """Get list of available Cartesia TTS models."""
    from ..tts.cartesia import CartesiaClient, CartesiaError

    try:
        async with CartesiaClient() as client:
            return await client.get_models()
    except CartesiaError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        # API key not configured
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/cartesia/voices")
async def list_cartesia_voices(tenant_id: str = Depends(require_auth)) -> list[dict]:
    """Get list of available Cartesia voices."""
    from ..tts.cartesia import CartesiaClient, CartesiaError

    try:
        async with CartesiaClient() as client:
            voices = await client.get_voices()
            return [
                {
                    "voice_id": v.get("id"),
                    "name": v.get("name"),
                    "description": v.get("description"),
                    "language": v.get("language"),
                    "is_public": v.get("is_public"),
                }
                for v in voices
            ]
    except CartesiaError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        # API key not configured
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/cartesia/voices/{voice_id}")
async def get_cartesia_voice(voice_id: str, tenant_id: str = Depends(require_auth)) -> dict:
    """Get details for a specific Cartesia voice."""
    from ..tts.cartesia import CartesiaClient, CartesiaError

    try:
        async with CartesiaClient() as client:
            voice = await client.get_voice(voice_id)
            return {
                "voice_id": voice.get("id"),
                "name": voice.get("name"),
                "description": voice.get("description"),
                "language": voice.get("language"),
                "is_public": voice.get("is_public"),
                "created_at": voice.get("created_at"),
            }
    except CartesiaError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        # API key not configured
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------------
# Kokoro API endpoints
# -------------------------------------------------------------------------


@router.get("/api/kokoro/voices")
async def list_kokoro_voices(tenant_id: str = Depends(require_auth)) -> list[dict]:
    """Get list of available Kokoro voices.

    Kokoro is a self-hosted TTS model, so no API key is required.
    """
    from ..tts.kokoro import KokoroClient, KokoroError

    try:
        voices = await KokoroClient.get_voices()
        return voices
    except KokoroError as e:
        raise HTTPException(status_code=502, detail=str(e))


class KokoroPreviewRequest(BaseModel):
    """Request to preview a Kokoro voice."""

    voice: str = "af_heart"
    speed: float = 1.0


def _pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
    """Convert raw PCM16 data to WAV format."""
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm_data)

    # WAV header
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,  # File size - 8
        b"WAVE",
        b"fmt ",
        16,  # Subchunk1 size
        1,  # Audio format (PCM)
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm_data


@router.post("/api/kokoro/preview")
async def preview_kokoro_voice(
    request: KokoroPreviewRequest,
    tenant_id: str = Depends(require_auth),
) -> Response:
    """Generate a short audio preview of a Kokoro voice.

    Returns WAV audio for immediate playback in browser.
    Does not log to playback history.
    """
    preview_text = "Hello! This is a voice preview."

    try:
        async with httpx.AsyncClient(
            base_url=settings.kokoro_base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
        ) as client:
            response = await client.post(
                "/v1/audio/speech",
                json={
                    "model": "kokoro",
                    "input": preview_text,
                    "voice": request.voice,
                    "response_format": "pcm",
                    "speed": request.speed,
                },
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Kokoro error: {response.status_code}",
                )

            # Convert PCM to WAV for browser playback
            wav_data = _pcm_to_wav(response.content)

            return Response(
                content=wav_data,
                media_type="audio/wav",
                headers={"Cache-Control": "no-cache"},
            )

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Connection error: {e}")
