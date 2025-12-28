"""FastAPI application factory, connection manager, and OBS harness.

This module has been slimmed down from ~3300 lines to ~600 lines by extracting
routes into separate modules in the routes/ package.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from . import __version__
from .config import settings
from .database import close_db, get_session, init_db
from .helpers.conversation import load_persisted_memory_on_startup
from .helpers.santa import create_redemption_callback, create_santa_state_callback
from .helpers.twitch import create_chat_callback
from .models import (
    Character,
    CharacterStatus,
    ClearTextCommand,
    PlaybackLog,
    PlayCommand,
    SantaConfig,
    StopCommand,
    StopStreamCommand,
    StreamEndCommand,
    StreamStartCommand,
    TextChunkCommand,
    TextCommand,
    TextStreamEndCommand,
    TextStreamStartCommand,
    TwitchConfig,
    VolumeCommand,
    WordTimingCommand,
)
from .routes import auth, characters, moderators, pages, presets, santa, system, tts_providers, twitch, websockets
from .santa_session import SantaSessionManager
from .state import AppState

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for all channels."""

    # Heartbeat constants
    PING_INTERVAL = 25  # seconds - send ping every 25s (under 30s proxy timeout)
    STALE_THRESHOLD = 60  # seconds - close connections without pong for 60s

    def __init__(self) -> None:
        from fastapi import WebSocket
        self._connections: dict[str, list[WebSocket]] = {}  # Multiple connections per channel
        self._channel_state: dict[str, dict[str, Any]] = {}
        self._dashboard_connections: dict[WebSocket, str] = {}  # WebSocket -> tenant_id
        self._last_pong: dict[WebSocket, float] = {}  # Track last pong time per connection

    async def connect(self, channel: str, websocket) -> None:
        """Register a channel connection (supports multiple per channel)."""
        await websocket.accept()
        if channel not in self._connections:
            self._connections[channel] = []
            self._channel_state[channel] = {"playing": False, "streaming": False}
        self._connections[channel].append(websocket)
        self._last_pong[websocket] = time.time()  # Initialize pong time
        logger.info(f"WebSocket connected: {channel} ({len(self._connections[channel])} connections)")
        await self._notify_dashboard()

    def record_pong(self, websocket) -> None:
        """Record that a pong was received from a connection."""
        self._last_pong[websocket] = time.time()

    def disconnect(self, channel: str, websocket=None) -> None:
        """Remove a channel connection. If websocket specified, only remove that one."""
        if channel not in self._connections:
            return
        if websocket is not None:
            # Remove specific websocket
            if websocket in self._connections[channel]:
                self._connections[channel].remove(websocket)
            self._last_pong.pop(websocket, None)  # Clean up pong tracking
            remaining = len(self._connections.get(channel, []))
            logger.info(f"WebSocket disconnected: {channel} ({remaining} connections remaining)")
            # Clean up if no more connections
            if not self._connections[channel]:
                del self._connections[channel]
                self._channel_state.pop(channel, None)
        else:
            # Remove all connections for channel
            for ws in self._connections[channel]:
                self._last_pong.pop(ws, None)  # Clean up pong tracking
            logger.info(f"WebSocket disconnected: {channel} (all connections)")
            del self._connections[channel]
            self._channel_state.pop(channel, None)

    async def connect_dashboard(self, websocket, tenant_id: str) -> None:
        """Register a dashboard connection for a specific tenant."""
        await websocket.accept()
        self._dashboard_connections[websocket] = tenant_id
        self._last_pong[websocket] = time.time()  # Initialize pong time
        # Send current state immediately (only characters for this tenant)
        tenant_characters = [
            ch.model_dump() for ch in self.get_characters()
            if ch.name.startswith(f"{tenant_id}:")  # Filter by tenant-scoped keys
        ]
        await websocket.send_json({"type": "characters", "characters": tenant_characters})

    def disconnect_dashboard(self, websocket) -> None:
        """Remove a dashboard connection."""
        self._dashboard_connections.pop(websocket, None)
        self._last_pong.pop(websocket, None)  # Clean up pong tracking

    async def send_to_channel(self, channel: str, message: dict) -> bool:
        """Send a JSON message to all connections on a channel."""
        if channel not in self._connections or not self._connections[channel]:
            return False
        failed = []
        for ws in self._connections[channel][:]:  # Copy list to allow removal
            try:
                await ws.send_json(message)
            except Exception:
                failed.append(ws)
        # Clean up failed connections
        for ws in failed:
            self.disconnect(channel, ws)
        return len(self._connections.get(channel, [])) > 0

    async def send_bytes_to_channel(self, channel: str, data: bytes) -> bool:
        """Send binary data to all connections on a channel."""
        if channel not in self._connections or not self._connections[channel]:
            return False
        failed = []
        for ws in self._connections[channel][:]:  # Copy list to allow removal
            try:
                await ws.send_bytes(data)
            except Exception:
                failed.append(ws)
        # Clean up failed connections
        for ws in failed:
            self.disconnect(channel, ws)
        return len(self._connections.get(channel, [])) > 0

    def get_characters(self) -> list[CharacterStatus]:
        """Get list of connected characters with status."""
        return [
            CharacterStatus(
                name=name,
                connected=True,
                playing=self._channel_state.get(name, {}).get("playing", False),
                streaming=self._channel_state.get(name, {}).get("streaming", False),
            )
            for name, conns in self._connections.items()
            if conns  # Only include if there are active connections
        ]

    def is_connected(self, channel: str) -> bool:
        """Check if a channel has any connections."""
        return channel in self._connections and len(self._connections[channel]) > 0

    async def set_channel_state(self, channel: str, key: str, value: Any) -> None:
        """Update channel state and notify dashboard."""
        if channel in self._channel_state:
            self._channel_state[channel][key] = value
            await self._notify_dashboard()

    async def _notify_dashboard(self) -> None:
        """Notify all dashboard connections of state changes (filtered by tenant)."""
        all_characters = self.get_characters()
        for ws, tenant_id in list(self._dashboard_connections.items()):
            # Filter to only this tenant's characters (keys are "tenant_id:character")
            tenant_characters = [
                c.model_dump() for c in all_characters
                if c.name.startswith(f"{tenant_id}:")
            ]
            message = {"type": "characters", "characters": tenant_characters}
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect_dashboard(ws)

    async def broadcast_character_sync(self, characters: list[dict], tenant_id: str) -> None:
        """Broadcast full character data to dashboard connections for a specific tenant.

        Used when character settings are changed to sync across all clients.
        """
        message = {"type": "character_sync", "characters": characters}
        for ws, ws_tenant in list(self._dashboard_connections.items()):
            if ws_tenant != tenant_id:
                continue  # Only send to this tenant's connections
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect_dashboard(ws)


class OBSHarness:
    """API for controlling audio and text on OBS browser sources."""

    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager

    async def play(
        self, channel: str, file: str, volume: float = 1.0, loop: bool = False
    ) -> bool:
        """Play an audio file on a channel."""
        cmd = PlayCommand(file=f"/static/audio/{file}", volume=volume, loop=loop)
        success = await self._manager.send_to_channel(channel, cmd.model_dump())
        if success:
            await self._manager.set_channel_state(channel, "playing", True)
            await self._log_playback(channel, file, "audio")
        return success

    async def stop(self, channel: str) -> bool:
        """Stop audio on a channel."""
        cmd = StopCommand()
        success = await self._manager.send_to_channel(channel, cmd.model_dump())
        if success:
            await self._manager.set_channel_state(channel, "playing", False)
        return success

    async def set_volume(self, channel: str, level: float) -> bool:
        """Set volume level on a channel."""
        cmd = VolumeCommand(level=level)
        return await self._manager.send_to_channel(channel, cmd.model_dump())

    async def stream_start(
        self, channel: str, sample_rate: int = 24000, channels: int = 1
    ) -> bool:
        """Start an audio stream on a channel."""
        cmd = StreamStartCommand(sample_rate=sample_rate, channels=channels)
        success = await self._manager.send_to_channel(channel, cmd.model_dump())
        if success:
            await self._manager.set_channel_state(channel, "streaming", True)
            await self._log_playback(channel, "stream", "stream")
            logger.debug(f"[{channel}] Audio stream started (sample_rate={sample_rate})")
        return success

    async def stream_audio(self, channel: str, audio_bytes: bytes) -> bool:
        """Send audio chunk to a channel."""
        return await self._manager.send_bytes_to_channel(channel, audio_bytes)

    async def stream_end(self, channel: str) -> bool:
        """End an audio stream on a channel.

        Note: streaming state is NOT set to False here - it's set when browser
        reports stream_ended event, so dashboard knows when playback finishes.
        """
        cmd = StreamEndCommand()
        logger.debug(f"[{channel}] Audio stream ended")
        return await self._manager.send_to_channel(channel, cmd.model_dump())

    async def stop_stream(self, channel: str) -> bool:
        """Forcefully stop audio stream and clear playback on a channel."""
        cmd = StopStreamCommand()
        success = await self._manager.send_to_channel(channel, cmd.model_dump())
        if success:
            await self._manager.set_channel_state(channel, "streaming", False)
        return success

    async def show_text(
        self,
        channel: str,
        text: str,
        style: str = "typewriter",
        duration: int = 3000,
        position_x: float = 0.5,
        position_y: float = 0.5,
        font_family: str = "Arial",
        font_size: int = 48,
        color: str = "#ffffff",
        stroke_color: str | None = None,
        stroke_width: int = 0,
    ) -> bool:
        """Display animated text on a channel."""
        cmd = TextCommand(
            text=text,
            style=style,
            duration=duration,
            position_x=position_x,
            position_y=position_y,
            font_family=font_family,
            font_size=font_size,
            color=color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
        )
        success = await self._manager.send_to_channel(channel, cmd.model_dump())
        if success:
            await self._log_playback(channel, text, "text")
        return success

    async def clear_text(self, channel: str) -> bool:
        """Clear text overlay on a channel."""
        cmd = ClearTextCommand()
        return await self._manager.send_to_channel(channel, cmd.model_dump())

    async def text_stream_start(
        self,
        channel: str,
        font_family: str = "Arial",
        font_size: int = 48,
        color: str = "#ffffff",
        stroke_color: str | None = None,
        stroke_width: int = 0,
        position_x: float = 0.5,
        position_y: float = 0.5,
        instant_reveal: bool = False,
    ) -> bool:
        """Start streaming text on a channel."""
        cmd = TextStreamStartCommand(
            font_family=font_family,
            font_size=font_size,
            color=color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            position_x=position_x,
            position_y=position_y,
            instant_reveal=instant_reveal,
        )
        return await self._manager.send_to_channel(channel, cmd.model_dump())

    async def text_chunk(self, channel: str, text: str) -> bool:
        """Send text chunk to a channel for streaming display."""
        cmd = TextChunkCommand(text=text)
        return await self._manager.send_to_channel(channel, cmd.model_dump())

    async def text_stream_end(self, channel: str) -> bool:
        """End streaming text on a channel."""
        cmd = TextStreamEndCommand()
        return await self._manager.send_to_channel(channel, cmd.model_dump())

    async def word_timing(self, channel: str, words: list[dict]) -> bool:
        """Send word timing data to a channel for synced text reveal."""
        cmd = WordTimingCommand(words=words)
        return await self._manager.send_to_channel(channel, cmd.model_dump())

    def list_characters(self) -> list[CharacterStatus]:
        """Get list of connected characters."""
        return self._manager.get_characters()

    def is_connected(self, channel: str) -> bool:
        """Check if a channel is connected."""
        return self._manager.is_connected(channel)

    def is_streaming(self, channel: str) -> bool:
        """Check if a channel is currently streaming audio."""
        return self._manager._channel_state.get(channel, {}).get("streaming", False)

    async def wait_for_stream_complete(self, channel: str, timeout: float = 60.0) -> bool:
        """Wait for audio stream to complete on a channel.

        Args:
            channel: The channel name
            timeout: Maximum seconds to wait

        Returns:
            True if stream completed, False if timeout
        """
        start = asyncio.get_event_loop().time()
        while self.is_streaming(channel):
            if asyncio.get_event_loop().time() - start > timeout:
                return False
            await asyncio.sleep(0.1)
        return True

    async def _log_playback(self, channel: str, content: str, content_type: str) -> None:
        """Log a playback event."""
        try:
            async with get_session() as session:
                log = PlaybackLog(channel=channel, content=content, content_type=content_type)
                session.add(log)
        except Exception:
            pass  # Don't fail on logging errors


def create_app(
    db_url: str = "sqlite+aiosqlite:///obs_harness.db",
    static_dir: str | Path | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    if static_dir is None:
        static_dir = Path(__file__).parent.parent.parent / "static"
    static_dir = Path(static_dir)

    # Create core infrastructure
    manager = ConnectionManager()
    harness = OBSHarness(manager)

    # Create shared application state
    app_state = AppState(
        manager=manager,
        harness=harness,
        feature_santa_enabled=settings.feature_santa_enabled,
    )

    async def initialize_tenant(
        tenant_id: str,
        twitch_config: TwitchConfig,
        santa_config: SantaConfig | None,
    ) -> None:
        """Initialize EventSub and Santa managers for a tenant."""
        # Look up channel's user ID if different from logged-in user
        channel_user_id = twitch_config.user_id
        if twitch_config.channel and twitch_config.channel.lower() != (twitch_config.username or "").lower():
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://api.twitch.tv/helix/users?login={twitch_config.channel}",
                        headers={
                            "Authorization": f"Bearer {twitch_config.access_token}",
                            "Client-Id": settings.twitch_client_id,
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("data"):
                            channel_user_id = data["data"][0]["id"]
            except Exception as e:
                logger.warning(f"Failed to look up channel user ID for tenant {tenant_id}: {e}")

        # Initialize EventSub manager for this tenant
        eventsub_mgr = app_state.get_eventsub_manager(tenant_id)

        # Check if Santa is enabled
        santa_enabled = santa_config and santa_config.enabled
        reward_id = santa_config.reward_id if santa_config else None

        # Set callbacks and start EventSub
        eventsub_mgr.set_chat_callback(create_chat_callback(app_state, tenant_id))
        await eventsub_mgr.start(
            access_token=twitch_config.access_token,
            client_id=settings.twitch_client_id,
            broadcaster_user_id=channel_user_id,
            user_id=twitch_config.user_id,
            refresh_token=twitch_config.refresh_token,
            reward_id=reward_id if santa_enabled else None,
            on_redemption=create_redemption_callback(app_state, tenant_id) if santa_enabled else None,
            subscribe_to_chat=True,
            subscribe_to_redemptions=santa_enabled,
        )
        logger.info(f"EventSub connected for tenant {tenant_id} (channel: {twitch_config.channel})")

        # Initialize Santa manager for this tenant (only if feature is enabled)
        if app_state.feature_santa_enabled and santa_config:
            santa_mgr = SantaSessionManager(
                harness=harness,
                eventsub=eventsub_mgr,
                character_name=santa_config.character_name,
                max_followups=santa_config.max_followups,
                response_timeout=santa_config.response_timeout_seconds,
                debounce_seconds=santa_config.debounce_seconds,
                chat_vote_seconds=santa_config.chat_vote_seconds,
            )
            santa_mgr.set_state_callback(create_santa_state_callback(app_state, tenant_id))
            app_state.set_santa_manager(tenant_id, santa_mgr)
            logger.info(f"Santa manager initialized for tenant {tenant_id}")

    async def ping_all_connections():
        """Background task: Send pings to all WebSocket clients and close stale connections."""
        while True:
            await asyncio.sleep(manager.PING_INTERVAL)
            now = time.time()

            # Ping channel connections
            for channel, websockets in list(manager._connections.items()):
                for ws in list(websockets):
                    try:
                        await ws.send_json({"action": "ping", "ts": now})
                    except Exception:
                        manager.disconnect(channel, ws)

            # Ping dashboard connections
            for ws in list(manager._dashboard_connections):
                try:
                    await ws.send_json({"type": "ping", "ts": now})
                except Exception:
                    manager.disconnect_dashboard(ws)

            # Ping Santa dashboard connections
            for ws in list(app_state.santa_dashboard_connections.keys()):
                try:
                    await ws.send_json({"type": "ping", "ts": now})
                except Exception:
                    app_state.santa_dashboard_connections.pop(ws, None)

            # Ping Twitch chat connections
            for ws in list(app_state.twitch_chat_connections.keys()):
                try:
                    await ws.send_json({"type": "ping", "ts": now})
                except Exception:
                    app_state.twitch_chat_connections.pop(ws, None)

            # Close stale connections (no pong received within threshold)
            stale_threshold = now - manager.STALE_THRESHOLD
            for ws, last_pong in list(manager._last_pong.items()):
                if last_pong < stale_threshold:
                    logger.warning(f"Closing stale WebSocket connection (no pong for {now - last_pong:.0f}s)")
                    try:
                        await ws.close()
                    except Exception:
                        pass
                    # Clean up tracking (disconnect handlers will also try, but be safe)
                    manager._last_pong.pop(ws, None)

    async def eventsub_auto_reconnect():
        """Background task to auto-reconnect EventSub for all tenants if disconnected."""
        INITIAL_DELAY = 10  # Start checking after 10 seconds
        MAX_DELAY = 300  # Max 5 minutes between attempts
        CHECK_INTERVAL = 30  # Check all tenants every 30 seconds
        tenant_delays: dict[str, int] = {}

        while True:
            await asyncio.sleep(CHECK_INTERVAL)

            # Get all TwitchConfigs from DB
            try:
                async with get_session() as session:
                    result = await session.execute(select(TwitchConfig))
                    twitch_configs = list(result.scalars().all())

                for twitch_config in twitch_configs:
                    if not twitch_config.access_token or not twitch_config.user_id:
                        continue  # No valid config, can't reconnect

                    tenant_id = twitch_config.tenant_id
                    eventsub_mgr = app_state.eventsub_managers.get(tenant_id)

                    # Skip if no manager exists (will be created on login)
                    if not eventsub_mgr:
                        continue

                    # Skip if already connected - reset backoff on success
                    if eventsub_mgr.is_connected:
                        tenant_delays[tenant_id] = INITIAL_DELAY
                        continue

                    # Get Santa config for this tenant
                    async with get_session() as session:
                        santa_result = await session.execute(
                            select(SantaConfig).where(SantaConfig.tenant_id == tenant_id).limit(1)
                        )
                        santa_config = santa_result.scalar_one_or_none()

                    # Look up channel's user ID if different from logged-in user
                    channel_user_id = twitch_config.user_id
                    if twitch_config.channel and twitch_config.channel.lower() != (twitch_config.username or "").lower():
                        try:
                            import httpx
                            async with httpx.AsyncClient() as client:
                                resp = await client.get(
                                    f"https://api.twitch.tv/helix/users?login={twitch_config.channel}",
                                    headers={
                                        "Authorization": f"Bearer {twitch_config.access_token}",
                                        "Client-Id": settings.twitch_client_id,
                                    }
                                )
                                if resp.status_code == 200:
                                    data = resp.json()
                                    if data.get("data"):
                                        channel_user_id = data["data"][0]["id"]
                        except Exception:
                            pass  # Use default user_id

                    # Check if Santa is enabled
                    santa_enabled = santa_config and santa_config.enabled
                    reward_id = santa_config.reward_id if santa_config else None

                    # Try to reconnect
                    try:
                        logger.info(f"EventSub disconnected for tenant {tenant_id}, attempting auto-reconnect...")
                        eventsub_mgr.set_chat_callback(create_chat_callback(app_state, tenant_id))
                        await eventsub_mgr.start(
                            access_token=twitch_config.access_token,
                            client_id=settings.twitch_client_id,
                            broadcaster_user_id=channel_user_id,
                            user_id=twitch_config.user_id,
                            refresh_token=twitch_config.refresh_token,
                            reward_id=reward_id if santa_enabled else None,
                            on_redemption=create_redemption_callback(app_state, tenant_id) if santa_enabled else None,
                            subscribe_to_chat=True,
                            subscribe_to_redemptions=santa_enabled,
                        )
                        logger.info(f"EventSub auto-reconnect successful for tenant {tenant_id}")
                        tenant_delays[tenant_id] = INITIAL_DELAY  # Reset backoff
                    except Exception as e:
                        # Increase backoff for next attempt
                        current_delay = tenant_delays.get(tenant_id, INITIAL_DELAY)
                        tenant_delays[tenant_id] = min(current_delay * 2, MAX_DELAY)
                        logger.warning(f"EventSub auto-reconnect failed for tenant {tenant_id}: {e}")

            except Exception as e:
                logger.warning(f"EventSub auto-reconnect error: {e}")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db(db_url)

        # Load persisted conversation memory
        try:
            await load_persisted_memory_on_startup(app_state)
        except Exception as e:
            logger.warning(f"Failed to load persisted memory: {e}")

        # Initialize all tenants from saved configs
        try:
            async with get_session() as session:
                result = await session.execute(select(TwitchConfig))
                twitch_configs = list(result.scalars().all())

                for twitch_config in twitch_configs:
                    if not twitch_config.access_token or not twitch_config.user_id:
                        continue

                    tenant_id = twitch_config.tenant_id

                    # Get Santa config for this tenant
                    santa_result = await session.execute(
                        select(SantaConfig).where(SantaConfig.tenant_id == tenant_id).limit(1)
                    )
                    santa_config = santa_result.scalar_one_or_none()

                    try:
                        await initialize_tenant(tenant_id, twitch_config, santa_config)
                    except Exception as e:
                        logger.warning(f"Failed to initialize tenant {tenant_id}: {e}")

        except Exception as e:
            logger.warning(f"Failed to initialize tenants on startup: {e}")

        # Start background tasks
        ping_task = asyncio.create_task(ping_all_connections())
        reconnect_task = asyncio.create_task(eventsub_auto_reconnect())

        yield

        # Cancel background tasks on shutdown
        ping_task.cancel()
        reconnect_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass
        try:
            await reconnect_task
        except asyncio.CancelledError:
            pass

        # Stop all EventSub connections
        for tenant_id, eventsub_mgr in app_state.eventsub_managers.items():
            try:
                await eventsub_mgr.stop()
            except Exception as e:
                logger.warning(f"Error stopping EventSub for {tenant_id}: {e}")

        await close_db()

    # Create FastAPI app
    app = FastAPI(
        title="OBS Harness",
        version=__version__,
        lifespan=lifespan,
    )

    # Add exception handler for auth redirects
    from fastapi import Request
    from fastapi.responses import RedirectResponse
    from .auth import RedirectToLogin

    @app.exception_handler(RedirectToLogin)
    async def redirect_to_login_handler(request: Request, exc: RedirectToLogin):
        """Redirect to login page when authentication is required."""
        return RedirectResponse(url="/login", status_code=302)

    # Store state on app for access from routes
    app.state.app_state = app_state
    app.state.harness = harness
    app.state.static_dir = static_dir

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Include all routers
    app.include_router(system.router)
    app.include_router(pages.router)
    app.include_router(websockets.router)
    app.include_router(auth.router)
    app.include_router(twitch.router)
    app.include_router(tts_providers.router)
    app.include_router(presets.router)
    app.include_router(characters.router)
    app.include_router(santa.router)
    app.include_router(moderators.router)

    return app
