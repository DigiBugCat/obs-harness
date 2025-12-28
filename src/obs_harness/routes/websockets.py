"""WebSocket route handlers.

Handles real-time connections for dashboard, Twitch chat, and browser sources.
"""

import json
import logging
import time

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlmodel import select

from .. import __version__
from ..database import get_session
from ..models import Character, Moderator, TwitchConfig
from .system import BUILD_ID
from . import get_state
from ..state import AppState
from ..helpers.conversation import update_interrupted_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSockets"])


async def get_app_state(websocket: WebSocket) -> AppState:
    """Get app state from WebSocket's app reference."""
    return websocket.app.state.app_state


@router.websocket("/ws/dashboard")
async def dashboard_websocket(
    websocket: WebSocket,
    channel: str | None = Query(default=None, description="Channel to view (tenant_id)"),
):
    """WebSocket endpoint for dashboard live updates (requires auth).

    Supports moderator access via ?channel= parameter.
    """
    state = await get_app_state(websocket)

    # Verify authentication before accepting connection
    user_id = websocket.cookies.get("tenant_id")
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Determine effective channel (which channel they're viewing)
    effective_channel = channel or user_id

    # If viewing another channel, verify moderator access
    if effective_channel != user_id:
        async with get_session() as session:
            result = await session.execute(
                select(Moderator).where(
                    Moderator.broadcaster_tenant_id == effective_channel,
                    Moderator.moderator_user_id == user_id,
                ).limit(1)
            )
            if not result.scalar_one_or_none():
                await websocket.close(code=4003, reason="Access denied")
                return

    await state.manager.connect_dashboard(websocket, effective_channel)

    # Send hello message with version info and effective tenant_id for client
    await websocket.send_json({
        "type": "hello",
        "version": __version__,
        "build_id": BUILD_ID,
        "tenant_id": effective_channel,  # Use effective channel for status key matching
    })

    try:
        while True:
            data = await websocket.receive_text()
            try:
                event = json.loads(data)
                if event.get("event") == "pong":
                    state.manager.record_pong(websocket)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        state.manager.disconnect_dashboard(websocket)


@router.websocket("/ws/twitch/chat")
async def twitch_chat_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time Twitch chat updates via EventSub (requires auth)."""
    state = await get_app_state(websocket)

    # Verify authentication before accepting connection
    tenant_id = websocket.cookies.get("tenant_id")
    if not tenant_id:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    state.twitch_chat_connections[websocket] = tenant_id

    # Get channel from database for status
    channel = None
    eventsub_active = False

    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id).limit(1)
        )
        twitch_config = result.scalar_one_or_none()
        if twitch_config:
            channel = twitch_config.channel
            eventsub_mgr = state.eventsub_managers.get(tenant_id)
            eventsub_active = eventsub_mgr.is_connected if eventsub_mgr else False

    # Send connection status immediately
    await websocket.send_json({
        "type": "connected",
        "eventsub_active": eventsub_active,
        "channel": channel,
    })

    try:
        while True:
            data = await websocket.receive_text()
            try:
                event = json.loads(data)
                if event.get("event") == "pong":
                    pass  # Could track pongs if needed
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        state.twitch_chat_connections.pop(websocket, None)


@router.websocket("/ws/{character}")
async def character_websocket(
    websocket: WebSocket,
    character: str,
    token: str = Query(..., description="WebSocket auth token from character settings"),
):
    """WebSocket endpoint for a browser source character.

    Requires token query parameter for authentication (OBS browser sources can't use cookies).
    Example: ws://host/ws/alice?token=abc123...
    """
    state = await get_app_state(websocket)

    # Accept connection first (required for proper close codes)
    await websocket.accept()

    # Validate character exists AND token matches
    try:
        async with get_session() as session:
            result = await session.execute(
                select(Character).where(
                    Character.name == character,
                    Character.ws_token == token,
                )
            )
            db_character = result.scalar_one_or_none()

            if not db_character:
                await websocket.close(code=4004, reason="Invalid character or token")
                return

            # Get tenant_id for tenant-scoped operations
            tenant_id = db_character.tenant_id
            persist_memory = db_character.persist_memory
    except Exception:
        await websocket.close(code=4000, reason="Database error")
        return

    # Use tenant-scoped key for connection manager
    channel_key = f"{tenant_id}:{character}"

    # Register connection with manager (websocket already accepted above)
    manager = state.manager
    if channel_key not in manager._connections:
        manager._connections[channel_key] = []
        manager._channel_state[channel_key] = {"playing": False, "streaming": False}
    manager._connections[channel_key].append(websocket)
    manager._last_pong[websocket] = time.time()  # Initialize pong tracking
    await manager._notify_dashboard()

    # Send hello message with version info for client version checking
    await websocket.send_json({
        "action": "hello",
        "version": __version__,
        "build_id": BUILD_ID,
    })

    try:
        while True:
            data = await websocket.receive_text()
            try:
                event = json.loads(data)
                event_type = event.get("event")

                if event_type == "ended":
                    await manager.set_channel_state(channel_key, "playing", False)
                elif event_type == "stream_ended":
                    await manager.set_channel_state(channel_key, "streaming", False)
                elif event_type == "stream_stopped":
                    # Browser reports actual playback position when forcefully stopped
                    await manager.set_channel_state(channel_key, "streaming", False)
                    actual_text = event.get("spoken_text", "")
                    playback_time = event.get("playback_time", 0)
                    word_count = event.get("word_count", 0)
                    logger.debug(f"[{channel_key}] Stream stopped at {playback_time:.2f}s - {word_count} words actually played: \"{actual_text[:100]}...\"")

                    # Update interrupted message with actual spoken text
                    # channel_key is already in tenant_id:character format
                    if channel_key in state.pending_interrupted:
                        msg_idx, persist, db_id = state.pending_interrupted[channel_key]
                        await update_interrupted_message(
                            state, tenant_id, character, msg_idx, actual_text, persist, db_id
                        )
                        logger.debug(f"[{channel_key}] Updated memory[{msg_idx}] with actual spoken text (persist={persist})")
                        del state.pending_interrupted[channel_key]
                elif event_type == "pong":
                    manager.record_pong(websocket)

            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(channel_key, websocket)
        await manager._notify_dashboard()
