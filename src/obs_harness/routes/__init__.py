"""Route modules for OBS Harness.

This package contains all FastAPI route handlers, organized by feature area.
"""

from fastapi import Depends, HTTPException, Request

from ..state import AppState


def get_state(request: Request) -> AppState:
    """FastAPI dependency to get shared application state."""
    return request.app.state.app_state


async def require_santa_feature(state: AppState = Depends(get_state)) -> None:
    """FastAPI dependency that requires Santa feature to be enabled."""
    if not state.feature_santa_enabled:
        raise HTTPException(status_code=404, detail="Not found")
