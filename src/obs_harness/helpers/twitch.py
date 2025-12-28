"""Twitch helper functions.

Provides callback factories and token refresh for Twitch integration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from ..config import settings
from ..database import get_session
from ..models import TwitchConfig
from sqlmodel import select

if TYPE_CHECKING:
    from ..state import AppState
    from ..twitch_eventsub import ChatMessage

logger = logging.getLogger(__name__)


async def refresh_twitch_token(tenant_id: str) -> bool:
    """Refresh the Twitch access token using the refresh token.

    Returns True if successful, False otherwise.
    """
    client_id = settings.twitch_client_id
    client_secret = settings.twitch_client_secret

    if not client_id or not client_secret:
        logger.error("Cannot refresh token: TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET not configured")
        return False

    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id)
        )
        twitch_config = result.scalar_one_or_none()

        if not twitch_config or not twitch_config.refresh_token:
            logger.warning("Cannot refresh token: no refresh token stored")
            return False

        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": twitch_config.refresh_token,
                        "grant_type": "refresh_token",
                    }
                )

                if resp.status_code != 200:
                    logger.error(f"Token refresh failed: {resp.status_code} - {resp.text}")
                    return False

                token_data = resp.json()
                new_access_token = token_data["access_token"]
                new_refresh_token = token_data.get("refresh_token", twitch_config.refresh_token)
                expires_in = token_data.get("expires_in", 3600)

                # Update database
                twitch_config.access_token = new_access_token
                twitch_config.refresh_token = new_refresh_token
                twitch_config.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                twitch_config.updated_at = datetime.utcnow()
                await session.commit()

                logger.info(f"Token refreshed successfully, expires in {expires_in}s")
                return True

        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return False


def create_chat_callback(state: "AppState", tenant_id: str):
    """Create a tenant-specific chat message callback closure."""
    async def on_chat_message(message: "ChatMessage") -> None:
        """Callback for incoming chat messages - broadcast to this tenant's chat WebSocket clients and Santa."""
        # Broadcast to WebSocket clients for this tenant only
        msg_data = {
            "type": "chat_message",
            "message": {
                "user": message.user_display_name,
                "text": message.message,
                "timestamp": message.timestamp.isoformat(),
                "tenant_id": tenant_id,
            }
        }
        for ws, ws_tenant in list(state.twitch_chat_connections.items()):
            if ws_tenant != tenant_id:
                continue  # Only send to this tenant's connections
            try:
                await ws.send_json(msg_data)
            except Exception:
                state.twitch_chat_connections.pop(ws, None)

        # Forward to Santa if there's an active session waiting for followup
        santa_mgr = state.get_santa_manager(tenant_id)
        if santa_mgr and santa_mgr.is_active:
            await santa_mgr.receive_chat_message(
                user_id=message.user_id,
                username=message.user_login,
                message=message.message,
            )
    return on_chat_message
