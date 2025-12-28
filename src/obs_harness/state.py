"""Shared application state for OBS Harness.

This module defines the AppState dataclass that holds all shared state
accessed by route handlers. State is initialized in create_app() and
accessed via request.app.state.app_state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Union

from fastapi import WebSocket

if TYPE_CHECKING:
    from .app import ConnectionManager, OBSHarness
    from .chat_pipeline import ChatPipeline
    from .tts_pipeline import TTSStreamer
    from .twitch_eventsub import TwitchEventSubManager


@dataclass
class AppState:
    """Shared application state accessible from all routes.

    Access via: state = request.app.state.app_state
    """

    # Core infrastructure
    manager: "ConnectionManager"
    harness: "OBSHarness"

    # Per-tenant managers (tenant_id -> manager)
    eventsub_managers: dict[str, "TwitchEventSubManager"] = field(default_factory=dict)

    # WebSocket connections tracking (WebSocket -> tenant_id)
    twitch_chat_connections: dict[WebSocket, str] = field(default_factory=dict)

    # Conversation memory (tenant_id:character_name -> messages)
    conversation_memory: dict[str, list[dict]] = field(default_factory=dict)

    # Pending interrupted messages needing actual spoken text
    # Maps tenant-scoped key -> (msg_idx, persist_memory, db_msg_id)
    pending_interrupted: dict[str, tuple[int, bool, int | None]] = field(default_factory=dict)

    # Generation tracking - only one generation per character at a time
    active_generations: dict[str, Union["ChatPipeline", "TTSStreamer"]] = field(default_factory=dict)
    generation_locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    # Helper methods

    def tenant_key(self, tenant_id: str, name: str) -> str:
        """Create a tenant-scoped key for in-memory dictionaries."""
        return f"{tenant_id}:{name}"

    def get_generation_lock(self, tenant_id: str, name: str) -> asyncio.Lock:
        """Get or create a generation lock for a character."""
        key = self.tenant_key(tenant_id, name)
        if key not in self.generation_locks:
            self.generation_locks[key] = asyncio.Lock()
        return self.generation_locks[key]

    def get_eventsub_manager(self, tenant_id: str) -> "TwitchEventSubManager":
        """Get EventSub manager for a tenant (creates if not exists)."""
        from .twitch_eventsub import TwitchEventSubManager

        if tenant_id not in self.eventsub_managers:
            self.eventsub_managers[tenant_id] = TwitchEventSubManager()
        return self.eventsub_managers[tenant_id]
