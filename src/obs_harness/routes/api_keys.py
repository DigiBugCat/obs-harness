"""API key management routes.

Handles creation, listing, and deletion of API keys for programmatic access.
"""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select

from ..auth import require_auth, hash_api_key
from ..database import get_session
from ..models import (
    ApiKey,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/api-keys", tags=["API Keys"])


@router.get("")
async def list_api_keys(
    tenant_id: str = Depends(require_auth),
) -> dict:
    """List all API keys for the current tenant.

    Returns key metadata (prefix, label, timestamps) but NOT the actual keys.
    """
    async with get_session() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at.desc())
        )
        keys = result.scalars().all()

    return {
        "api_keys": [
            ApiKeyResponse(
                id=k.id,
                key_prefix=k.key_prefix,
                label=k.label,
                created_at=k.created_at,
                last_used_at=k.last_used_at,
            ).model_dump()
            for k in keys
        ]
    }


@router.post("")
async def create_api_key(
    request: ApiKeyCreate,
    tenant_id: str = Depends(require_auth),
) -> ApiKeyCreated:
    """Create a new API key.

    IMPORTANT: The full key is only returned ONCE in this response.
    Store it securely - it cannot be retrieved later.
    """
    # Generate a secure random key with obs_ prefix
    raw_key = secrets.token_urlsafe(32)
    full_key = f"obs_{raw_key}"
    key_prefix = full_key[:12]  # "obs_" + first 8 chars of random part
    key_hash = hash_api_key(full_key)

    async with get_session() as session:
        api_key = ApiKey(
            tenant_id=tenant_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            label=request.label,
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

    logger.info(f"Created API key '{request.label}' ({key_prefix}...) for tenant {tenant_id}")

    return ApiKeyCreated(
        id=api_key.id,
        key=full_key,  # Only time the full key is returned!
        key_prefix=key_prefix,
        label=request.label,
        created_at=api_key.created_at,
    )


@router.delete("/{key_id}")
async def delete_api_key(
    key_id: int,
    tenant_id: str = Depends(require_auth),
) -> dict:
    """Delete (revoke) an API key.

    Once deleted, the key can no longer be used for authentication.
    """
    async with get_session() as session:
        result = await session.execute(
            select(ApiKey).where(
                ApiKey.id == key_id,
                ApiKey.tenant_id == tenant_id,  # Ensure ownership
            ).limit(1)
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise HTTPException(status_code=404, detail="API key not found")

        key_prefix = api_key.key_prefix
        label = api_key.label
        await session.delete(api_key)
        await session.commit()

    logger.info(f"Deleted API key '{label}' ({key_prefix}...) for tenant {tenant_id}")
    return {"success": True}
