"""Santa session helper functions.

Provides broadcasting, callbacks, and state management for Santa sessions.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import select

from ..database import get_session
from ..models import SantaConfig, SantaSession
from ..santa_session import SantaState

if TYPE_CHECKING:
    from ..state import AppState
    from ..santa_session import SessionData
    from ..twitch_eventsub import ChannelPointRedemption

logger = logging.getLogger(__name__)


async def broadcast_santa_status(
    state: "AppState",
    tenant_id: str,
    session_data: "SessionData | None" = None,
) -> None:
    """Broadcast Santa session status to Santa dashboard connections for a specific tenant."""
    mgr = state.get_santa_manager(tenant_id)
    if mgr:
        status = mgr.get_session_status()
    else:
        status = {"active": False, "session_id": None, "state": None}

    message = {"type": "santa_status", "status": status, "tenant_id": tenant_id}
    for ws, ws_tenant in list(state.santa_dashboard_connections.items()):
        if ws_tenant != tenant_id:
            continue  # Only send to this tenant's connections
        try:
            await ws.send_json(message)
        except Exception:
            state.santa_dashboard_connections.pop(ws, None)


async def finalize_santa_session(state: "AppState", tenant_id: str) -> None:
    """Finalize the current Santa session (save to DB, unpause reward)."""
    santa_mgr = state.get_santa_manager(tenant_id)
    eventsub_mgr = state.get_eventsub_manager(tenant_id)

    if not santa_mgr or not santa_mgr.active_session:
        return

    session_data = santa_mgr.active_session

    # Update database
    async with get_session() as db_session:
        result = await db_session.execute(
            select(SantaSession).where(SantaSession.id == session_data.session_id)
        )
        db_record = result.scalar_one_or_none()
        if db_record:
            db_record.state = session_data.state.value
            db_record.outcome = session_data.outcome
            db_record.followup_count = session_data.followup_count
            db_record.conversation_history = santa_mgr.get_conversation_json()
            db_record.ended_at = datetime.utcnow()
            await db_session.commit()

    # Get reward ID from config and re-enable
    async with get_session() as session:
        result = await session.execute(
            select(SantaConfig).where(SantaConfig.tenant_id == tenant_id).limit(1)
        )
        config = result.scalar_one_or_none()
        if config and config.reward_id and config.enabled:
            await eventsub_mgr.enable_reward(config.reward_id)

    logger.info(f"Santa session {session_data.session_id} finalized: {session_data.outcome} (tenant: {tenant_id})")


def create_santa_state_callback(state: "AppState", tenant_id: str):
    """Create a tenant-specific state change callback closure."""
    async def on_santa_state_change(session_data: "SessionData") -> None:
        """Callback for Santa session state changes."""
        await broadcast_santa_status(state, tenant_id, session_data)

        # When session completes, finalize it (save to DB, re-enable reward)
        if session_data.state == SantaState.COMPLETE:
            await finalize_santa_session(state, tenant_id)
    return on_santa_state_change


def create_redemption_callback(state: "AppState", tenant_id: str):
    """Create a tenant-specific redemption callback closure."""
    async def handle_channel_point_redemption(redemption: "ChannelPointRedemption") -> None:
        """Handle incoming channel point redemption."""
        santa_mgr = state.get_santa_manager(tenant_id)
        eventsub_mgr = state.get_eventsub_manager(tenant_id)

        if not santa_mgr:
            logger.warning(f"Santa manager not initialized for tenant {tenant_id}, ignoring redemption")
            return

        # Get Santa config for this tenant
        async with get_session() as session:
            result = await session.execute(
                select(SantaConfig).where(SantaConfig.tenant_id == tenant_id).limit(1)
            )
            config = result.scalar_one_or_none()

        if not config or not config.enabled:
            logger.debug(f"Santa not enabled for tenant {tenant_id}, ignoring redemption")
            return

        # Check if this is the configured reward
        if config.reward_id and redemption.reward_id != config.reward_id:
            logger.debug(f"Redemption for different reward ({redemption.reward_title}), ignoring")
            return

        # Check if session already active
        if santa_mgr.is_active:
            logger.warning(f"Santa session already active, cannot process redemption from {redemption.user_display_name}")
            # Optionally refund the redemption
            await eventsub_mgr.cancel_redemption(redemption.redemption_id, redemption.reward_id)
            return

        # Pause the reward to prevent new redeems
        await eventsub_mgr.disable_reward(redemption.reward_id)

        # Get past sessions for this user (repeat visitor detection)
        past_sessions = []
        async with get_session() as session:
            result = await session.execute(
                select(SantaSession)
                .where(
                    SantaSession.tenant_id == tenant_id,
                    SantaSession.redeemer_user_id == redemption.user_id
                )
                .order_by(SantaSession.started_at.desc())
                .limit(5)
            )
            for ps in result.scalars().all():
                past_sessions.append({
                    "wish_text": ps.wish_text,
                    "outcome": ps.outcome,
                    "started_at": ps.started_at.isoformat() if ps.started_at else None,
                })

        # Create session record
        async with get_session() as session:
            db_session = SantaSession(
                tenant_id=tenant_id,
                redeemer_user_id=redemption.user_id,
                redeemer_username=redemption.user_login,
                redeemer_display_name=redemption.user_display_name,
                wish_text=redemption.user_input or "",
                state="processing",
            )
            session.add(db_session)
            await session.commit()
            await session.refresh(db_session)
            session_id = db_session.id

        logger.info(f"Processing redemption from {redemption.user_display_name}: {redemption.user_input}")

        # Start the Santa session
        await santa_mgr.start_session(
            session_id=session_id,
            user_id=redemption.user_id,
            username=redemption.user_display_name,
            wish_text=redemption.user_input or "I want a surprise!",
            past_sessions=past_sessions,
        )
    return handle_channel_point_redemption
