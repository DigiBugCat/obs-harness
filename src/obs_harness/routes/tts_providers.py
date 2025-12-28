"""TTS provider API routes.

Handles ElevenLabs, Cartesia, and OpenRouter model/voice lookups.
"""

from fastapi import APIRouter, Depends, HTTPException

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
