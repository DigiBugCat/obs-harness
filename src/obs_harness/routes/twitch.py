"""Twitch API routes.

Handles Twitch status, token management, channel configuration, and EventSub control.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from ..auth import require_auth
from ..config import settings
from ..database import get_session
from ..helpers.santa import create_redemption_callback
from ..helpers.twitch import create_chat_callback, refresh_twitch_token
from ..models import SantaConfig, TwitchChannelRequest, TwitchConfig, TwitchTokenRequest
from . import get_state
from ..state import AppState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/twitch", tags=["Twitch"])


@router.get("/status")
async def twitch_status(
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Get Twitch connection status for the current tenant."""
    # Get stored user info from database
    user_id = None
    username = None
    channel = None
    token_expires_at = None
    has_refresh_token = False
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch_config = result.scalar_one_or_none()
        if twitch_config:
            user_id = twitch_config.user_id
            username = twitch_config.username
            channel = twitch_config.channel
            token_expires_at = twitch_config.token_expires_at
            has_refresh_token = bool(twitch_config.refresh_token)

    eventsub_mgr = state.eventsub_managers.get(tenant_id)
    return {
        "connected": eventsub_mgr.is_connected if eventsub_mgr else False,
        "channel": channel,
        "user_id": user_id,
        "username": username,
        "token_expires_at": token_expires_at.isoformat() if token_expires_at else None,
        "has_refresh_token": has_refresh_token,
    }


@router.post("/refresh")
async def twitch_refresh_token_route(
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Manually refresh the Twitch access token."""
    success = await refresh_twitch_token(tenant_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to refresh token")

    # Restart EventSub with new token
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch_config = result.scalar_one_or_none()

        if twitch_config:
            client_id = settings.twitch_client_id
            eventsub_mgr = state.get_eventsub_manager(tenant_id)
            eventsub_mgr.set_chat_callback(create_chat_callback(state, tenant_id))
            await eventsub_mgr.start(
                access_token=twitch_config.access_token,
                client_id=client_id,
                broadcaster_user_id=twitch_config.user_id,
                user_id=twitch_config.user_id,
                subscribe_to_chat=True,
                subscribe_to_redemptions=False,
            )

    return {"success": True, "message": "Token refreshed and EventSub reconnected"}


@router.post("/token")
async def twitch_save_token(
    request: TwitchTokenRequest,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Save Twitch OAuth token and connect to chat.

    Called by frontend after OAuth implicit grant flow completes.
    """
    # Save or update token in database
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch_config = result.scalar_one_or_none()

        if twitch_config:
            # Update existing config
            twitch_config.access_token = request.access_token
            twitch_config.user_id = request.user_id
            twitch_config.username = request.username
            twitch_config.channel = request.channel
            twitch_config.updated_at = datetime.utcnow()
        else:
            # Create new config
            twitch_config = TwitchConfig(
                tenant_id=tenant_id,
                access_token=request.access_token,
                user_id=request.user_id,
                username=request.username,
                channel=request.channel,
            )
            session.add(twitch_config)

        await session.commit()

    # Look up the channel's user ID (may be different from logged-in user)
    channel_user_id = request.user_id  # Default to logged-in user
    if request.channel.lower() != request.username.lower():
        # Different channel - look up its user ID
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.twitch.tv/helix/users?login={request.channel}",
                    headers={
                        "Authorization": f"Bearer {request.access_token}",
                        "Client-Id": settings.twitch_client_id,
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data"):
                        channel_user_id = data["data"][0]["id"]
                        logger.info(f"Looked up channel {request.channel} -> user_id {channel_user_id}")
        except Exception as e:
            logger.warning(f"Failed to look up channel user ID: {e}")

    # Start EventSub for real-time chat via WebSocket
    try:
        # Set the chat callback to broadcast to WebSocket clients
        eventsub_mgr = state.get_eventsub_manager(tenant_id)
        eventsub_mgr.set_chat_callback(create_chat_callback(state, tenant_id))

        await eventsub_mgr.start(
            access_token=request.access_token,
            client_id=settings.twitch_client_id,
            broadcaster_user_id=channel_user_id,  # Channel to monitor
            user_id=request.user_id,  # Authenticated user (for permissions)
            subscribe_to_chat=True,
            subscribe_to_redemptions=False,  # Don't subscribe to redemptions yet (Santa handles that)
        )
        logger.info(f"EventSub started for chat on #{request.channel} (broadcaster: {channel_user_id})")
    except Exception as e:
        logger.warning(f"Failed to start EventSub for chat: {e}")

    return {"success": True, "channel": request.channel, "user_id": request.user_id, "username": request.username}


@router.post("/channel")
async def twitch_set_channel(
    request: TwitchChannelRequest,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Change the Twitch channel to listen to."""
    # Get stored config
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch_config = result.scalar_one_or_none()

        if not twitch_config:
            raise HTTPException(status_code=400, detail="Not logged in to Twitch")

        # Update channel
        twitch_config.channel = request.channel
        twitch_config.updated_at = datetime.utcnow()
        await session.commit()

        access_token = twitch_config.access_token
        user_id = twitch_config.user_id

    # Restart EventSub for the new channel
    try:
        # Look up channel's user ID
        channel_user_id = user_id  # Default
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.twitch.tv/helix/users?login={request.channel}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": settings.twitch_client_id,
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data"):
                    channel_user_id = data["data"][0]["id"]
                    logger.info(f"Looked up channel {request.channel} -> user_id {channel_user_id}")

        # Check if Santa is enabled - if so, we need to include redemptions
        async with get_session() as santa_session:
            santa_result = await santa_session.execute(
                select(SantaConfig).where(SantaConfig.tenant_id == tenant_id)
            )
            santa_config = santa_result.scalar_one_or_none()
        santa_enabled = santa_config and santa_config.enabled
        reward_id = santa_config.reward_id if santa_config else None

        # Restart EventSub with new broadcaster
        eventsub_mgr = state.get_eventsub_manager(tenant_id)
        eventsub_mgr.set_chat_callback(create_chat_callback(state, tenant_id))
        await eventsub_mgr.start(
            access_token=access_token,
            client_id=settings.twitch_client_id,
            broadcaster_user_id=channel_user_id,
            user_id=user_id,
            reward_id=reward_id if santa_enabled else None,
            on_redemption=create_redemption_callback(state, tenant_id) if santa_enabled else None,
            subscribe_to_chat=True,
            subscribe_to_redemptions=santa_enabled,
        )
        logger.info(f"EventSub restarted for chat on #{request.channel} (Santa: {santa_enabled})")
    except Exception as e:
        logger.warning(f"Failed to restart EventSub for new channel: {e}")

    return {"success": True, "channel": request.channel}


@router.post("/disconnect")
async def twitch_disconnect(
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Disconnect from Twitch and clear saved credentials."""
    eventsub_mgr = state.eventsub_managers.get(tenant_id)
    if eventsub_mgr:
        await eventsub_mgr.stop()
        del state.eventsub_managers[tenant_id]

    # Clear stored config from database
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch_config = result.scalar_one_or_none()
        if twitch_config:
            await session.delete(twitch_config)
            await session.commit()

    return {"success": True}


@router.post("/cleanup-subscriptions")
async def twitch_cleanup_subscriptions(
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Delete all existing EventSub subscriptions to fix 'maximum subscriptions exceeded' error."""
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch_config = result.scalar_one_or_none()
        if not twitch_config:
            raise HTTPException(status_code=400, detail="Not connected to Twitch")

        try:
            eventsub_mgr = state.get_eventsub_manager(tenant_id)
            deleted = await eventsub_mgr.cleanup_subscriptions(
                access_token=twitch_config.access_token,
                client_id=settings.twitch_client_id,
            )
            return {"success": True, "deleted": deleted}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


@router.get("/chat")
async def get_twitch_chat(
    seconds: int = 60,
    state: AppState = Depends(get_state),
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Get recent chat messages (for debugging/preview).

    Args:
        seconds: Number of seconds of chat history to retrieve
    """
    # Get channel from database
    channel = None
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch_config = result.scalar_one_or_none()
        if twitch_config:
            channel = twitch_config.channel

    eventsub_mgr = state.eventsub_managers.get(tenant_id)
    if eventsub_mgr and eventsub_mgr.is_connected:
        context = await eventsub_mgr.get_chat_context(seconds=seconds)
        return {
            "channel": channel,
            "context": context,
        }
    else:
        return {"messages": [], "channel": channel, "context": ""}
