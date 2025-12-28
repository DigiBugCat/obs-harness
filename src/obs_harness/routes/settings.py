"""User settings API routes.

Handles API key management (BYOK - Bring Your Own Key).
"""

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..auth import require_auth
from ..database import get_session
from ..helpers.keys import get_api_key_status
from ..models import UserSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class ApiKeyUpdate(BaseModel):
    """Request to update an API key."""

    provider: Literal["elevenlabs", "cartesia", "openrouter"]
    key: str


@router.get("")
async def get_settings(
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Get user settings with masked API keys."""
    api_keys = await get_api_key_status(tenant_id)
    return {
        "api_keys": api_keys,
    }


@router.put("/api-keys")
async def update_api_key(
    request: ApiKeyUpdate,
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Save or update an API key."""
    async with get_session() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.tenant_id == tenant_id).limit(1)
        )
        user_settings = result.scalar_one_or_none()

        if not user_settings:
            user_settings = UserSettings(tenant_id=tenant_id)
            session.add(user_settings)

        # Update the appropriate key
        if request.provider == "elevenlabs":
            user_settings.elevenlabs_api_key = request.key
        elif request.provider == "cartesia":
            user_settings.cartesia_api_key = request.key
        elif request.provider == "openrouter":
            user_settings.openrouter_api_key = request.key

        user_settings.updated_at = datetime.utcnow()
        await session.commit()

    logger.info(f"Updated {request.provider} API key for tenant {tenant_id}")
    return {"success": True, "provider": request.provider}


@router.delete("/api-keys/{provider}")
async def delete_api_key(
    provider: Literal["elevenlabs", "cartesia", "openrouter"],
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Remove an API key (will fall back to global if available)."""
    async with get_session() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.tenant_id == tenant_id).limit(1)
        )
        user_settings = result.scalar_one_or_none()

        if not user_settings:
            raise HTTPException(status_code=404, detail="No settings found")

        # Clear the appropriate key
        if provider == "elevenlabs":
            user_settings.elevenlabs_api_key = None
        elif provider == "cartesia":
            user_settings.cartesia_api_key = None
        elif provider == "openrouter":
            user_settings.openrouter_api_key = None

        user_settings.updated_at = datetime.utcnow()
        await session.commit()

    logger.info(f"Deleted {provider} API key for tenant {tenant_id}")
    return {"success": True, "provider": provider}
