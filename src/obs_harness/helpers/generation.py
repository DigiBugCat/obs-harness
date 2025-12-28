"""Active generation tracking helpers.

Manages concurrent text-to-speech and chat generations per character.
Only one generation can be active per character at a time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..state import AppState


async def cancel_active_generation(
    state: "AppState",
    tenant_id: str,
    name: str,
) -> str | None:
    """Cancel any active generation for a character and return partial spoken text.

    Returns:
        The text that was actually spoken before cancellation, or None if no active generation.
    """
    key = state.tenant_key(tenant_id, name)
    gen = state.active_generations.pop(key, None)
    if gen is None:
        return None
    await gen.cancel()  # Async - closes WebSocket immediately
    spoken_text = gen.get_spoken_text()
    return spoken_text
