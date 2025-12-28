"""API key resolution helpers for BYOK (Bring Your Own Key) support.

Provides functions to:
- Get API keys with tenant-specific override, falling back to global
- Mask keys for safe display in UI
"""

from sqlmodel import select

from ..config import settings
from ..database import get_session
from ..models import UserSettings


def mask_key(key: str | None) -> str | None:
    """Mask API key showing only last 4 chars.

    Args:
        key: The API key to mask

    Returns:
        Masked key like "••••••••abcd" or None if key is None/too short
    """
    if not key or len(key) < 8:
        return None
    return "•" * (len(key) - 4) + key[-4:]


async def get_user_settings(tenant_id: str) -> UserSettings | None:
    """Get UserSettings for a tenant."""
    async with get_session() as session:
        result = await session.execute(
            select(UserSettings).where(UserSettings.tenant_id == tenant_id).limit(1)
        )
        return result.scalar_one_or_none()


async def get_api_key(tenant_id: str, provider: str) -> str | None:
    """Get API key for tenant, falling back to global environment key.

    Args:
        tenant_id: The tenant's ID
        provider: One of "elevenlabs", "cartesia", "openrouter", "kokoro"

    Returns:
        The API key to use, or None if not configured anywhere.
        For self-hosted providers like Kokoro, returns "not-needed".
    """
    # Kokoro is self-hosted - no API key required
    if provider == "kokoro":
        return "not-needed"

    # Check tenant-specific key first
    user_settings = await get_user_settings(tenant_id)

    if user_settings:
        if provider == "elevenlabs" and user_settings.elevenlabs_api_key:
            return user_settings.elevenlabs_api_key
        elif provider == "cartesia" and user_settings.cartesia_api_key:
            return user_settings.cartesia_api_key
        elif provider == "openrouter" and user_settings.openrouter_api_key:
            return user_settings.openrouter_api_key

    # Fall back to global environment key
    if provider == "elevenlabs":
        return settings.elevenlabs_api_key
    elif provider == "cartesia":
        return settings.cartesia_api_key
    elif provider == "openrouter":
        return settings.openrouter_api_key

    return None


async def get_api_key_status(tenant_id: str) -> dict:
    """Get status of all API keys for a tenant.

    Returns dict with masked keys and source (tenant/global/none).
    """
    user_settings = await get_user_settings(tenant_id)

    def get_status(tenant_key: str | None, global_key: str | None) -> dict:
        if tenant_key:
            return {
                "has_key": True,
                "source": "user",
                "masked": mask_key(tenant_key),
            }
        elif global_key:
            return {
                "has_key": True,
                "source": "global",
                "masked": mask_key(global_key),
            }
        else:
            return {
                "has_key": False,
                "source": None,
                "masked": None,
            }

    return {
        "elevenlabs": get_status(
            user_settings.elevenlabs_api_key if user_settings else None,
            settings.elevenlabs_api_key,
        ),
        "cartesia": get_status(
            user_settings.cartesia_api_key if user_settings else None,
            settings.cartesia_api_key,
        ),
        "openrouter": get_status(
            user_settings.openrouter_api_key if user_settings else None,
            settings.openrouter_api_key,
        ),
        # Kokoro is self-hosted, no API key needed
        "kokoro": {
            "has_key": True,
            "source": "local",
            "masked": "(self-hosted)",
        },
    }
