"""Moderator management API routes.

Handles moderator access control for dashboard.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from ..auth import require_auth
from ..config import settings
from ..database import get_session
from ..helpers.twitch import refresh_twitch_token
from ..models import (
    Moderator,
    ModeratorAdd,
    TwitchConfig,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/moderators", tags=["Moderators"])


@router.get("")
async def list_moderators(
    tenant_id: str = Depends(require_auth),
) -> dict:
    """List moderators for the current channel."""
    async with get_session() as session:
        result = await session.execute(
            select(Moderator).where(
                Moderator.broadcaster_tenant_id == tenant_id
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
    request: ModeratorAdd,
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Add a moderator by Twitch username."""
    # Get owner's access token for API call
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(
                TwitchConfig.tenant_id == tenant_id
            ).limit(1)
        )
        twitch_config = result.scalar_one_or_none()
        if not twitch_config:
            raise HTTPException(status_code=400, detail="Twitch not configured")

    # Look up user via Twitch API
    async def lookup_user(access_token: str):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.twitch.tv/helix/users?login={request.username}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": settings.twitch_client_id,
                },
            )
            return resp

    resp = await lookup_user(twitch_config.access_token)

    # If token expired, try refreshing
    if resp.status_code == 401:
        logger.info(f"Token expired for tenant {tenant_id}, attempting refresh...")
        if await refresh_twitch_token(tenant_id):
            # Re-fetch config with new token
            async with get_session() as session:
                result = await session.execute(
                    select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id).limit(1)
                )
                twitch_config = result.scalar_one_or_none()
            if twitch_config:
                resp = await lookup_user(twitch_config.access_token)

    if resp.status_code != 200 or not resp.json().get("data"):
        raise HTTPException(
            status_code=404,
            detail=f"Twitch user '{request.username}' not found (API status: {resp.status_code})",
        )

    user_data = resp.json()["data"][0]
    mod_user_id = user_data["id"]
    mod_username = user_data["login"]

    # Add to database
    async with get_session() as session:
        # Check if already exists
        existing = await session.execute(
            select(Moderator).where(
                Moderator.broadcaster_tenant_id == tenant_id,
                Moderator.moderator_user_id == mod_user_id,
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="User is already a moderator")

        mod = Moderator(
            broadcaster_tenant_id=tenant_id,
            moderator_user_id=mod_user_id,
            moderator_username=mod_username,
        )
        session.add(mod)
        await session.commit()

    logger.info(f"Added moderator {mod_username} ({mod_user_id}) for tenant {tenant_id}")
    return {"success": True, "moderator": {"user_id": mod_user_id, "username": mod_username}}


@router.delete("/{user_id}")
async def remove_moderator(
    user_id: str,
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Remove a moderator."""
    async with get_session() as session:
        result = await session.execute(
            select(Moderator).where(
                Moderator.broadcaster_tenant_id == tenant_id,
                Moderator.moderator_user_id == user_id,
            ).limit(1)
        )
        mod = result.scalar_one_or_none()
        if not mod:
            raise HTTPException(status_code=404, detail="Moderator not found")

        username = mod.moderator_username
        await session.delete(mod)
        await session.commit()

    logger.info(f"Removed moderator {username} ({user_id}) from tenant {tenant_id}")
    return {"success": True}


@router.get("/accessible-channels")
async def get_accessible_channels(
    tenant_id: str = Depends(require_auth),
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
            select(Moderator, TwitchConfig)
            .join(TwitchConfig, Moderator.broadcaster_tenant_id == TwitchConfig.tenant_id)
            .where(Moderator.moderator_user_id == tenant_id)
        )
        for mod, broadcaster_config in mod_result:
            channels.append({
                "tenant_id": mod.broadcaster_tenant_id,
                "username": broadcaster_config.username or mod.broadcaster_tenant_id,
                "is_own": False,
            })

    return {"channels": channels}
