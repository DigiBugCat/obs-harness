"""Preset and history API routes.

Handles text animation presets and playback history.
"""

from fastapi import APIRouter, Depends
from sqlmodel import select

from ..auth import require_auth
from ..database import get_session
from ..models import PlaybackLog, PresetCreate, TextPreset

router = APIRouter(prefix="/api", tags=["Presets"])


@router.get("/presets")
async def get_presets(tenant_id: str = Depends(require_auth)) -> list[TextPreset]:
    """Get all text presets for the current tenant."""
    async with get_session() as session:
        result = await session.execute(
            select(TextPreset).where(TextPreset.tenant_id == tenant_id)
        )
        return list(result.scalars().all())


@router.post("/presets")
async def create_preset(request: PresetCreate, tenant_id: str = Depends(require_auth)) -> TextPreset:
    """Create a new text preset."""
    async with get_session() as session:
        preset = TextPreset(tenant_id=tenant_id, **request.model_dump())
        session.add(preset)
        await session.commit()
        await session.refresh(preset)
        return preset


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: int, tenant_id: str = Depends(require_auth)) -> dict:
    """Delete a text preset."""
    async with get_session() as session:
        result = await session.execute(
            select(TextPreset).where(TextPreset.id == preset_id, TextPreset.tenant_id == tenant_id)
        )
        preset = result.scalar_one_or_none()
        if preset:
            await session.delete(preset)
            await session.commit()
            return {"success": True, "deleted": preset_id}
        return {"success": False, "error": "Preset not found"}


@router.get("/history")
async def get_history(limit: int = 50, tenant_id: str = Depends(require_auth)) -> list[PlaybackLog]:
    """Get recent playback history for the current tenant."""
    async with get_session() as session:
        result = await session.execute(
            select(PlaybackLog)
            .where(PlaybackLog.tenant_id == tenant_id)
            .order_by(PlaybackLog.timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
