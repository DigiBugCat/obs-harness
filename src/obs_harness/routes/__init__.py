"""Route modules for OBS Harness.

This package contains all FastAPI route handlers, organized by feature area.
"""

from fastapi import Request

from ..state import AppState


def get_state(request: Request) -> AppState:
    """FastAPI dependency to get shared application state."""
    return request.app.state.app_state
