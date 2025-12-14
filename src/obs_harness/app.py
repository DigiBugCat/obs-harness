"""FastAPI application factory, routes, and OBSHarness class."""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from .database import close_db, get_session, init_db
from .elevenlabs import ElevenLabsClient, ElevenLabsError, estimate_tts_duration_ms
from .models import (
    Channel,
    ChannelCreate,
    ChannelResponse,
    ChannelStatus,
    ChannelUpdate,
    ClearTextCommand,
    PlaybackLog,
    PlayCommand,
    PlayRequest,
    PresetCreate,
    StopCommand,
    StreamEndCommand,
    StreamStartCommand,
    StreamStartRequest,
    TextCommand,
    TextPreset,
    TextRequest,
    TTSRequest,
    VolumeCommand,
    VolumeRequest,
)


class ConnectionManager:
    """Manages WebSocket connections for all channels."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._channel_state: dict[str, dict[str, Any]] = {}
        self._dashboard_connections: list[WebSocket] = []

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        """Register a channel connection."""
        await websocket.accept()
        self._connections[channel] = websocket
        self._channel_state[channel] = {"playing": False, "streaming": False}
        await self._notify_dashboard()

    def disconnect(self, channel: str) -> None:
        """Remove a channel connection."""
        self._connections.pop(channel, None)
        self._channel_state.pop(channel, None)

    async def connect_dashboard(self, websocket: WebSocket) -> None:
        """Register a dashboard connection."""
        await websocket.accept()
        self._dashboard_connections.append(websocket)
        # Send current state immediately
        await websocket.send_json({"type": "channels", "channels": [ch.model_dump() for ch in self.get_channels()]})

    def disconnect_dashboard(self, websocket: WebSocket) -> None:
        """Remove a dashboard connection."""
        if websocket in self._dashboard_connections:
            self._dashboard_connections.remove(websocket)

    async def send_to_channel(self, channel: str, message: dict) -> bool:
        """Send a JSON message to a specific channel."""
        if channel not in self._connections:
            return False
        try:
            await self._connections[channel].send_json(message)
            return True
        except Exception:
            self.disconnect(channel)
            return False

    async def send_bytes_to_channel(self, channel: str, data: bytes) -> bool:
        """Send binary data to a specific channel."""
        if channel not in self._connections:
            return False
        try:
            await self._connections[channel].send_bytes(data)
            return True
        except Exception:
            self.disconnect(channel)
            return False

    def get_channels(self) -> list[ChannelStatus]:
        """Get list of connected channels with status."""
        return [
            ChannelStatus(
                name=name,
                connected=True,
                playing=self._channel_state.get(name, {}).get("playing", False),
                streaming=self._channel_state.get(name, {}).get("streaming", False),
            )
            for name in self._connections
        ]

    def is_connected(self, channel: str) -> bool:
        """Check if a channel is connected."""
        return channel in self._connections

    def set_channel_state(self, channel: str, key: str, value: Any) -> None:
        """Update channel state."""
        if channel in self._channel_state:
            self._channel_state[channel][key] = value

    async def _notify_dashboard(self) -> None:
        """Notify all dashboard connections of state changes."""
        message = {"type": "channels", "channels": [c.model_dump() for c in self.get_channels()]}
        for ws in self._dashboard_connections[:]:
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
            self._manager.set_channel_state(channel, "playing", True)
            await self._log_playback(channel, file, "audio")
        return success

    async def stop(self, channel: str) -> bool:
        """Stop audio on a channel."""
        cmd = StopCommand()
        success = await self._manager.send_to_channel(channel, cmd.model_dump())
        if success:
            self._manager.set_channel_state(channel, "playing", False)
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
            self._manager.set_channel_state(channel, "streaming", True)
            await self._log_playback(channel, "stream", "stream")
        return success

    async def stream_audio(self, channel: str, audio_bytes: bytes) -> bool:
        """Send audio chunk to a channel."""
        return await self._manager.send_bytes_to_channel(channel, audio_bytes)

    async def stream_end(self, channel: str) -> bool:
        """End an audio stream on a channel."""
        cmd = StreamEndCommand()
        success = await self._manager.send_to_channel(channel, cmd.model_dump())
        if success:
            self._manager.set_channel_state(channel, "streaming", False)
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

    def list_channels(self) -> list[ChannelStatus]:
        """Get list of connected channels."""
        return self._manager.get_channels()

    def is_connected(self, channel: str) -> bool:
        """Check if a channel is connected."""
        return self._manager.is_connected(channel)

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

    manager = ConnectionManager()
    harness = OBSHarness(manager)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db(db_url)
        yield
        await close_db()

    app = FastAPI(
        title="OBS Audio Harness",
        description="Push audio and animated text to OBS via browser sources",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Attach harness to app state for external access
    app.state.harness = harness
    app.state.manager = manager

    # Mount static files
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # =========================================================================
    # Page Routes
    # =========================================================================

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        """Serve the dashboard page."""
        dashboard_path = static_dir / "dashboard.html"
        if dashboard_path.exists():
            return FileResponse(dashboard_path)
        return HTMLResponse("<html><body><h1>OBS Harness Dashboard</h1><p>Dashboard not found.</p></body></html>")

    @app.get("/channel/{name}", response_class=HTMLResponse)
    async def channel_page(name: str):
        """Serve the browser source page for a channel."""
        channel_path = static_dir / "channel.html"
        if channel_path.exists():
            return FileResponse(channel_path)
        return HTMLResponse(f"<html><body><h1>Channel: {name}</h1><p>Channel template not found.</p></body></html>")

    @app.get("/editor", response_class=HTMLResponse)
    async def editor_page():
        """Serve the text animation editor page."""
        editor_path = static_dir / "editor.html"
        if editor_path.exists():
            return FileResponse(editor_path)
        return HTMLResponse("<html><body><h1>Text Editor</h1><p>Editor not found.</p></body></html>")

    # =========================================================================
    # WebSocket Routes
    # =========================================================================

    # Dashboard WebSocket must be defined BEFORE the channel wildcard route
    @app.websocket("/ws/dashboard")
    async def dashboard_websocket(websocket: WebSocket):
        """WebSocket endpoint for dashboard live updates."""
        await manager.connect_dashboard(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect_dashboard(websocket)

    @app.websocket("/ws/{channel}")
    async def channel_websocket(websocket: WebSocket, channel: str):
        """WebSocket endpoint for a browser source channel."""
        # Accept connection first (required for proper close codes)
        await websocket.accept()

        # Validate channel exists
        try:
            async with get_session() as session:
                result = await session.execute(select(Channel).where(Channel.name == channel))
                db_channel = result.scalar_one_or_none()

                if not db_channel:
                    await websocket.close(code=4004, reason="Channel not found. Create it first.")
                    return
        except Exception:
            await websocket.close(code=4000, reason="Database error")
            return

        # Register connection with manager (don't call accept again)
        manager._connections[channel] = websocket
        manager._channel_state[channel] = {"playing": False, "streaming": False}
        await manager._notify_dashboard()

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    event = json.loads(data)
                    event_type = event.get("event")

                    if event_type == "ended":
                        manager.set_channel_state(channel, "playing", False)
                    elif event_type == "stream_ended":
                        manager.set_channel_state(channel, "streaming", False)

                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            manager.disconnect(channel)
            await manager._notify_dashboard()

    # =========================================================================
    # REST API Routes
    # =========================================================================

    @app.get("/api/channels")
    async def get_channels() -> list[ChannelStatus]:
        """Get list of connected channels."""
        return harness.list_channels()

    @app.get("/api/channels/all")
    async def get_all_channels() -> list[ChannelResponse]:
        """Get all configured channels with connection status."""
        async with get_session() as session:
            result = await session.execute(select(Channel))
            channels = list(result.scalars().all())

            return [
                ChannelResponse(
                    id=channel.id,
                    name=channel.name,
                    description=channel.description,
                    default_volume=channel.default_volume,
                    default_text_style=channel.default_text_style,
                    elevenlabs_voice_id=channel.elevenlabs_voice_id,
                    mute_state=channel.mute_state,
                    color=channel.color,
                    icon=channel.icon,
                    connected=manager.is_connected(channel.name),
                    playing=manager._channel_state.get(channel.name, {}).get("playing", False),
                    streaming=manager._channel_state.get(channel.name, {}).get("streaming", False),
                    created_at=channel.created_at,
                )
                for channel in channels
            ]

    @app.post("/api/channels", status_code=201)
    async def create_channel(request: ChannelCreate) -> Channel:
        """Create a new channel."""
        async with get_session() as session:
            # Check if channel already exists
            result = await session.execute(select(Channel).where(Channel.name == request.name))
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Channel already exists")

            channel = Channel(**request.model_dump())
            session.add(channel)
            await session.commit()
            await session.refresh(channel)
            await manager._notify_dashboard()
            return channel

    @app.get("/api/channels/{name}")
    async def get_channel(name: str) -> ChannelResponse:
        """Get a specific channel by name."""
        async with get_session() as session:
            result = await session.execute(select(Channel).where(Channel.name == name))
            channel = result.scalar_one_or_none()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            return ChannelResponse(
                id=channel.id,
                name=channel.name,
                description=channel.description,
                default_volume=channel.default_volume,
                default_text_style=channel.default_text_style,
                elevenlabs_voice_id=channel.elevenlabs_voice_id,
                mute_state=channel.mute_state,
                color=channel.color,
                icon=channel.icon,
                connected=manager.is_connected(name),
                playing=manager._channel_state.get(name, {}).get("playing", False),
                streaming=manager._channel_state.get(name, {}).get("streaming", False),
                created_at=channel.created_at,
            )

    @app.put("/api/channels/{name}")
    async def update_channel(name: str, request: ChannelUpdate) -> Channel:
        """Update a channel configuration."""
        async with get_session() as session:
            result = await session.execute(select(Channel).where(Channel.name == name))
            channel = result.scalar_one_or_none()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")

            update_data = request.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(channel, key, value)
            channel.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(channel)
            await manager._notify_dashboard()
            return channel

    @app.delete("/api/channels/{name}")
    async def delete_channel(name: str) -> dict:
        """Delete a channel. Disconnects any active connection."""
        async with get_session() as session:
            result = await session.execute(select(Channel).where(Channel.name == name))
            channel = result.scalar_one_or_none()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")

            # Disconnect if connected
            if manager.is_connected(name):
                manager.disconnect(name)

            await session.delete(channel)
            await session.commit()
            await manager._notify_dashboard()
            return {"success": True, "deleted": name}

    @app.post("/api/channel/{name}/play")
    async def api_play(name: str, request: PlayRequest) -> dict:
        """Play audio on a channel."""
        success = await harness.play(name, request.file, request.volume, request.loop)
        return {"success": success, "channel": name}

    @app.post("/api/channel/{name}/stop")
    async def api_stop(name: str) -> dict:
        """Stop audio on a channel."""
        success = await harness.stop(name)
        return {"success": success, "channel": name}

    @app.post("/api/channel/{name}/volume")
    async def api_volume(name: str, request: VolumeRequest) -> dict:
        """Set volume on a channel."""
        success = await harness.set_volume(name, request.level)
        return {"success": success, "channel": name}

    @app.post("/api/channel/{name}/stream/start")
    async def api_stream_start(name: str, request: StreamStartRequest) -> dict:
        """Start audio stream on a channel."""
        success = await harness.stream_start(name, request.sample_rate, request.channels)
        return {"success": success, "channel": name}

    @app.post("/api/channel/{name}/stream/end")
    async def api_stream_end(name: str) -> dict:
        """End audio stream on a channel."""
        success = await harness.stream_end(name)
        return {"success": success, "channel": name}

    @app.post("/api/channel/{name}/text")
    async def api_text(name: str, request: TextRequest) -> dict:
        """Display animated text on a channel."""
        success = await harness.show_text(
            name,
            request.text,
            request.style,
            request.duration,
            request.position_x,
            request.position_y,
            request.font_family or "Arial",
            request.font_size or 48,
            request.color or "#ffffff",
            request.stroke_color,
            request.stroke_width or 0,
        )
        return {"success": success, "channel": name}

    @app.post("/api/channel/{name}/text/clear")
    async def api_clear_text(name: str) -> dict:
        """Clear text overlay on a channel."""
        success = await harness.clear_text(name)
        return {"success": success, "channel": name}

    @app.post("/api/channel/{name}/tts")
    async def api_tts(name: str, request: TTSRequest) -> dict:
        """Generate TTS and stream to channel."""
        # Verify channel exists and has voice configured
        async with get_session() as session:
            result = await session.execute(select(Channel).where(Channel.name == name))
            channel = result.scalar_one_or_none()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            if not channel.elevenlabs_voice_id:
                raise HTTPException(
                    status_code=400, detail="Channel has no ElevenLabs voice configured"
                )

        # Check if ElevenLabs API key is configured
        if not os.environ.get("ELEVENLABS_API_KEY"):
            raise HTTPException(
                status_code=500, detail="ELEVENLABS_API_KEY environment variable not set"
            )

        # Calculate estimated duration for text animation
        duration = request.text_duration or estimate_tts_duration_ms(request.text)
        style = request.text_style or channel.default_text_style

        try:
            # Start audio stream
            await harness.stream_start(name, sample_rate=24000, channels=1)

            # Stream TTS audio from ElevenLabs
            # Text animation starts when first audio byte arrives for better sync
            text_shown = False
            async with ElevenLabsClient() as client:
                async for chunk in client.stream_tts(channel.elevenlabs_voice_id, request.text):
                    # Show text on first audio chunk (syncs text with audio start)
                    if not text_shown and request.show_text:
                        await harness.show_text(name, request.text, style, duration)
                        text_shown = True
                    await harness.stream_audio(name, chunk)

            # End stream
            await harness.stream_end(name)

            return {"success": True, "channel": name, "duration_ms": duration}

        except ElevenLabsError as e:
            await harness.stream_end(name)
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            await harness.stream_end(name)
            raise HTTPException(status_code=500, detail=f"TTS error: {e}")

    @app.get("/api/presets")
    async def get_presets() -> list[TextPreset]:
        """Get all text presets."""
        async with get_session() as session:
            result = await session.execute(select(TextPreset))
            return list(result.scalars().all())

    @app.post("/api/presets")
    async def create_preset(request: PresetCreate) -> TextPreset:
        """Create a new text preset."""
        async with get_session() as session:
            preset = TextPreset(**request.model_dump())
            session.add(preset)
            await session.commit()
            await session.refresh(preset)
            return preset

    @app.delete("/api/presets/{preset_id}")
    async def delete_preset(preset_id: int) -> dict:
        """Delete a text preset."""
        async with get_session() as session:
            result = await session.execute(select(TextPreset).where(TextPreset.id == preset_id))
            preset = result.scalar_one_or_none()
            if preset:
                await session.delete(preset)
                return {"success": True, "deleted": preset_id}
            return {"success": False, "error": "Preset not found"}

    @app.get("/api/history")
    async def get_history(limit: int = 50) -> list[PlaybackLog]:
        """Get recent playback history."""
        async with get_session() as session:
            result = await session.execute(
                select(PlaybackLog).order_by(PlaybackLog.timestamp.desc()).limit(limit)
            )
            return list(result.scalars().all())

    return app
