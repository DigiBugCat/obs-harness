"""FastAPI application factory, routes, and OBSHarness class."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Union

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from .chat_pipeline import ChatPipeline, ChatPipelineConfig
from .database import close_db, get_session, init_db
from .elevenlabs import ElevenLabsClient, ElevenLabsError
from .elevenlabs_ws import ElevenLabsWSError
from .tts_pipeline import TTSStreamer, TTSStreamConfig, TextDisplayConfig
from .openrouter import OpenRouterClient
from .models import (
    Character,
    CharacterCreate,
    CharacterResponse,
    CharacterStatus,
    CharacterUpdate,
    ChatRequest,
    ChatResponse,
    ClearTextCommand,
    ConversationMessage,
    PlaybackLog,
    PlayCommand,
    PresetCreate,
    SpeakRequest,
    StopCommand,
    StopStreamCommand,
    StreamEndCommand,
    StreamStartCommand,
    TextChunkCommand,
    TextCommand,
    TextPreset,
    TextStreamEndCommand,
    TextStreamStartCommand,
    TwitchChannelRequest,
    TwitchConfig,
    TwitchStatusResponse,
    TwitchTokenRequest,
    VolumeCommand,
    WordTimingCommand,
)
from .twitch_chat import TwitchChatManager


class ConnectionManager:
    """Manages WebSocket connections for all channels."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}  # Multiple connections per channel
        self._channel_state: dict[str, dict[str, Any]] = {}
        self._dashboard_connections: list[WebSocket] = []

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        """Register a channel connection (supports multiple per channel)."""
        await websocket.accept()
        if channel not in self._connections:
            self._connections[channel] = []
            self._channel_state[channel] = {"playing": False, "streaming": False}
        self._connections[channel].append(websocket)
        await self._notify_dashboard()

    def disconnect(self, channel: str, websocket: WebSocket | None = None) -> None:
        """Remove a channel connection. If websocket specified, only remove that one."""
        if channel not in self._connections:
            return
        if websocket is not None:
            # Remove specific websocket
            if websocket in self._connections[channel]:
                self._connections[channel].remove(websocket)
            # Clean up if no more connections
            if not self._connections[channel]:
                del self._connections[channel]
                self._channel_state.pop(channel, None)
        else:
            # Remove all connections for channel
            del self._connections[channel]
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
    twitch_manager = TwitchChatManager()

    # In-memory conversation history per character (for non-persistent memory)
    conversation_memory: dict[str, list[dict]] = {}

    # Track pending interrupted messages that need actual spoken text from browser
    # Maps character name -> (msg_idx, persist_memory, db_msg_id)
    pending_interrupted: dict[str, tuple[int, bool, int | None]] = {}

    # Generation tracking - only one generation per character at a time
    active_generations: dict[str, Union[ChatPipeline, TTSStreamer]] = {}
    generation_locks: dict[str, asyncio.Lock] = {}

    # =========================================================================
    # Conversation Memory Helpers
    # =========================================================================

    async def get_conversation_messages(character_name: str, persist: bool) -> list[dict]:
        """Get conversation messages for a character."""
        if persist:
            async with get_session() as session:
                result = await session.execute(
                    select(ConversationMessage)
                    .where(ConversationMessage.character_name == character_name)
                    .order_by(ConversationMessage.created_at)
                )
                messages = list(result.scalars().all())
                return [
                    {
                        "role": m.role,
                        "content": m.content,
                        "interrupted": m.interrupted,
                        "generated_text": m.generated_text,
                    }
                    for m in messages
                ]
        else:
            return conversation_memory.get(character_name, [])

    async def save_conversation_message(
        character_name: str,
        role: str,
        content: str,
        persist: bool,
        interrupted: bool = False,
        generated_text: str | None = None,
    ) -> tuple[int, int | None]:
        """Save a conversation message. Returns (in-memory index, db_id or None)."""
        msg = {
            "role": role,
            "content": content,
            "interrupted": interrupted,
            "generated_text": generated_text,
        }

        if persist:
            async with get_session() as session:
                db_msg = ConversationMessage(
                    character_name=character_name,
                    role=role,
                    content=content,
                    interrupted=interrupted,
                    generated_text=generated_text,
                )
                session.add(db_msg)
                await session.commit()
                await session.refresh(db_msg)
                # Also keep in memory for current session
                if character_name not in conversation_memory:
                    conversation_memory[character_name] = []
                conversation_memory[character_name].append(msg)
                return len(conversation_memory[character_name]) - 1, db_msg.id
        else:
            if character_name not in conversation_memory:
                conversation_memory[character_name] = []
            conversation_memory[character_name].append(msg)
            return len(conversation_memory[character_name]) - 1, None

    async def update_interrupted_message(
        character_name: str,
        msg_idx: int,
        actual_content: str,
        persist: bool,
        db_msg_id: int | None,
    ) -> None:
        """Update an interrupted message with the actual spoken content."""
        # Update in-memory
        if character_name in conversation_memory and msg_idx < len(conversation_memory[character_name]):
            conversation_memory[character_name][msg_idx]["content"] = actual_content

        # Update in database if persisted
        if persist and db_msg_id is not None:
            async with get_session() as session:
                result = await session.execute(
                    select(ConversationMessage).where(ConversationMessage.id == db_msg_id)
                )
                db_msg = result.scalar_one_or_none()
                if db_msg:
                    db_msg.content = actual_content
                    await session.commit()

    async def clear_conversation_messages(character_name: str, persist: bool) -> None:
        """Clear all conversation messages for a character."""
        # Clear in-memory
        if character_name in conversation_memory:
            del conversation_memory[character_name]

        # Clear from database if persisted
        if persist:
            async with get_session() as session:
                result = await session.execute(
                    select(ConversationMessage).where(
                        ConversationMessage.character_name == character_name
                    )
                )
                messages = list(result.scalars().all())
                for msg in messages:
                    await session.delete(msg)
                await session.commit()

    async def load_persisted_memory_on_startup() -> None:
        """Load persisted memory into in-memory cache on startup."""
        async with get_session() as session:
            # Get all characters with persist_memory enabled
            result = await session.execute(
                select(Character).where(Character.persist_memory == True)
            )
            characters = list(result.scalars().all())

            for char in characters:
                # Load their messages into memory
                msg_result = await session.execute(
                    select(ConversationMessage)
                    .where(ConversationMessage.character_name == char.name)
                    .order_by(ConversationMessage.created_at)
                )
                messages = list(msg_result.scalars().all())
                if messages:
                    conversation_memory[char.name] = [
                        {
                            "role": m.role,
                            "content": m.content,
                            "interrupted": m.interrupted,
                            "generated_text": m.generated_text,
                        }
                        for m in messages
                    ]
                    print(f"Loaded {len(messages)} persisted messages for {char.name}")

    def get_generation_lock(name: str) -> asyncio.Lock:
        """Get or create a lock for a character's generation."""
        if name not in generation_locks:
            generation_locks[name] = asyncio.Lock()
        return generation_locks[name]

    async def cancel_active_generation(name: str) -> str | None:
        """Cancel any active generation for a character and return partial spoken text."""
        gen = active_generations.pop(name, None)
        if gen is None:
            return None
        await gen.cancel()  # Now async - closes WebSocket immediately
        spoken_text = gen.get_spoken_text()
        return spoken_text

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await init_db(db_url)

        # Load saved Twitch config and auto-connect if available
        try:
            async with get_session() as session:
                result = await session.execute(select(TwitchConfig).limit(1))
                twitch_config = result.scalar_one_or_none()
                if twitch_config:
                    await twitch_manager.start(
                        access_token=twitch_config.access_token,
                        channel=twitch_config.channel,
                    )
                    print(f"Twitch chat auto-connected to #{twitch_config.channel}")
        except Exception as e:
            print(f"Failed to auto-connect Twitch chat: {e}")

        # Load persisted conversation memory
        try:
            await load_persisted_memory_on_startup()
        except Exception as e:
            print(f"Failed to load persisted memory: {e}")

        yield

        await twitch_manager.stop()
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
    app.state.twitch = twitch_manager

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

    @app.get("/twitch", response_class=HTMLResponse)
    async def twitch_page():
        """Serve the Twitch OAuth sign-in page."""
        twitch_path = static_dir / "twitch.html"
        if twitch_path.exists():
            return FileResponse(twitch_path)
        return HTMLResponse("<html><body><h1>Twitch</h1><p>Twitch page not found.</p></body></html>")

    @app.get("/auth/callback", response_class=HTMLResponse)
    async def auth_callback():
        """Handle OAuth callback - serves twitch.html which processes the token."""
        twitch_path = static_dir / "twitch.html"
        if twitch_path.exists():
            return FileResponse(twitch_path)
        return HTMLResponse("<html><body><h1>Auth Error</h1><p>Callback page not found.</p></body></html>")

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

        # Register connection with manager (websocket already accepted above)
        if character not in manager._connections:
            manager._connections[character] = []
            manager._channel_state[character] = {"playing": False, "streaming": False}
        manager._connections[character].append(websocket)
        await manager._notify_dashboard()

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    event = json.loads(data)
                    event_type = event.get("event")

                    if event_type == "ended":
                        await manager.set_channel_state(character, "playing", False)
                    elif event_type == "stream_ended":
                        await manager.set_channel_state(character, "streaming", False)
                    elif event_type == "stream_stopped":
                        # Browser reports actual playback position when forcefully stopped
                        await manager.set_channel_state(character, "streaming", False)
                        actual_text = event.get("spoken_text", "")
                        playback_time = event.get("playback_time", 0)
                        word_count = event.get("word_count", 0)
                        print(f"[{character}] Stream stopped at {playback_time:.2f}s - {word_count} words actually played: \"{actual_text[:100]}...\"")

                        # Update interrupted message with actual spoken text
                        if character in pending_interrupted:
                            msg_idx, persist, db_id = pending_interrupted[character]
                            await update_interrupted_message(
                                character, msg_idx, actual_text, persist, db_id
                            )
                            print(f"[{character}] Updated memory[{msg_idx}] with actual spoken text (persist={persist})")
                            del pending_interrupted[character]

                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            manager.disconnect(character, websocket)
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
    # Twitch API Routes
    # =========================================================================

    @app.get("/api/twitch/status")
    async def twitch_status() -> TwitchStatusResponse:
        """Get Twitch chat connection status."""
        return TwitchStatusResponse(
            connected=twitch_manager.is_connected,
            channel=twitch_manager.current_channel,
        )

    @app.post("/api/twitch/token")
    async def twitch_save_token(request: TwitchTokenRequest) -> dict:
        """Save Twitch OAuth token and connect to chat.

        Called by frontend after OAuth implicit grant flow completes.
        """
        # Save or update token in database
        async with get_session() as session:
            result = await session.execute(select(TwitchConfig).limit(1))
            twitch_config = result.scalar_one_or_none()

            if twitch_config:
                # Update existing config
                twitch_config.access_token = request.access_token
                twitch_config.channel = request.channel
                twitch_config.updated_at = datetime.utcnow()
            else:
                # Create new config
                twitch_config = TwitchConfig(
                    access_token=request.access_token,
                    channel=request.channel,
                )
                session.add(twitch_config)

            await session.commit()

        # Start Twitch chat connection
        await twitch_manager.start(
            access_token=request.access_token,
            channel=request.channel,
        )

        return {"success": True, "channel": request.channel}

    @app.post("/api/twitch/channel")
    async def twitch_set_channel(request: TwitchChannelRequest) -> dict:
        """Change the Twitch channel to listen to."""
        if not twitch_manager.is_connected:
            raise HTTPException(status_code=400, detail="Not connected to Twitch")

        # Update channel in database
        async with get_session() as session:
            result = await session.execute(select(TwitchConfig).limit(1))
            twitch_config = result.scalar_one_or_none()

            if twitch_config:
                # Leave old channel
                if twitch_config.channel != request.channel:
                    await twitch_manager.leave_channel(twitch_config.channel)

                twitch_config.channel = request.channel
                twitch_config.updated_at = datetime.utcnow()
                await session.commit()

        # Join new channel
        await twitch_manager.join_channel(request.channel)

        return {"success": True, "channel": request.channel}

    @app.post("/api/twitch/disconnect")
    async def twitch_disconnect() -> dict:
        """Disconnect from Twitch chat."""
        await twitch_manager.stop()
        return {"success": True}

    @app.get("/api/twitch/chat")
    async def get_twitch_chat(seconds: int = 60) -> dict:
        """Get recent chat messages (for debugging/preview)."""
        if not twitch_manager.current_channel:
            return {"messages": [], "channel": None}

        context = await twitch_manager.get_chat_context(seconds=seconds)
        return {
            "channel": twitch_manager.current_channel,
            "context": context,
        }

    # =========================================================================
    # OpenRouter API Routes
    # =========================================================================

    @app.get("/api/openrouter/models/{model:path}/providers")
    async def get_model_providers(model: str) -> dict:
        """Get available providers for an OpenRouter model.

        Args:
            model: Model identifier (e.g., "anthropic/claude-sonnet-4.5")

        Returns:
            List of provider names that can serve this model.
        """
        if not os.environ.get("OPENROUTER_API_KEY"):
            return {"providers": []}

        async with OpenRouterClient() as client:
            providers = await client.get_model_providers(model)
            return {"providers": providers}

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
            elevenlabs_model_id=c.elevenlabs_model_id,
            voice_stability=c.voice_stability,
            voice_similarity_boost=c.voice_similarity_boost,
            voice_style=c.voice_style,
            voice_speed=c.voice_speed,
            system_prompt=c.system_prompt,
            model=c.model,
            provider=c.provider,
            temperature=c.temperature,
            max_tokens=c.max_tokens,
            twitch_chat_enabled=c.twitch_chat_enabled,
            twitch_chat_window_seconds=c.twitch_chat_window_seconds,
            twitch_chat_max_messages=c.twitch_chat_max_messages,
            memory_enabled=c.memory_enabled,
            persist_memory=c.persist_memory,
            connected=manager.is_connected(c.name),
            playing=manager._channel_state.get(c.name, {}).get("playing", False),
            streaming=manager._channel_state.get(c.name, {}).get("streaming", False),
            created_at=c.created_at,
        )

    # -------------------------------------------------------------------------
    # ElevenLabs API endpoints
    # -------------------------------------------------------------------------

    @app.get("/api/elevenlabs/models")
    async def list_elevenlabs_models() -> list[dict]:
        """Get list of available ElevenLabs TTS models.

        Returns models that support text-to-speech with their capabilities.
        """
        try:
            async with ElevenLabsClient() as client:
                models = await client.get_models()
                # Filter to only TTS-capable models and return relevant info
                tts_models = []
                for m in models:
                    if m.get("can_do_text_to_speech"):
                        tts_models.append({
                            "model_id": m.get("model_id"),
                            "name": m.get("name"),
                            "description": m.get("description"),
                            "languages": [
                                lang.get("language_id")
                                for lang in m.get("languages", [])
                            ],
                            "can_be_finetuned": m.get("can_be_finetuned", False),
                            "can_use_style": m.get("can_use_style", False),
                            "can_use_speaker_boost": m.get("can_use_speaker_boost", False),
                            "serves_pro_voices": m.get("serves_pro_voices", False),
                            "max_characters_request_free_user": m.get("max_characters_request_free_user"),
                            "max_characters_request_subscribed_user": m.get("max_characters_request_subscribed_user"),
                        })
                return tts_models
        except ElevenLabsError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/elevenlabs/voices")
    async def list_elevenlabs_voices() -> list[dict]:
        """Get list of available ElevenLabs voices."""
        try:
            async with ElevenLabsClient() as client:
                voices = await client.get_voices()
                # Return simplified voice info
                return [
                    {
                        "voice_id": v.get("voice_id"),
                        "name": v.get("name"),
                        "category": v.get("category"),
                        "description": v.get("description"),
                        "labels": v.get("labels", {}),
                        "preview_url": v.get("preview_url"),
                        "high_quality_base_model_ids": v.get("high_quality_base_model_ids", []),
                    }
                    for v in voices
                ]
        except ElevenLabsError as e:
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/elevenlabs/voices/{voice_id}")
    async def get_elevenlabs_voice(voice_id: str) -> dict:
        """Get details for a specific ElevenLabs voice including compatible models."""
        try:
            async with ElevenLabsClient() as client:
                voice = await client.get_voice(voice_id)
                return {
                    "voice_id": voice.get("voice_id"),
                    "name": voice.get("name"),
                    "category": voice.get("category"),
                    "description": voice.get("description"),
                    "labels": voice.get("labels", {}),
                    "preview_url": voice.get("preview_url"),
                    "high_quality_base_model_ids": voice.get("high_quality_base_model_ids", []),
                    "settings": voice.get("settings", {}),
                }
        except ElevenLabsError as e:
            raise HTTPException(status_code=502, detail=str(e))

    # -------------------------------------------------------------------------
    # Character CRUD and interaction endpoints
    # -------------------------------------------------------------------------

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

        # Create TTS and text display configs
        tts_config = TTSStreamConfig(
            voice_id=character.elevenlabs_voice_id,
            model_id=character.elevenlabs_model_id,
            stability=character.voice_stability,
            similarity_boost=character.voice_similarity_boost,
            style=character.voice_style,
            speed=character.voice_speed,
        )
        text_config = TextDisplayConfig(
            font_family=character.text_font_family,
            font_size=character.text_font_size,
            color=character.text_color,
            stroke_color=character.text_stroke_color,
            stroke_width=character.text_stroke_width,
            position_x=character.text_position_x,
            position_y=character.text_position_y,
        )

        # Create unified TTS streamer with browser callbacks
        streamer = TTSStreamer(
            tts_config=tts_config,
            text_config=text_config,
            show_text=request.show_text,
            send_text_start=lambda: harness.text_stream_start(
                name,
                font_family=text_config.font_family,
                font_size=text_config.font_size,
                color=text_config.color,
                stroke_color=text_config.stroke_color,
                stroke_width=text_config.stroke_width,
                position_x=text_config.position_x,
                position_y=text_config.position_y,
            ),
            send_text_end=lambda: harness.text_stream_end(name),
            send_audio_start=lambda: harness.stream_start(name, sample_rate=24000, channels=1),
            send_audio_chunk=lambda audio: harness.stream_audio(name, audio),
            send_audio_end=lambda: harness.stream_end(name),
            send_word_timing=lambda words: harness.word_timing(name, words),
        )

        try:
            # Acquire lock and cancel any existing generation
            async with get_generation_lock(name):
                if name in active_generations:
                    await cancel_active_generation(name)
                    await harness.stop_stream(name)
                active_generations[name] = streamer

            await streamer.stream(request.text)

            # Log the speak
            await harness._log_playback(name, request.text, "stream")

            return {"success": True, "character": name}

        except ElevenLabsWSError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"TTS error: {e}")
        finally:
            # Clear active generation (use get to avoid race with stop endpoint)
            if active_generations.get(name) is streamer:
                active_generations.pop(name, None)

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

        # Determine twitch chat seconds (request override or character default)
        # request.twitch_chat_seconds == 0 means disabled for this request
        # request.twitch_chat_seconds == None means use character default
        twitch_seconds = request.twitch_chat_seconds
        if twitch_seconds is None:
            twitch_seconds = character.twitch_chat_window_seconds if character.twitch_chat_enabled else 0

        # Get Twitch chat context if enabled
        twitch_chat_context = None
        if twitch_seconds > 0 and twitch_manager.is_connected:
            twitch_chat_context = await twitch_manager.get_chat_context(
                seconds=twitch_seconds,
                max_messages=character.twitch_chat_max_messages,
            )

        # Get conversation history if memory is enabled (filter out context messages for LLM)
        history = None
        if character.memory_enabled:
            all_history = conversation_memory.get(name, [])
            # Only include user/assistant messages for LLM context
            history = [m for m in all_history if m.get("role") in ("user", "assistant")]

        # Create TTS and text display configs
        tts_config = TTSStreamConfig(
            voice_id=character.elevenlabs_voice_id,
            model_id=character.elevenlabs_model_id,
            stability=character.voice_stability,
            similarity_boost=character.voice_similarity_boost,
            style=character.voice_style,
            speed=character.voice_speed,
        )
        text_config = TextDisplayConfig(
            font_family=character.text_font_family,
            font_size=character.text_font_size,
            color=character.text_color,
            stroke_color=character.text_stroke_color,
            stroke_width=character.text_stroke_width,
            position_x=character.text_position_x,
            position_y=character.text_position_y,
        )

        # Create unified TTS streamer with browser callbacks
        tts_streamer = TTSStreamer(
            tts_config=tts_config,
            text_config=text_config,
            show_text=request.show_text,
            send_text_start=lambda: harness.text_stream_start(
                name,
                font_family=text_config.font_family,
                font_size=text_config.font_size,
                color=text_config.color,
                stroke_color=text_config.stroke_color,
                stroke_width=text_config.stroke_width,
                position_x=text_config.position_x,
                position_y=text_config.position_y,
            ),
            send_text_end=lambda: harness.text_stream_end(name),
            send_audio_start=lambda: harness.stream_start(name, sample_rate=24000, channels=1),
            send_audio_chunk=lambda audio: harness.stream_audio(name, audio),
            send_audio_end=lambda: harness.stream_end(name),
            send_word_timing=lambda words: harness.word_timing(name, words),
        )

        # Create LLM pipeline configuration
        pipeline_config = ChatPipelineConfig(
            system_prompt=character.system_prompt,
            model=character.model,
            provider=character.provider,
            temperature=character.temperature,
            max_tokens=character.max_tokens,
            twitch_chat_context=twitch_chat_context,
            conversation_history=history,
        )

        # Create and run pipeline
        pipeline = ChatPipeline(
            config=pipeline_config,
            tts_streamer=tts_streamer,
        )

        # Track if we saved partial memory from an interrupted generation
        interrupted_prev = False

        try:
            # Acquire lock and cancel any existing generation
            async with get_generation_lock(name):
                if name in active_generations:
                    # Cancel the previous generation - it will save its own interrupted state
                    await cancel_active_generation(name)
                    await harness.stop_stream(name)
                    interrupted_prev = True
                active_generations[name] = pipeline

            response_text = await pipeline.run(request.message)

            # Store conversation in memory
            # Store twitch context if present
            if twitch_chat_context:
                await save_conversation_message(
                    name, "context", twitch_chat_context, character.persist_memory
                )
            await save_conversation_message(
                name, "user", request.message, character.persist_memory
            )

            # Check if we were cancelled (interrupted by stop button or new chat)
            if pipeline._cancelled:
                # Save as interrupted - browser will update with actual spoken text
                spoken_text = pipeline.get_spoken_text()
                if spoken_text:
                    msg_idx, db_id = await save_conversation_message(
                        character_name=name,
                        role="assistant",
                        content=spoken_text,
                        persist=character.persist_memory,
                        interrupted=True,
                        generated_text=spoken_text,
                    )
                    # Track for browser update
                    pending_interrupted[name] = (msg_idx, character.persist_memory, db_id)
            else:
                # Normal completion - save full response
                await save_conversation_message(
                    name, "assistant", response_text, character.persist_memory
                )
                # Log the chat
                await harness._log_playback(name, f"chat:{name}", "stream")

            return ChatResponse(
                success=True,
                character=name,
                response_text=response_text,
                twitch_chat_context=twitch_chat_context,
            )

        except Exception as e:
            # Ensure streams are cleaned up on error
            await harness.stream_end(name)
            await harness.text_stream_end(name)
            raise HTTPException(status_code=500, detail=f"Chat error: {e}")
        finally:
            # Clear active generation (use get to avoid race with stop endpoint)
            if active_generations.get(name) is pipeline:
                active_generations.pop(name, None)

    @app.post("/api/characters/{name}/stop")
    async def stop_character_generation(name: str) -> dict:
        """Stop any active generation (speak/chat) for a character.

        Note: The interrupted message is saved by the original chat endpoint
        when it detects it was cancelled, not here.
        """
        was_active = False
        spoken_text = None

        async with get_generation_lock(name):
            if name in active_generations:
                was_active = True
                # Cancel the generation (sets _cancelled=True)
                spoken_text = await cancel_active_generation(name)

        # Always send stop command to browser - audio may still be playing
        # even if generation has already completed
        await harness.stop_stream(name)

        return {
            "success": True,
            "character": name,
            "was_active": was_active,
            "spoken_text": spoken_text,
        }

    @app.delete("/api/characters/{name}/memory")
    async def clear_character_memory(name: str) -> dict:
        """Clear conversation memory for a character."""
        # Look up character to get persist_memory setting
        async with get_session() as session:
            result = await session.execute(
                select(Character).where(Character.name == name)
            )
            character = result.scalar_one_or_none()
            persist = character.persist_memory if character else False

        await clear_conversation_messages(name, persist)
        return {"success": True, "character": name, "message": "Memory cleared"}

    @app.get("/api/characters/{name}/memory")
    async def get_character_memory(name: str) -> dict:
        """Get conversation memory for a character."""
        # Look up character to get persist_memory setting
        async with get_session() as session:
            result = await session.execute(
                select(Character).where(Character.name == name)
            )
            character = result.scalar_one_or_none()
            persist = character.persist_memory if character else False

        history = await get_conversation_messages(name, persist)
        return {"character": name, "message_count": len(history), "messages": history}

    return app
