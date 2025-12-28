"""Moderator management API routes.

Handles Santa dashboard moderator access control.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from ..auth import require_auth, require_santa_auth, SantaAuthContext
from ..config import settings
from ..database import get_session
from ..models import (
    SantaModerator,
    SantaModeratorAdd,
    TwitchConfig,
)
from . import require_santa_feature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/moderators", tags=["Moderators"])


@router.get("")
async def list_moderators(
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """List moderators for the current channel (owner only)."""
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Only owners can view moderators")

    async with get_session() as session:
        result = await session.execute(
            select(SantaModerator).where(
                SantaModerator.broadcaster_tenant_id == auth.effective_tenant_id
            )
        )
        mods = result.scalars().all()

    return {
        "moderators": [
            {
                "user_id": m.moderator_user_id,
                "username": m.moderator_username,
                "added_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mods
        ]
    }


@router.post("")
async def add_moderator(
    request: SantaModeratorAdd,
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Add a moderator by Twitch username (owner only)."""
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Only owners can add moderators")

    # Get owner's access token for API call
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(
                TwitchConfig.tenant_id == auth.effective_tenant_id
            ).limit(1)
        )
        twitch_config = result.scalar_one_or_none()
        if not twitch_config:
            raise HTTPException(status_code=400, detail="Twitch not configured")

    # Look up user via Twitch API
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.twitch.tv/helix/users?login={request.username}",
            headers={
                "Authorization": f"Bearer {twitch_config.access_token}",
                "Client-Id": settings.twitch_client_id,
            },
        )
        if resp.status_code != 200 or not resp.json().get("data"):
            raise HTTPException(
                status_code=404,
                detail=f"Twitch user '{request.username}' not found",
            )

        user_data = resp.json()["data"][0]
        mod_user_id = user_data["id"]
        mod_username = user_data["login"]

    # Add to database
    async with get_session() as session:
        # Check if already exists
        existing = await session.execute(
            select(SantaModerator).where(
                SantaModerator.broadcaster_tenant_id == auth.effective_tenant_id,
                SantaModerator.moderator_user_id == mod_user_id,
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="User is already a moderator")

        mod = SantaModerator(
            broadcaster_tenant_id=auth.effective_tenant_id,
            moderator_user_id=mod_user_id,
            moderator_username=mod_username,
        )
        session.add(mod)
        await session.commit()

    logger.info(f"Added moderator {mod_username} ({mod_user_id}) for tenant {auth.effective_tenant_id}")
    return {"success": True, "moderator": {"user_id": mod_user_id, "username": mod_username}}


@router.delete("/{user_id}")
async def remove_moderator(
    user_id: str,
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Remove a moderator (owner only)."""
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Only owners can remove moderators")

    async with get_session() as session:
        result = await session.execute(
            select(SantaModerator).where(
                SantaModerator.broadcaster_tenant_id == auth.effective_tenant_id,
                SantaModerator.moderator_user_id == user_id,
            ).limit(1)
        )
        mod = result.scalar_one_or_none()
        if not mod:
            raise HTTPException(status_code=404, detail="Moderator not found")

        username = mod.moderator_username
        await session.delete(mod)
        await session.commit()

    logger.info(f"Removed moderator {username} ({user_id}) from tenant {auth.effective_tenant_id}")
    return {"success": True}


@router.get("/accessible-channels")
async def get_accessible_channels(
    tenant_id: str = Depends(require_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Get list of channels the current user can access (own + channels they mod for)."""
    channels: list[dict] = []

    async with get_session() as session:
        # Get user's own channel info
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id).limit(1)
        )
        own_config = result.scalar_one_or_none()
        if own_config:
            channels.append({
                "tenant_id": tenant_id,
                "username": own_config.username or tenant_id,
                "is_own": True,
            })

        # Get channels where user is a moderator
        mod_result = await session.execute(
            select(SantaModerator, TwitchConfig)
            .join(TwitchConfig, SantaModerator.broadcaster_tenant_id == TwitchConfig.tenant_id)
            .where(SantaModerator.moderator_user_id == tenant_id)
        )
        for mod, broadcaster_config in mod_result:
            channels.append({
                "tenant_id": mod.broadcaster_tenant_id,
                "username": broadcaster_config.username or mod.broadcaster_tenant_id,
                "is_own": False,
            })

    return {"channels": channels}
