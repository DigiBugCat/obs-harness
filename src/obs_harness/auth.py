"""Authentication and authorization for multi-tenant access.

Uses Twitch OAuth for identity. Whitelist controls who can access.
API keys provide programmatic access for external scripts/services.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from fastapi import Depends, Query, Request, HTTPException

from .config import settings

logger = logging.getLogger(__name__)


@dataclass
class AuthContext:
    """Authentication context for dashboard access with moderator support.

    Contains information about the authenticated user and which channel
    they are viewing. Used by routes to determine permissions.
    """

    user_id: str  # Logged-in user's Twitch ID
    username: str  # Logged-in user's username
    effective_tenant_id: str  # Which channel they're viewing
    is_owner: bool  # True if viewing their own channel


class RedirectToLogin(Exception):
    """Raised when user needs to be redirected to login page.

    This exception is caught by an exception handler in app.py
    that returns a proper RedirectResponse.
    """
    pass


def is_allowed(twitch_user_id: str) -> bool:
    """Check if a Twitch user ID is on the whitelist.

    If whitelist is empty, allow all users (development mode).
    """
    allowed = settings.allowed_twitch_ids_set
    if not allowed:
        return True  # No whitelist = allow all (dev mode)
    return twitch_user_id in allowed


async def get_session_tenant(request: Request) -> Optional[str]:
    """Get tenant_id from session cookie.

    Returns None if not authenticated.
    """
    return request.cookies.get("tenant_id")


async def require_auth(request: Request) -> str:
    """FastAPI dependency that requires authenticated session.

    Usage:
        @app.get("/api/characters")
        async def list_characters(tenant_id: str = Depends(require_auth)):
            ...

    Raises:
        HTTPException: 401 if not authenticated
    """
    from sqlmodel import select
    from .database import get_session
    from .models import TwitchConfig

    tenant_id = await get_session_tenant(request)
    if not tenant_id:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login with Twitch."
        )

    # Verify tenant has valid session in database
    async with get_session() as session:
        result = await session.execute(
            select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id).limit(1)
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=401,
                detail="Session expired. Please login again."
            )

    return tenant_id


async def optional_auth(request: Request) -> Optional[str]:
    """FastAPI dependency that optionally gets tenant_id.

    Returns None if not authenticated (doesn't raise).
    Useful for routes that work with or without auth.
    """
    return await get_session_tenant(request)


class RequireAuthRedirect:
    """FastAPI dependency that redirects to login for HTML pages.

    Usage:
        @app.get("/dashboard", response_class=HTMLResponse)
        async def dashboard(tenant_id: str = Depends(require_auth_redirect)):
            ...
    """

    async def __call__(self, request: Request) -> str:
        """Check auth, redirect to login if not authenticated."""
        from sqlmodel import select
        from .database import get_session
        from .models import TwitchConfig

        tenant_id = await get_session_tenant(request)
        if not tenant_id:
            raise RedirectToLogin()

        # Verify tenant has valid session in database
        async with get_session() as session:
            result = await session.execute(
                select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id).limit(1)
            )
            if not result.scalar_one_or_none():
                # Cookie exists but no valid session - redirect to login
                raise RedirectToLogin()

        return tenant_id


# Singleton instance for HTML page auth
require_auth_redirect = RequireAuthRedirect()


class RequireModeratorAuth:
    """FastAPI dependency for dashboard authentication with moderator support.

    Checks:
    1. User is authenticated (has valid tenant_id cookie)
    2. User is either:
       - The owner of the effective_tenant_id
       - A moderator in the broadcaster's allowlist

    The effective_tenant_id is determined by:
    1. Query parameter `?channel=X` if provided
    2. Cookie `effective_channel` if set
    3. Falls back to the user's own tenant_id
    """

    async def __call__(
        self,
        request: Request,
        channel: str | None = Query(default=None, description="Channel to view (tenant_id)"),
    ) -> AuthContext:
        from sqlmodel import select
        from .database import get_session
        from .models import TwitchConfig, Moderator

        # Get authenticated user
        tenant_id = await get_session_tenant(request)
        if not tenant_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        # Verify user session exists and get username
        async with get_session() as session:
            result = await session.execute(
                select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id).limit(1)
            )
            user_config = result.scalar_one_or_none()
            if not user_config:
                raise HTTPException(status_code=401, detail="Session expired")

        # Determine effective tenant (which channel they're viewing)
        effective_tenant_id = (
            channel
            or request.cookies.get("effective_channel")
            or tenant_id
        )

        # Check authorization
        is_owner = effective_tenant_id == tenant_id

        if not is_owner:
            # Check if user is a moderator for this broadcaster
            async with get_session() as session:
                mod_result = await session.execute(
                    select(Moderator).where(
                        Moderator.broadcaster_tenant_id == effective_tenant_id,
                        Moderator.moderator_user_id == tenant_id,
                    ).limit(1)
                )
                if not mod_result.scalar_one_or_none():
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied. You are not a moderator for this channel.",
                    )

        return AuthContext(
            user_id=tenant_id,
            username=user_config.username or tenant_id,
            effective_tenant_id=effective_tenant_id,
            is_owner=is_owner,
        )


# Singleton instance for moderator auth
require_moderator_auth = RequireModeratorAuth()


async def require_owner_only(
    auth: AuthContext = Depends(require_moderator_auth),
) -> AuthContext:
    """Require that the user is the owner (not just a mod).

    Used for routes that only channel owners can access,
    such as creating/deleting characters or modifying configuration.
    """
    if not auth.is_owner:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can perform this action",
        )
    return auth


# =============================================================================
# API Key Authentication
# =============================================================================


def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256.

    Args:
        key: The plaintext API key

    Returns:
        Hex-encoded SHA-256 hash
    """
    return hashlib.sha256(key.encode()).hexdigest()


async def validate_api_key(key: str) -> Optional[str]:
    """Validate an API key and return the tenant_id if valid.

    Also updates the key's last_used_at timestamp.

    Args:
        key: The plaintext API key from the Authorization header

    Returns:
        tenant_id if key is valid, None otherwise
    """
    from sqlmodel import select
    from .database import get_session
    from .models import ApiKey

    # Hash the provided key
    key_hash = hash_api_key(key)

    async with get_session() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash).limit(1)
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            return None

        # Update last_used_at
        api_key.last_used_at = datetime.utcnow()
        await session.commit()

        logger.debug(f"API key authenticated: {api_key.key_prefix}... for tenant {api_key.tenant_id}")
        return api_key.tenant_id


async def require_auth_or_api_key(request: Request) -> str:
    """FastAPI dependency that accepts either cookie OR API key auth.

    This allows both browser sessions (cookie) and external scripts
    (Authorization: Bearer <key>) to access protected endpoints.

    Usage:
        @app.post("/api/characters/{name}/speak")
        async def speak(tenant_id: str = Depends(require_auth_or_api_key)):
            ...

    Raises:
        HTTPException: 401 if neither auth method succeeds
    """
    from sqlmodel import select
    from .database import get_session
    from .models import TwitchConfig

    # Try cookie auth first (for browser sessions)
    tenant_id = await get_session_tenant(request)
    if tenant_id:
        # Verify tenant has valid session in database
        async with get_session() as session:
            result = await session.execute(
                select(TwitchConfig).where(TwitchConfig.tenant_id == tenant_id).limit(1)
            )
            if result.scalar_one_or_none():
                return tenant_id

    # Try API key auth (for external scripts)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        key = auth_header[7:]  # Strip "Bearer " prefix
        tenant_id = await validate_api_key(key)
        if tenant_id:
            return tenant_id

    # Neither auth method succeeded
    raise HTTPException(
        status_code=401,
        detail="Not authenticated. Provide a valid session cookie or Authorization: Bearer <api_key> header."
    )
