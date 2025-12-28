"""System and health check routes.

Provides version info, feature flags, and health checks.
No authentication required.
"""

import time

from fastapi import APIRouter, Depends

from .. import __version__
from . import get_state
from ..state import AppState

router = APIRouter(tags=["System"])

# Build ID for version checking - changes on every server restart
BUILD_ID = str(int(time.time()))


@router.get("/api/version")
async def get_version():
    """Get server version and build ID for client version checking."""
    return {"version": __version__, "build_id": BUILD_ID}


@router.get("/api/features")
async def get_features(state: AppState = Depends(get_state)):
    """Get enabled feature flags for UI conditional rendering."""
    return {"santa": state.feature_santa_enabled}


@router.get("/health")
async def health_check():
    """Health check endpoint for load balancers and client polling."""
    return {"status": "ok", "build_id": BUILD_ID}
