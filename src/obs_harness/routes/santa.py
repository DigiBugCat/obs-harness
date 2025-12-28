"""Santa session API routes.

Handles Mall Santa configuration, session management, and EventSub integration.
"""

import json
import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import delete, select

from ..auth import require_auth, require_owner_only, require_santa_auth, SantaAuthContext
from ..config import settings
from ..database import get_session
from ..helpers.santa import (
    create_redemption_callback,
    finalize_santa_session,
)
from ..helpers.twitch import create_chat_callback
from ..models import (
    Character,
    SantaAccessibleChannel,
    SantaConfig,
    SantaConfigResponse,
    SantaConfigUpdate,
    SantaMessageRequest,
    SantaModerator,
    SantaModeratorAdd,
    SantaModeratorResponse,
    SantaSession,
    SantaSessionStatus,
    SantaVerdictRequest,
    TwitchConfig,
)
from . import get_state, require_santa_feature
from ..state import AppState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/santa", tags=["Santa"])


@router.get("/config")
async def get_santa_config(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> SantaConfigResponse:
    """Get Santa configuration for the current tenant."""
    tenant_id = auth.effective_tenant_id
    async with get_session() as session:
        result = await session.execute(
            select(SantaConfig).where(SantaConfig.tenant_id == tenant_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            config = SantaConfig(tenant_id=tenant_id)
            session.add(config)
            await session.commit()
            await session.refresh(config)

        return SantaConfigResponse(
            enabled=config.enabled,
            character_name=config.character_name,
            reward_id=config.reward_id,
            chat_vote_seconds=config.chat_vote_seconds,
            max_followups=config.max_followups,
            response_timeout_seconds=config.response_timeout_seconds,
            debounce_seconds=config.debounce_seconds,
        )


@router.put("/config")
async def update_santa_config(
    request: SantaConfigUpdate,
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> SantaConfigResponse:
    """Update Santa configuration."""
    tenant_id = auth.effective_tenant_id
    async with get_session() as session:
        result = await session.execute(
            select(SantaConfig).where(SantaConfig.tenant_id == tenant_id)
        )
        config = result.scalar_one_or_none()
        if not config:
            config = SantaConfig(tenant_id=tenant_id)
            session.add(config)

        # Track if enabled state changed
        old_enabled = config.enabled
        old_reward_id = config.reward_id

        update_data = request.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(config, key, value)
        config.updated_at = datetime.utcnow()
        await session.commit()
        await session.refresh(config)

        # Update santa manager with new settings if it exists
        santa_mgr = state.get_santa_manager(tenant_id)
        if santa_mgr:
            santa_mgr.max_followups = config.max_followups
            santa_mgr.response_timeout = config.response_timeout_seconds
            santa_mgr.debounce_seconds = config.debounce_seconds
            santa_mgr.chat_vote_seconds = config.chat_vote_seconds
            santa_mgr.character_name = config.character_name

        # Enable/disable reward based on enabled state
        reward_id = config.reward_id
        eventsub_mgr = state.eventsub_managers.get(tenant_id)
        if reward_id and eventsub_mgr and eventsub_mgr.is_connected:
            if config.enabled and not old_enabled:
                # Santa was just enabled - enable the reward
                await eventsub_mgr.enable_reward(reward_id)
                logger.info(f"Santa enabled - enabled reward {reward_id}")
            elif not config.enabled and old_enabled:
                # Santa was just disabled - disable the reward
                await eventsub_mgr.disable_reward(reward_id)
                logger.info(f"Santa disabled - disabled reward {reward_id}")

        return SantaConfigResponse(
            enabled=config.enabled,
            character_name=config.character_name,
            reward_id=config.reward_id,
            chat_vote_seconds=config.chat_vote_seconds,
            max_followups=config.max_followups,
            response_timeout_seconds=config.response_timeout_seconds,
            debounce_seconds=config.debounce_seconds,
        )


@router.get("/session")
async def get_santa_session(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> SantaSessionStatus:
    """Get current Santa session status."""
    tenant_id = auth.effective_tenant_id
    santa_mgr = state.get_santa_manager(tenant_id)
    if not santa_mgr:
        return SantaSessionStatus(active=False)

    status = santa_mgr.get_session_status()
    return SantaSessionStatus(**status)


@router.get("/sessions")
async def get_santa_sessions(
    limit: int = 20,
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Get past Santa sessions with conversation history."""
    tenant_id = auth.effective_tenant_id
    async with get_session() as session:
        result = await session.execute(
            select(SantaSession)
            .where(SantaSession.tenant_id == tenant_id)
            .order_by(SantaSession.started_at.desc())
            .limit(limit)
        )
        sessions = result.scalars().all()

    return {
        "sessions": [
            {
                "id": s.id,
                "redeemer_display_name": s.redeemer_display_name,
                "wish_text": s.wish_text,
                "outcome": s.outcome,
                "followup_count": s.followup_count,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "conversation": json.loads(s.conversation_history) if s.conversation_history else [],
            }
            for s in sessions
        ]
    }


@router.delete("/sessions")
async def clear_santa_sessions(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Clear all past Santa sessions for the current tenant."""
    tenant_id = auth.effective_tenant_id
    async with get_session() as session:
        await session.execute(
            delete(SantaSession).where(SantaSession.tenant_id == tenant_id)
        )
        await session.commit()

    logger.info(f"Cleared all Santa sessions for tenant {tenant_id}")
    return {"success": True, "message": "All sessions cleared"}


@router.post("/reset")
async def reset_santa(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Full Santa reset: clear sessions, clear memory, restart EventSub."""
    tenant_id = auth.effective_tenant_id
    results = []

    # 1. Clear sessions for this tenant
    async with get_session() as session:
        await session.execute(
            delete(SantaSession).where(SantaSession.tenant_id == tenant_id)
        )
        await session.commit()
    results.append("Sessions cleared")

    # 2. Clear character memory for santa_timmy
    async with get_session() as session:
        result = await session.execute(
            select(Character).where(
                Character.tenant_id == tenant_id,
                Character.name == "santa_timmy"
            )
        )
        char = result.scalar_one_or_none()
        if char:
            char.memory = None
            session.add(char)
            await session.commit()
            results.append("Memory cleared")

    # 3. Restart EventSub if we have Twitch config
    eventsub_mgr = state.eventsub_managers.get(tenant_id)
    if eventsub_mgr and eventsub_mgr.is_connected:
        await eventsub_mgr.stop()
        results.append("EventSub stopped")

    # Get config and restart
    async with get_session() as session:
        config_result = await session.execute(
            select(SantaConfig).where(SantaConfig.tenant_id == tenant_id)
        )
        santa_config = config_result.scalar_one_or_none()
        twitch_result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch = twitch_result.scalar_one_or_none()

        if twitch and twitch.access_token and twitch.user_id:
            eventsub_mgr = state.get_eventsub_manager(tenant_id)

            await eventsub_mgr.start(
                access_token=twitch.access_token,
                client_id=settings.twitch_client_id,
                broadcaster_user_id=twitch.user_id,
                user_id=twitch.user_id,
                refresh_token=twitch.refresh_token,
                reward_id=santa_config.reward_id if santa_config else None,
                on_redemption=create_redemption_callback(state, tenant_id),
                subscribe_to_chat=True,
                subscribe_to_redemptions=True,
            )
            eventsub_mgr.set_chat_callback(create_chat_callback(state, tenant_id))
            results.append("EventSub restarted")

    logger.info(f"Santa reset complete: {', '.join(results)}")
    return {"success": True, "results": results}


@router.post("/session/message")
async def santa_session_message(
    request: SantaMessageRequest,
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Send a message to the active Santa session (dashboard override)."""
    tenant_id = auth.effective_tenant_id
    santa_mgr = state.get_santa_manager(tenant_id)
    if not santa_mgr:
        raise HTTPException(status_code=500, detail="Santa manager not initialized")

    if not santa_mgr.is_active:
        raise HTTPException(status_code=400, detail="No active Santa session")

    success = await santa_mgr.send_message(request.message)
    return {"success": success}


@router.post("/session/verdict")
async def santa_session_verdict(
    request: SantaVerdictRequest,
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Force a verdict on the active Santa session (skip chat voting)."""
    tenant_id = auth.effective_tenant_id
    santa_mgr = state.get_santa_manager(tenant_id)
    if not santa_mgr:
        raise HTTPException(status_code=500, detail="Santa manager not initialized")

    if not santa_mgr.is_active:
        raise HTTPException(status_code=400, detail="No active Santa session")

    success = await santa_mgr.force_verdict(request.verdict)
    if success:
        # Finalize session after verdict
        await finalize_santa_session(state, tenant_id)
    return {"success": success}


@router.post("/session/cancel")
async def santa_session_cancel(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Cancel the active Santa session."""
    tenant_id = auth.effective_tenant_id
    santa_mgr = state.get_santa_manager(tenant_id)
    if not santa_mgr:
        raise HTTPException(status_code=500, detail="Santa manager not initialized")

    if not santa_mgr.is_active:
        return {"success": True, "message": "No active session to cancel"}

    await santa_mgr.cancel_session("cancelled")
    await finalize_santa_session(state, tenant_id)
    return {"success": True}


@router.post("/session/hold")
async def santa_session_hold(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Toggle hold state on active session (pauses timeouts)."""
    tenant_id = auth.effective_tenant_id
    santa_mgr = state.get_santa_manager(tenant_id)
    if not santa_mgr:
        raise HTTPException(status_code=500, detail="Santa manager not initialized")

    new_state = santa_mgr.toggle_hold()
    return {"success": True, "held": new_state}


@router.post("/start")
async def santa_start(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Start listening for channel point redemptions."""
    tenant_id = auth.effective_tenant_id
    # Get Twitch config
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch_config = result.scalar_one_or_none()

    if not twitch_config:
        raise HTTPException(status_code=400, detail="Twitch not configured. Go to /twitch to sign in.")

    if not twitch_config.user_id:
        raise HTTPException(status_code=400, detail="Twitch user ID not set. Re-authenticate at /twitch.")

    # Get Santa config for reward_id
    async with get_session() as session:
        result = await session.execute(
            select(SantaConfig).where(SantaConfig.tenant_id == tenant_id)
        )
        santa_config = result.scalar_one_or_none()

    try:
        eventsub_mgr = state.get_eventsub_manager(tenant_id)
        await eventsub_mgr.start(
            access_token=twitch_config.access_token,
            client_id=settings.twitch_client_id,
            broadcaster_user_id=twitch_config.user_id,
            refresh_token=twitch_config.refresh_token,
            reward_id=santa_config.reward_id if santa_config else None,
            on_redemption=create_redemption_callback(state, tenant_id),
        )
        return {"success": True, "message": "EventSub started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start EventSub: {e}")


@router.post("/stop")
async def santa_stop(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Stop listening for channel point redemptions."""
    tenant_id = auth.effective_tenant_id
    eventsub_mgr = state.eventsub_managers.get(tenant_id)
    if eventsub_mgr:
        await eventsub_mgr.stop()
    return {"success": True, "message": "EventSub stopped"}


@router.get("/rewards")
async def get_santa_rewards(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Get available channel point rewards."""
    tenant_id = auth.effective_tenant_id
    eventsub_mgr = state.eventsub_managers.get(tenant_id)
    if not eventsub_mgr or not eventsub_mgr.is_connected:
        return {"rewards": [], "message": "EventSub not connected"}

    rewards = await eventsub_mgr.get_rewards()
    return {"rewards": rewards}


@router.get("/eventsub/status")
async def get_eventsub_status(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Get EventSub connection status."""
    tenant_id = auth.effective_tenant_id
    eventsub_mgr = state.eventsub_managers.get(tenant_id)
    return {
        "connected": eventsub_mgr.is_connected if eventsub_mgr else False,
    }


@router.post("/interrupt")
async def santa_interrupt(
    request: dict,
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Send a Mall Director interruption through Santa (uses speech lock)."""
    tenant_id = auth.effective_tenant_id
    message = request.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message required")

    santa_mgr = state.get_santa_manager(tenant_id)
    if not santa_mgr:
        raise HTTPException(status_code=500, detail="Santa manager not initialized")

    success = await santa_mgr.interrupt_with_message(message)
    if success:
        return {"success": True}
    else:
        raise HTTPException(status_code=500, detail="Failed to send interruption")


@router.post("/toggle")
async def toggle_santa_enabled(
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_santa_auth),
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Toggle Santa enabled state - restarts EventSub to subscribe/unsubscribe from redemptions."""
    tenant_id = auth.effective_tenant_id
    async with get_session() as session:
        result = await session.execute(
            select(SantaConfig).where(SantaConfig.tenant_id == tenant_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=400, detail="Santa not configured")

        # Toggle the enabled state
        config.enabled = not config.enabled
        session.add(config)
        await session.commit()
        await session.refresh(config)

        new_enabled = config.enabled
        reward_id = config.reward_id

        # Get Twitch config for restart
        twitch_result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch_config = twitch_result.scalar_one_or_none()

    # Restart EventSub to subscribe/unsubscribe from redemptions
    if twitch_config and twitch_config.access_token:
        try:
            eventsub_mgr = state.get_eventsub_manager(tenant_id)

            # Stop current connection
            await eventsub_mgr.stop()

            # Look up channel's user ID
            channel_user_id = twitch_config.user_id
            if twitch_config.channel and twitch_config.channel.lower() != (twitch_config.username or "").lower():
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"https://api.twitch.tv/helix/users?login={twitch_config.channel}",
                            headers={
                                "Authorization": f"Bearer {twitch_config.access_token}",
                                "Client-Id": settings.twitch_client_id,
                            }
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("data"):
                                channel_user_id = data["data"][0]["id"]
                except Exception:
                    pass

            # Restart with appropriate subscriptions
            eventsub_mgr.set_chat_callback(create_chat_callback(state, tenant_id))
            await eventsub_mgr.start(
                access_token=twitch_config.access_token,
                client_id=settings.twitch_client_id,
                broadcaster_user_id=channel_user_id,
                user_id=twitch_config.user_id,
                refresh_token=twitch_config.refresh_token,
                reward_id=reward_id if new_enabled else None,
                on_redemption=create_redemption_callback(state, tenant_id) if new_enabled else None,
                subscribe_to_chat=True,
                subscribe_to_redemptions=new_enabled,
            )

            if new_enabled:
                # Enable the reward on Twitch
                if reward_id:
                    await eventsub_mgr.enable_reward(reward_id)
                logger.info(f"Santa enabled - EventSub restarted with redemptions")
            else:
                # Disable the reward on Twitch
                if reward_id:
                    await eventsub_mgr.disable_reward(reward_id)
                logger.info(f"Santa disabled - EventSub restarted without redemptions")

        except Exception as e:
            logger.error(f"Failed to restart EventSub on toggle: {e}")

    return {"success": True, "enabled": new_enabled}


@router.post("/reward/create")
async def create_santa_reward(
    title: str = "Talk to Santa",
    cost: int = 100,
    prompt: str = "Tell Santa your Christmas wish!",
    state: AppState = Depends(get_state),
    auth: SantaAuthContext = Depends(require_owner_only),  # Owner only
    _santa: None = Depends(require_santa_feature),
) -> dict:
    """Create a new channel point reward for Santa wishes (owner only)."""
    tenant_id = auth.effective_tenant_id
    eventsub_mgr = state.eventsub_managers.get(tenant_id)
    if not eventsub_mgr or not eventsub_mgr.is_connected:
        raise HTTPException(status_code=400, detail="EventSub not connected")

    result = await eventsub_mgr.create_reward(
        title=title,
        cost=cost,
        prompt=prompt,
        is_user_input_required=True,
        is_enabled=True,
    )

    if result:
        # Auto-save this reward to config
        async with get_session() as session:
            db_result = await session.execute(
                select(SantaConfig).where(SantaConfig.tenant_id == tenant_id)
            )
            config = db_result.scalar_one_or_none()
            if config:
                config.reward_id = result["id"]
                session.add(config)
                await session.commit()

        return {"success": True, "reward": result}
    else:
        raise HTTPException(status_code=500, detail="Failed to create reward")
