"""FastAPI application factory, routes, and OBSHarness class."""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from .chat_pipeline import ChatPipeline, ChatPipelineConfig
from .database import close_db, get_session, init_db
from .elevenlabs import ElevenLabsClient, ElevenLabsError, estimate_tts_duration_ms
from .models import (
    Character,
    CharacterCreate,
    CharacterResponse,
    CharacterStatus,
    CharacterUpdate,
    ChatRequest,
    ChatResponse,
    ClearTextCommand,
    PlaybackLog,
    PlayCommand,
    PresetCreate,
    SpeakRequest,
    StopCommand,
    StreamEndCommand,
    StreamStartCommand,
    TextChunkCommand,
    TextCommand,
    TextPreset,
    TextStreamEndCommand,
    TextStreamStartCommand,
    VolumeCommand,
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
        await websocket.send_json({"type": "characters", "characters": [ch.model_dump() for ch in self.get_characters()]})

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

    def get_characters(self) -> list[CharacterStatus]:
        """Get list of connected characters with status."""
        return [
            CharacterStatus(
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
        message = {"type": "characters", "characters": [c.model_dump() for c in self.get_characters()]}
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

    def list_characters(self) -> list[CharacterStatus]:
        """Get list of connected characters."""
        return self._manager.get_characters()

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

    @app.websocket("/ws/{character}")
    async def character_websocket(websocket: WebSocket, character: str):
        """WebSocket endpoint for a browser source character."""
        # Accept connection first (required for proper close codes)
        await websocket.accept()

        # Validate character exists
        try:
            async with get_session() as session:
                result = await session.execute(select(Character).where(Character.name == character))
                db_character = result.scalar_one_or_none()

                if not db_character:
                    await websocket.close(code=4004, reason="Character not found. Create it first.")
                    return
        except Exception:
            await websocket.close(code=4000, reason="Database error")
            return

        # Register connection with manager (don't call accept again)
        manager._connections[character] = websocket
        manager._channel_state[character] = {"playing": False, "streaming": False}
        await manager._notify_dashboard()

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    event = json.loads(data)
                    event_type = event.get("event")

                    if event_type == "ended":
                        manager.set_channel_state(character, "playing", False)
                    elif event_type == "stream_ended":
                        manager.set_channel_state(character, "streaming", False)

                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            manager.disconnect(character)
            await manager._notify_dashboard()

    # =========================================================================
    # REST API Routes - Presets & History
    # =========================================================================

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

    # =========================================================================
    # Character API Routes
    # =========================================================================

    def _character_to_response(c: Character) -> CharacterResponse:
        """Convert a Character model to CharacterResponse with connection status."""
        return CharacterResponse(
            id=c.id,
            name=c.name,
            description=c.description,
            color=c.color,
            icon=c.icon,
            default_volume=c.default_volume,
            mute_state=c.mute_state,
            default_text_style=c.default_text_style,
            text_font_family=c.text_font_family,
            text_font_size=c.text_font_size,
            text_color=c.text_color,
            text_stroke_color=c.text_stroke_color,
            text_stroke_width=c.text_stroke_width,
            text_position_x=c.text_position_x,
            text_position_y=c.text_position_y,
            text_duration=c.text_duration,
            elevenlabs_voice_id=c.elevenlabs_voice_id,
            voice_stability=c.voice_stability,
            voice_similarity_boost=c.voice_similarity_boost,
            voice_style=c.voice_style,
            voice_speed=c.voice_speed,
            system_prompt=c.system_prompt,
            model=c.model,
            temperature=c.temperature,
            max_tokens=c.max_tokens,
            connected=manager.is_connected(c.name),
            playing=manager._channel_state.get(c.name, {}).get("playing", False),
            streaming=manager._channel_state.get(c.name, {}).get("streaming", False),
            created_at=c.created_at,
        )

    @app.post("/api/characters", status_code=201)
    async def create_character(request: CharacterCreate) -> Character:
        """Create a new character."""
        async with get_session() as session:
            # Check if character already exists
            result = await session.execute(
                select(Character).where(Character.name == request.name)
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Character already exists")

            character = Character(**request.model_dump())
            session.add(character)
            await session.commit()
            await session.refresh(character)
            await manager._notify_dashboard()
            return character

    @app.get("/api/characters")
    async def list_characters() -> list[CharacterResponse]:
        """List all characters with connection status."""
        async with get_session() as session:
            result = await session.execute(select(Character))
            characters = list(result.scalars().all())
            return [_character_to_response(c) for c in characters]

    @app.get("/api/characters/{name}")
    async def get_character(name: str) -> CharacterResponse:
        """Get a character by name."""
        async with get_session() as session:
            result = await session.execute(
                select(Character).where(Character.name == name)
            )
            character = result.scalar_one_or_none()
            if not character:
                raise HTTPException(status_code=404, detail="Character not found")

            return _character_to_response(character)

    @app.put("/api/characters/{name}")
    async def update_character(name: str, request: CharacterUpdate) -> Character:
        """Update a character."""
        async with get_session() as session:
            result = await session.execute(
                select(Character).where(Character.name == name)
            )
            character = result.scalar_one_or_none()
            if not character:
                raise HTTPException(status_code=404, detail="Character not found")

            update_data = request.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(character, key, value)
            character.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(character)
            await manager._notify_dashboard()
            return character

    @app.delete("/api/characters/{name}")
    async def delete_character(name: str) -> dict:
        """Delete a character. Disconnects any active connection."""
        async with get_session() as session:
            result = await session.execute(
                select(Character).where(Character.name == name)
            )
            character = result.scalar_one_or_none()
            if not character:
                raise HTTPException(status_code=404, detail="Character not found")

            # Disconnect if connected
            if manager.is_connected(name):
                manager.disconnect(name)

            await session.delete(character)
            await session.commit()
            await manager._notify_dashboard()
            return {"success": True, "deleted": name}

    @app.post("/api/characters/{name}/speak")
    async def character_speak(name: str, request: SpeakRequest) -> dict:
        """Speak text directly using character's voice (no AI).

        This endpoint:
        1. Looks up the character configuration
        2. Streams TTS audio to the connected browser
        """
        # Check ElevenLabs API key
        if not os.environ.get("ELEVENLABS_API_KEY"):
            raise HTTPException(
                status_code=500, detail="ELEVENLABS_API_KEY environment variable not set"
            )

        # Look up character
        async with get_session() as session:
            result = await session.execute(
                select(Character).where(Character.name == name)
            )
            character = result.scalar_one_or_none()
            if not character:
                raise HTTPException(status_code=404, detail="Character not found")

        # Verify character is connected
        if not manager.is_connected(name):
            raise HTTPException(
                status_code=400, detail=f"Character '{name}' is not connected"
            )

        # Calculate estimated duration for text animation
        duration = request.text_duration or character.text_duration or estimate_tts_duration_ms(request.text)
        style = request.text_style or character.default_text_style

        try:
            # Start audio stream
            await harness.stream_start(name, sample_rate=24000, channels=1)

            # Stream TTS audio from ElevenLabs
            text_shown = False
            async with ElevenLabsClient() as client:
                async for chunk in client.stream_tts(character.elevenlabs_voice_id, request.text):
                    # Show text on first audio chunk (syncs text with audio start)
                    if not text_shown and request.show_text:
                        await harness.show_text(
                            name,
                            request.text,
                            style=style,
                            duration=duration,
                            position_x=character.text_position_x,
                            position_y=character.text_position_y,
                            font_family=character.text_font_family,
                            font_size=character.text_font_size,
                            color=character.text_color,
                            stroke_color=character.text_stroke_color,
                            stroke_width=character.text_stroke_width,
                        )
                        text_shown = True
                    await harness.stream_audio(name, chunk)

            # End stream
            await harness.stream_end(name)

            # Log the speak
            await harness._log_playback(name, request.text, "stream")

            return {"success": True, "character": name, "duration_ms": duration}

        except ElevenLabsError as e:
            await harness.stream_end(name)
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            await harness.stream_end(name)
            raise HTTPException(status_code=500, detail=f"TTS error: {e}")

    @app.post("/api/characters/{name}/chat")
    async def character_chat(name: str, request: ChatRequest) -> ChatResponse:
        """Chat with a character - streams LLM response through TTS to browser.

        This endpoint:
        1. Looks up the character configuration
        2. Validates system_prompt is set (required for AI chat)
        3. Streams LLM response tokens through ElevenLabs TTS
        4. Sends audio and text to the browser in real-time
        """
        # Check environment variables
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise HTTPException(
                status_code=500, detail="OPENROUTER_API_KEY environment variable not set"
            )
        if not os.environ.get("ELEVENLABS_API_KEY"):
            raise HTTPException(
                status_code=500, detail="ELEVENLABS_API_KEY environment variable not set"
            )

        # Look up character
        async with get_session() as session:
            result = await session.execute(
                select(Character).where(Character.name == name)
            )
            character = result.scalar_one_or_none()
            if not character:
                raise HTTPException(status_code=404, detail="Character not found")

        # Validate system_prompt is set (required for AI chat)
        if not character.system_prompt:
            raise HTTPException(
                status_code=400,
                detail="Character has no system_prompt configured. Use /speak endpoint for direct TTS.",
            )

        # Verify character is connected
        if not manager.is_connected(name):
            raise HTTPException(
                status_code=400, detail=f"Character '{name}' is not connected"
            )

        # Create pipeline configuration
        config = ChatPipelineConfig(
            character_name=character.name,
            system_prompt=character.system_prompt,
            voice_id=character.elevenlabs_voice_id,
            channel=name,  # Character name is used as channel
            model=character.model,
            temperature=character.temperature,
            max_tokens=character.max_tokens,
            voice_stability=character.voice_stability,
            voice_similarity_boost=character.voice_similarity_boost,
            voice_style=character.voice_style,
            voice_speed=character.voice_speed,
            show_text=request.show_text,
        )

        # Create callbacks that use the harness methods
        async def send_text_start() -> bool:
            return await harness.text_stream_start(
                name,
                font_family=character.text_font_family,
                font_size=character.text_font_size,
                color=character.text_color,
                stroke_color=character.text_stroke_color,
                stroke_width=character.text_stroke_width,
                position_x=character.text_position_x,
                position_y=character.text_position_y,
            )

        async def send_text_chunk(text: str) -> bool:
            return await harness.text_chunk(name, text)

        async def send_text_end() -> bool:
            return await harness.text_stream_end(name)

        async def send_audio_start() -> bool:
            return await harness.stream_start(name, sample_rate=24000, channels=1)

        async def send_audio_chunk(audio_bytes: bytes) -> bool:
            return await harness.stream_audio(name, audio_bytes)

        async def send_audio_end() -> bool:
            return await harness.stream_end(name)

        # Create and run pipeline
        pipeline = ChatPipeline(
            config=config,
            send_text_start=send_text_start,
            send_text_chunk=send_text_chunk,
            send_text_end=send_text_end,
            send_audio_start=send_audio_start,
            send_audio_chunk=send_audio_chunk,
            send_audio_end=send_audio_end,
        )

        try:
            response_text = await pipeline.run(request.message)

            # Log the chat
            await harness._log_playback(name, f"chat:{name}", "stream")

            return ChatResponse(
                success=True,
                character=name,
                response_text=response_text,
            )

        except Exception as e:
            # Ensure streams are cleaned up on error
            await harness.stream_end(name)
            await harness.text_stream_end(name)
            raise HTTPException(status_code=500, detail=f"Chat error: {e}")

    return app
