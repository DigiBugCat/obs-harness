"""Authentication and authorization for multi-tenant access.

Uses Twitch OAuth for identity. Whitelist controls who can access.
"""

from typing import Optional

from fastapi import Request, HTTPException

from .config import settings


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
    tenant_id = await get_session_tenant(request)
    if not tenant_id:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated. Please login with Twitch."
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
        from fastapi.responses import RedirectResponse

        tenant_id = await get_session_tenant(request)
        if not tenant_id:
            # Raise an HTTPException that will be caught and turned into a redirect
            raise HTTPException(
                status_code=307,
                detail="Redirect to login",
                headers={"Location": "/login"}
            )
        return tenant_id


# Singleton instance for HTML page auth
require_auth_redirect = RequireAuthRedirect()
