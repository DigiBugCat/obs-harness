"""OAuth authentication routes.

Handles Twitch OAuth authorization code flow.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlmodel import select

from ..auth import is_allowed
from ..config import settings
from ..database import get_session
from ..helpers.santa import create_santa_state_callback
from ..helpers.twitch import create_chat_callback
from ..models import SantaConfig, TwitchConfig
from ..santa_session import SantaSessionManager
from . import get_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


def get_static_dir(request: Request) -> Path:
    """Get static directory path from app state."""
    return request.app.state.static_dir


@router.get("/twitch")
async def auth_twitch_start():
    """Start OAuth authorization code flow - redirects to Twitch."""
    client_id = settings.twitch_client_id
    if not client_id:
        raise HTTPException(status_code=500, detail="TWITCH_CLIENT_ID not configured")

    redirect_uri = settings.twitch_redirect_uri

    scopes = [
        "chat:read",
        "user:read:chat",
        "user:write:chat",
        "channel:read:redemptions",
        "channel:manage:redemptions",
    ]

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",  # Authorization code flow
        "scope": " ".join(scopes),
    }

    auth_url = f"https://id.twitch.tv/oauth2/authorize?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def auth_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """Handle OAuth callback - exchange authorization code for tokens."""
    state = get_state(request)
    static_dir = get_static_dir(request)

    # Check for OAuth errors
    if error:
        logger.error(f"OAuth error: {error} - {error_description}")
        return RedirectResponse(url=f"/login?error={error}")

    if not code:
        # No code - might be legacy implicit flow, serve the page
        twitch_path = static_dir / "twitch.html"
        if twitch_path.exists():
            return FileResponse(twitch_path)
        return HTMLResponse("<html><body><h1>Auth Error</h1><p>No authorization code received.</p></body></html>")

    # Exchange authorization code for tokens
    client_id = settings.twitch_client_id
    client_secret = settings.twitch_client_secret
    redirect_uri = settings.twitch_redirect_uri

    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="TWITCH_CLIENT_ID or TWITCH_CLIENT_SECRET not configured")

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # Exchange code for tokens
            token_resp = await client.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                }
            )

            if token_resp.status_code != 200:
                logger.error(f"Token exchange failed: {token_resp.status_code} - {token_resp.text}")
                return RedirectResponse(url="/login?error=token_exchange_failed")

            token_data = token_resp.json()
            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour

            # Get user info
            user_resp = await client.get(
                "https://api.twitch.tv/helix/users",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": client_id,
                }
            )

            if user_resp.status_code != 200:
                logger.error(f"User info fetch failed: {user_resp.status_code}")
                return RedirectResponse(url="/login?error=user_fetch_failed")

            user_data = user_resp.json()["data"][0]
            user_id = user_data["id"]
            username = user_data["login"]

            # Check whitelist
            if not is_allowed(user_id):
                logger.warning(f"Access denied for Twitch user {username} (ID: {user_id}) - not on whitelist")
                return RedirectResponse(url="/login?error=not_allowed")

            # Calculate token expiry
            token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

            # tenant_id is the user's Twitch ID
            tenant_id = user_id

            # Save to database
            async with get_session() as session:
                result = await session.execute(
                    select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id).limit(1)
                )
                twitch_config = result.scalar_one_or_none()

                if twitch_config:
                    twitch_config.access_token = access_token
                    twitch_config.refresh_token = refresh_token
                    twitch_config.token_expires_at = token_expires_at
                    twitch_config.user_id = user_id
                    twitch_config.username = username
                    twitch_config.channel = username  # Default to own channel
                    twitch_config.updated_at = datetime.utcnow()
                else:
                    twitch_config = TwitchConfig(
                        tenant_id=tenant_id,
                        access_token=access_token,
                        refresh_token=refresh_token,
                        token_expires_at=token_expires_at,
                        user_id=user_id,
                        username=username,
                        channel=username,  # Default to own channel
                    )
                    session.add(twitch_config)

                await session.commit()

            # Get or create Santa config for this tenant
            santa_config = None
            async with get_session() as session:
                santa_result = await session.execute(
                    select(SantaConfig).where(SantaConfig.tenant_id == tenant_id).limit(1)
                )
                santa_config = santa_result.scalar_one_or_none()

                if state.feature_santa_enabled and not santa_config:
                    # Create default Santa config for new tenant
                    santa_config = SantaConfig(tenant_id=tenant_id)
                    session.add(santa_config)
                    await session.commit()
                    await session.refresh(santa_config)

            # Initialize EventSub manager for this tenant
            eventsub_mgr = state.get_eventsub_manager(tenant_id)
            eventsub_mgr.set_chat_callback(create_chat_callback(state, tenant_id))
            await eventsub_mgr.start(
                access_token=access_token,
                client_id=client_id,
                broadcaster_user_id=user_id,
                user_id=user_id,
                subscribe_to_chat=True,
                subscribe_to_redemptions=False,
            )

            # Initialize Santa manager if config exists (only if feature is enabled)
            if state.feature_santa_enabled and santa_config:
                santa_mgr = SantaSessionManager(
                    harness=state.harness,
                    eventsub=eventsub_mgr,
                    character_name=santa_config.character_name,
                    max_followups=santa_config.max_followups,
                    response_timeout=santa_config.response_timeout_seconds,
                    debounce_seconds=santa_config.debounce_seconds,
                    chat_vote_seconds=santa_config.chat_vote_seconds,
                )
                santa_mgr.set_state_callback(create_santa_state_callback(state, tenant_id))
                state.set_santa_manager(tenant_id, santa_mgr)

            logger.info(f"OAuth complete, EventSub started for {username} (tenant: {tenant_id})")

            # Set session cookie and redirect to dashboard
            response = RedirectResponse(url="/", status_code=302)
            response.set_cookie(
                "tenant_id",
                user_id,
                httponly=True,
                secure=True,  # HTTPS only in production
                samesite="lax",
                max_age=86400 * 7  # 7 days
            )
            return response

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        return RedirectResponse(url="/login?error=callback_failed")
