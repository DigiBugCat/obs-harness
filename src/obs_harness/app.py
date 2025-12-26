"""FastAPI application factory, routes, and OBSHarness class."""

import asyncio
import json
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Union

from . import __version__

# Build ID for version checking - changes on every server restart
BUILD_ID = str(int(time.time()))

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from .chat_pipeline import ChatPipeline, ChatPipelineConfig
from .database import close_db, get_session, init_db
from .elevenlabs import ElevenLabsClient, ElevenLabsError
from .tts import TTSProviderType, ElevenLabsWSError, CartesiaWSError, ElevenLabsSettings, CartesiaSettings
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
    SantaConfig,
    SantaConfigResponse,
    SantaConfigUpdate,
    SantaMessageRequest,
    SantaSession,
    SantaSessionStatus,
    SantaVerdictRequest,
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
    get_character_tts_config,
)
from .twitch_eventsub import TwitchEventSubManager, ChannelPointRedemption, ChatMessage
from .santa_session import SantaSessionManager, SantaState, SessionData


class ConnectionManager:
    """Manages WebSocket connections for all channels."""

    # Heartbeat constants
    PING_INTERVAL = 25  # seconds - send ping every 25s (under 30s proxy timeout)
    STALE_THRESHOLD = 60  # seconds - close connections without pong for 60s

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}  # Multiple connections per channel
        self._channel_state: dict[str, dict[str, Any]] = {}
        self._dashboard_connections: list[WebSocket] = []
        self._last_pong: dict[WebSocket, float] = {}  # Track last pong time per connection

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        """Register a channel connection (supports multiple per channel)."""
        await websocket.accept()
        if channel not in self._connections:
            self._connections[channel] = []
            self._channel_state[channel] = {"playing": False, "streaming": False}
        self._connections[channel].append(websocket)
        self._last_pong[websocket] = time.time()  # Initialize pong time
        logger.info(f"WebSocket connected: {channel} ({len(self._connections[channel])} connections)")
        await self._notify_dashboard()

    def record_pong(self, websocket: WebSocket) -> None:
        """Record that a pong was received from a connection."""
        self._last_pong[websocket] = time.time()

    def disconnect(self, channel: str, websocket: WebSocket | None = None) -> None:
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

    async def connect_dashboard(self, websocket: WebSocket) -> None:
        """Register a dashboard connection."""
        await websocket.accept()
        self._dashboard_connections.append(websocket)
        self._last_pong[websocket] = time.time()  # Initialize pong time
        # Send current state immediately
        await websocket.send_json({"type": "characters", "characters": [ch.model_dump() for ch in self.get_characters()]})

    def disconnect_dashboard(self, websocket: WebSocket) -> None:
        """Remove a dashboard connection."""
        if websocket in self._dashboard_connections:
            self._dashboard_connections.remove(websocket)
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
        """Notify all dashboard connections of state changes."""
        message = {"type": "characters", "characters": [c.model_dump() for c in self.get_characters()]}
        for ws in self._dashboard_connections[:]:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect_dashboard(ws)

    async def broadcast_character_sync(self, characters: list[dict]) -> None:
        """Broadcast full character data to all dashboard connections.

        Used when character settings are changed to sync across all clients.
        """
        message = {"type": "character_sync", "characters": characters}
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
    eventsub_manager = TwitchEventSubManager()

    # Santa session manager (initialized after harness)
    santa_manager: SantaSessionManager | None = None

    # Santa dashboard WebSocket connections
    santa_dashboard_connections: list[WebSocket] = []

    # Twitch chat WebSocket connections for real-time chat updates
    twitch_chat_connections: list[WebSocket] = []

    # In-memory conversation history per character (for non-persistent memory)
    conversation_memory: dict[str, list[dict]] = {}

    # Track pending interrupted messages that need actual spoken text from browser
    # Maps character name -> (msg_idx, persist_memory, db_msg_id)
    pending_interrupted: dict[str, tuple[int, bool, int | None]] = {}

    # Generation tracking - only one generation per character at a time
    active_generations: dict[str, Union[ChatPipeline, TTSStreamer]] = {}
    # Using defaultdict ensures thread-safe lock creation (no race on first access)
    generation_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # =========================================================================
    # Conversation Memory Helpers
    # =========================================================================

    def _parse_message_content(content: str) -> str | list:
        """Parse message content, deserializing JSON if it's multimodal."""
        if content.startswith("["):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass
        return content

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
                        "content": _parse_message_content(m.content),
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
        content: str | list,
        persist: bool,
        interrupted: bool = False,
        generated_text: str | None = None,
    ) -> tuple[int, int | None]:
        """Save a conversation message. Returns (in-memory index, db_id or None).

        Content can be a string or a list (for multimodal messages with images).
        Lists are JSON-serialized for database storage.
        """
        # For database storage, serialize list content to JSON
        db_content = json.dumps(content) if isinstance(content, list) else content

        msg = {
            "role": role,
            "content": content,  # Keep as list in memory for API format
            "interrupted": interrupted,
            "generated_text": generated_text,
        }

        if persist:
            async with get_session() as session:
                db_msg = ConversationMessage(
                    character_name=character_name,
                    role=role,
                    content=db_content,  # JSON string for lists
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
                    logger.info(f"Loaded {len(messages)} persisted messages for {char.name}")

    async def cancel_active_generation(name: str) -> str | None:
        """Cancel any active generation for a character and return partial spoken text."""
        gen = active_generations.pop(name, None)
        if gen is None:
            return None
        await gen.cancel()  # Now async - closes WebSocket immediately
        spoken_text = gen.get_spoken_text()
        return spoken_text

    # =========================================================================
    # Santa Session Helpers
    # =========================================================================

    async def broadcast_santa_status(session_data: SessionData | None = None) -> None:
        """Broadcast Santa session status to all Santa dashboard connections."""
        nonlocal santa_manager
        if santa_manager:
            status = santa_manager.get_session_status()
        else:
            status = {"active": False, "session_id": None, "state": None}

        message = {"type": "santa_status", "status": status}
        for ws in santa_dashboard_connections[:]:
            try:
                await ws.send_json(message)
            except Exception:
                santa_dashboard_connections.remove(ws)

    async def on_santa_state_change(session_data: SessionData) -> None:
        """Callback for Santa session state changes."""
        await broadcast_santa_status(session_data)

    async def handle_channel_point_redemption(redemption: ChannelPointRedemption) -> None:
        """Handle incoming channel point redemption."""
        nonlocal santa_manager

        if not santa_manager:
            logger.warning("Santa manager not initialized, ignoring redemption")
            return

        # Get Santa config
        async with get_session() as session:
            result = await session.execute(select(SantaConfig).limit(1))
            config = result.scalar_one_or_none()

        if not config or not config.enabled:
            logger.debug("Santa not enabled, ignoring redemption")
            return

        # Check if this is the configured reward
        if config.reward_id and redemption.reward_id != config.reward_id:
            logger.debug(f"Redemption for different reward ({redemption.reward_title}), ignoring")
            return

        # Check if session already active
        if santa_manager.is_active:
            logger.warning(f"Santa session already active, cannot process redemption from {redemption.user_display_name}")
            # Optionally refund the redemption
            await eventsub_manager.cancel_redemption(redemption.redemption_id, redemption.reward_id)
            return

        # Pause the reward to prevent new redeems
        await eventsub_manager.disable_reward(redemption.reward_id)

        # Get past sessions for this user (repeat visitor detection)
        past_sessions = []
        async with get_session() as session:
            result = await session.execute(
                select(SantaSession)
                .where(SantaSession.redeemer_user_id == redemption.user_id)
                .order_by(SantaSession.started_at.desc())
                .limit(5)
            )
            for ps in result.scalars().all():
                past_sessions.append({
                    "wish_text": ps.wish_text,
                    "outcome": ps.outcome,
                    "started_at": ps.started_at.isoformat() if ps.started_at else None,
                })

        # Create session record
        async with get_session() as session:
            db_session = SantaSession(
                redeemer_user_id=redemption.user_id,
                redeemer_username=redemption.user_login,
                redeemer_display_name=redemption.user_display_name,
                wish_text=redemption.user_input or "",
                state="processing",
            )
            session.add(db_session)
            await session.commit()
            await session.refresh(db_session)
            session_id = db_session.id

        logger.info(f"Starting Santa session {session_id} for {redemption.user_display_name}")

        # Start the session
        success = await santa_manager.start_session(
            session_id=session_id,
            redeemer_user_id=redemption.user_id,
            redeemer_username=redemption.user_login,
            redeemer_display_name=redemption.user_display_name,
            wish_text=redemption.user_input or "I want a surprise!",
            past_sessions=past_sessions if past_sessions else None,
        )

        if not success:
            logger.error(f"Failed to start Santa session for {redemption.user_display_name}")
            await eventsub_manager.enable_reward(redemption.reward_id)

    async def finalize_santa_session() -> None:
        """Finalize the current Santa session (save to DB, unpause reward)."""
        nonlocal santa_manager

        if not santa_manager or not santa_manager.active_session:
            return

        session_data = santa_manager.active_session

        # Update database
        async with get_session() as db_session:
            result = await db_session.execute(
                select(SantaSession).where(SantaSession.id == session_data.session_id)
            )
            db_record = result.scalar_one_or_none()
            if db_record:
                db_record.state = session_data.state.value
                db_record.outcome = session_data.outcome
                db_record.followup_count = session_data.followup_count
                db_record.conversation_history = santa_manager.get_conversation_json()
                db_record.ended_at = datetime.utcnow()
                await db_session.commit()

        # Get reward ID from config and re-enable
        async with get_session() as session:
            result = await session.execute(select(SantaConfig).limit(1))
            config = result.scalar_one_or_none()
            if config and config.reward_id and config.enabled:
                await eventsub_manager.enable_reward(config.reward_id)

        logger.info(f"Santa session {session_data.session_id} finalized: {session_data.outcome}")

    # =========================================================================
    # Twitch Chat WebSocket Helpers
    # =========================================================================

    async def on_chat_message(message: ChatMessage) -> None:
        """Callback for incoming chat messages - broadcast to all chat WebSocket clients and Santa."""
        # Broadcast to WebSocket clients
        msg_data = {
            "type": "chat_message",
            "message": {
                "user": message.user_display_name,
                "text": message.message,
                "timestamp": message.timestamp.isoformat(),
            }
        }
        for ws in twitch_chat_connections[:]:
            try:
                await ws.send_json(msg_data)
            except Exception:
                twitch_chat_connections.remove(ws)

        # Forward to Santa if there's an active session waiting for followup
        if santa_manager and santa_manager.is_active:
            await santa_manager.on_chat_message(
                user_id=message.user_id,
                username=message.user_login,
                message=message.message,
            )

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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal santa_manager

        await init_db(db_url)

        # Load saved Twitch config and auto-connect EventSub if available
        try:
            async with get_session() as session:
                result = await session.execute(select(TwitchConfig).limit(1))
                twitch_config = result.scalar_one_or_none()
                if twitch_config and twitch_config.access_token and twitch_config.user_id:
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
                                        "Client-Id": os.environ.get("TWITCH_CLIENT_ID", "h1x5odjr6qy1m8sesgev1p9wcssz63"),
                                    }
                                )
                                if resp.status_code == 200:
                                    data = resp.json()
                                    if data.get("data"):
                                        channel_user_id = data["data"][0]["id"]
                        except Exception as e:
                            logger.warning(f"Failed to look up channel user ID on startup: {e}")

                    # Set chat callback and start EventSub
                    eventsub_manager.set_chat_callback(on_chat_message)
                    await eventsub_manager.start(
                        access_token=twitch_config.access_token,
                        client_id=os.environ.get("TWITCH_CLIENT_ID", "h1x5odjr6qy1m8sesgev1p9wcssz63"),
                        broadcaster_user_id=channel_user_id,
                        user_id=twitch_config.user_id,
                        subscribe_to_chat=True,
                        subscribe_to_redemptions=False,
                    )
                    logger.info(f"EventSub auto-connected to #{twitch_config.channel}")
        except Exception as e:
            logger.warning(f"Failed to auto-connect EventSub: {e}")

        # Load persisted conversation memory
        try:
            await load_persisted_memory_on_startup()
        except Exception as e:
            logger.warning(f"Failed to load persisted memory: {e}")

        # Initialize Santa session manager
        async with get_session() as session:
            result = await session.execute(select(SantaConfig).limit(1))
            santa_config = result.scalar_one_or_none()

        if santa_config:
            santa_manager = SantaSessionManager(
                harness=harness,
                eventsub=eventsub_manager,
                character_name=santa_config.character_name,
                max_followups=santa_config.max_followups,
                response_timeout=santa_config.response_timeout_seconds,
                debounce_seconds=santa_config.debounce_seconds,
                chat_vote_seconds=santa_config.chat_vote_seconds,
            )
            santa_manager.set_state_callback(on_santa_state_change)
            logger.info(f"Santa session manager initialized (character: {santa_config.character_name})")
        else:
            # Create default config
            async with get_session() as session:
                santa_config = SantaConfig()
                session.add(santa_config)
                await session.commit()

            santa_manager = SantaSessionManager(
                harness=harness,
                eventsub=eventsub_manager,
            )
            santa_manager.set_state_callback(on_santa_state_change)
            logger.info("Santa session manager initialized with defaults")

        # Start background ping task for WebSocket heartbeat
        ping_task = asyncio.create_task(ping_all_connections())

        yield

        # Cancel ping task on shutdown
        ping_task.cancel()
        try:
            await ping_task
        except asyncio.CancelledError:
            pass

        # Stop EventSub
        await eventsub_manager.stop()
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
    app.state.eventsub = eventsub_manager
    # Note: santa_manager is accessed via closure since it's initialized in lifespan

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

    @app.get("/santa", response_class=HTMLResponse)
    async def santa_page():
        """Serve the Santa Timmy dashboard page."""
        santa_path = static_dir / "santa.html"
        if santa_path.exists():
            return FileResponse(santa_path)
        return HTMLResponse("<html><body><h1>Santa Timmy</h1><p>Santa dashboard not found.</p></body></html>")

    # =========================================================================
    # Version API
    # =========================================================================

    @app.get("/api/version")
    async def get_version():
        """Get server version and build ID for client version checking."""
        return {"version": __version__, "build_id": BUILD_ID}

    @app.get("/health")
    async def health_check():
        """Health check endpoint for load balancers and client polling."""
        return {"status": "ok", "build_id": BUILD_ID}

    # =========================================================================
    # WebSocket Routes
    # =========================================================================

    # Dashboard WebSocket must be defined BEFORE the channel wildcard route
    @app.websocket("/ws/dashboard")
    async def dashboard_websocket(websocket: WebSocket):
        """WebSocket endpoint for dashboard live updates."""
        await manager.connect_dashboard(websocket)

        # Send hello message with version info for client version checking
        await websocket.send_json({
            "type": "hello",
            "version": __version__,
            "build_id": BUILD_ID,
        })

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    event = json.loads(data)
                    if event.get("event") == "pong":
                        manager.record_pong(websocket)
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            manager.disconnect_dashboard(websocket)

    @app.websocket("/ws/santa")
    async def santa_websocket(websocket: WebSocket):
        """WebSocket endpoint for Santa dashboard live updates."""
        await websocket.accept()
        santa_dashboard_connections.append(websocket)

        # Send current status immediately
        await broadcast_santa_status()

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    event = json.loads(data)
                    if event.get("event") == "pong":
                        pass  # Could track pongs if needed
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            if websocket in santa_dashboard_connections:
                santa_dashboard_connections.remove(websocket)

    @app.websocket("/ws/twitch/chat")
    async def twitch_chat_websocket(websocket: WebSocket):
        """WebSocket endpoint for real-time Twitch chat updates via EventSub."""
        await websocket.accept()
        twitch_chat_connections.append(websocket)

        # Get channel from database for status
        channel = None
        async with get_session() as session:
            result = await session.execute(select(TwitchConfig).limit(1))
            twitch_config = result.scalar_one_or_none()
            if twitch_config:
                channel = twitch_config.channel

        # Send connection status immediately
        await websocket.send_json({
            "type": "connected",
            "eventsub_active": eventsub_manager.is_connected,
            "channel": channel,
        })

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    event = json.loads(data)
                    if event.get("event") == "pong":
                        pass  # Could track pongs if needed
                except json.JSONDecodeError:
                    pass
        except WebSocketDisconnect:
            if websocket in twitch_chat_connections:
                twitch_chat_connections.remove(websocket)

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

        # Send hello message with version info for client version checking
        await websocket.send_json({
            "action": "hello",
            "version": __version__,
            "build_id": BUILD_ID,
        })

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
                        logger.debug(f"[{character}] Stream stopped at {playback_time:.2f}s - {word_count} words actually played: \"{actual_text[:100]}...\"")

                        # Update interrupted message with actual spoken text
                        if character in pending_interrupted:
                            msg_idx, persist, db_id = pending_interrupted[character]
                            await update_interrupted_message(
                                character, msg_idx, actual_text, persist, db_id
                            )
                            logger.debug(f"[{character}] Updated memory[{msg_idx}] with actual spoken text (persist={persist})")
                            del pending_interrupted[character]
                    elif event_type == "pong":
                        manager.record_pong(websocket)

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
    async def twitch_status() -> dict:
        """Get Twitch connection status."""
        # Get stored user info from database
        user_id = None
        username = None
        channel = None
        async with get_session() as session:
            result = await session.execute(select(TwitchConfig).limit(1))
            twitch_config = result.scalar_one_or_none()
            if twitch_config:
                user_id = twitch_config.user_id
                username = twitch_config.username
                channel = twitch_config.channel

        return {
            "connected": eventsub_manager.is_connected,
            "channel": channel,
            "user_id": user_id,
            "username": username,
        }

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
                twitch_config.user_id = request.user_id
                twitch_config.username = request.username
                twitch_config.channel = request.channel
                twitch_config.updated_at = datetime.utcnow()
            else:
                # Create new config
                twitch_config = TwitchConfig(
                    access_token=request.access_token,
                    user_id=request.user_id,
                    username=request.username,
                    channel=request.channel,
                )
                session.add(twitch_config)

            await session.commit()

        # Look up the channel's user ID (may be different from logged-in user)
        channel_user_id = request.user_id  # Default to logged-in user
        if request.channel.lower() != request.username.lower():
            # Different channel - look up its user ID
            try:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://api.twitch.tv/helix/users?login={request.channel}",
                        headers={
                            "Authorization": f"Bearer {request.access_token}",
                            "Client-Id": os.environ.get("TWITCH_CLIENT_ID", "h1x5odjr6qy1m8sesgev1p9wcssz63"),
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("data"):
                            channel_user_id = data["data"][0]["id"]
                            logger.info(f"Looked up channel {request.channel} -> user_id {channel_user_id}")
            except Exception as e:
                logger.warning(f"Failed to look up channel user ID: {e}")

        # Start EventSub for real-time chat via WebSocket
        try:
            # Set the chat callback to broadcast to WebSocket clients
            eventsub_manager.set_chat_callback(on_chat_message)

            await eventsub_manager.start(
                access_token=request.access_token,
                client_id=os.environ.get("TWITCH_CLIENT_ID", "h1x5odjr6qy1m8sesgev1p9wcssz63"),
                broadcaster_user_id=channel_user_id,  # Channel to monitor
                user_id=request.user_id,  # Authenticated user (for permissions)
                subscribe_to_chat=True,
                subscribe_to_redemptions=False,  # Don't subscribe to redemptions yet (Santa handles that)
            )
            logger.info(f"EventSub started for chat on #{request.channel} (broadcaster: {channel_user_id})")
        except Exception as e:
            logger.warning(f"Failed to start EventSub for chat: {e}")

        return {"success": True, "channel": request.channel, "user_id": request.user_id, "username": request.username}

    @app.post("/api/twitch/channel")
    async def twitch_set_channel(request: TwitchChannelRequest) -> dict:
        """Change the Twitch channel to listen to."""
        # Get stored config
        async with get_session() as session:
            result = await session.execute(select(TwitchConfig).limit(1))
            twitch_config = result.scalar_one_or_none()

            if not twitch_config:
                raise HTTPException(status_code=400, detail="Not logged in to Twitch")

            # Update channel
            twitch_config.channel = request.channel
            twitch_config.updated_at = datetime.utcnow()
            await session.commit()

            access_token = twitch_config.access_token
            user_id = twitch_config.user_id

        # Restart EventSub for the new channel
        try:
            # Look up channel's user ID
            channel_user_id = user_id  # Default
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.twitch.tv/helix/users?login={request.channel}",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Client-Id": os.environ.get("TWITCH_CLIENT_ID", "h1x5odjr6qy1m8sesgev1p9wcssz63"),
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data"):
                        channel_user_id = data["data"][0]["id"]
                        logger.info(f"Looked up channel {request.channel} -> user_id {channel_user_id}")

            # Restart EventSub with new broadcaster
            eventsub_manager.set_chat_callback(on_chat_message)
            await eventsub_manager.start(
                access_token=access_token,
                client_id=os.environ.get("TWITCH_CLIENT_ID", "h1x5odjr6qy1m8sesgev1p9wcssz63"),
                broadcaster_user_id=channel_user_id,
                user_id=user_id,
                subscribe_to_chat=True,
                subscribe_to_redemptions=False,
            )
            logger.info(f"EventSub restarted for chat on #{request.channel}")
        except Exception as e:
            logger.warning(f"Failed to restart EventSub for new channel: {e}")

        return {"success": True, "channel": request.channel}

    @app.post("/api/twitch/disconnect")
    async def twitch_disconnect() -> dict:
        """Disconnect from Twitch and clear saved credentials."""
        await eventsub_manager.stop()

        # Clear stored config from database
        async with get_session() as session:
            result = await session.execute(select(TwitchConfig).limit(1))
            twitch_config = result.scalar_one_or_none()
            if twitch_config:
                await session.delete(twitch_config)
                await session.commit()

        return {"success": True}

    @app.get("/api/twitch/chat")
    async def get_twitch_chat(seconds: int = 60) -> dict:
        """Get recent chat messages (for debugging/preview).

        Args:
            seconds: Number of seconds of chat history to retrieve
        """
        # Get channel from database
        channel = None
        async with get_session() as session:
            result = await session.execute(select(TwitchConfig).limit(1))
            twitch_config = result.scalar_one_or_none()
            if twitch_config:
                channel = twitch_config.channel

        if eventsub_manager.is_connected:
            context = await eventsub_manager.get_chat_context(seconds=seconds)
            return {
                "channel": channel,
                "context": context,
            }
        else:
            return {"messages": [], "channel": channel, "context": ""}

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
            tts_provider=c.tts_provider,
            tts_settings=json.loads(c.tts_settings) if c.tts_settings else None,
            connected=manager.is_connected(c.name),
            playing=manager._channel_state.get(c.name, {}).get("playing", False),
            streaming=manager._channel_state.get(c.name, {}).get("streaming", False),
            created_at=c.created_at,
            updated_at=c.updated_at,
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
    # Cartesia API endpoints
    # -------------------------------------------------------------------------

    @app.get("/api/cartesia/models")
    async def list_cartesia_models() -> list[dict]:
        """Get list of available Cartesia TTS models."""
        from .tts.cartesia import CartesiaClient, CartesiaError

        try:
            async with CartesiaClient() as client:
                return await client.get_models()
        except CartesiaError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except ValueError as e:
            # API key not configured
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/cartesia/voices")
    async def list_cartesia_voices() -> list[dict]:
        """Get list of available Cartesia voices."""
        from .tts.cartesia import CartesiaClient, CartesiaError

        try:
            async with CartesiaClient() as client:
                voices = await client.get_voices()
                return [
                    {
                        "voice_id": v.get("id"),
                        "name": v.get("name"),
                        "description": v.get("description"),
                        "language": v.get("language"),
                        "is_public": v.get("is_public"),
                    }
                    for v in voices
                ]
        except CartesiaError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except ValueError as e:
            # API key not configured
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/cartesia/voices/{voice_id}")
    async def get_cartesia_voice(voice_id: str) -> dict:
        """Get details for a specific Cartesia voice."""
        from .tts.cartesia import CartesiaClient, CartesiaError

        try:
            async with CartesiaClient() as client:
                voice = await client.get_voice(voice_id)
                return {
                    "voice_id": voice.get("id"),
                    "name": voice.get("name"),
                    "description": voice.get("description"),
                    "language": voice.get("language"),
                    "is_public": voice.get("is_public"),
                    "created_at": voice.get("created_at"),
                }
        except CartesiaError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except ValueError as e:
            # API key not configured
            raise HTTPException(status_code=500, detail=str(e))

    # -------------------------------------------------------------------------
    # Character CRUD and interaction endpoints
    # -------------------------------------------------------------------------

    def _validate_tts_settings(provider: str | None, settings: dict | None) -> None:
        """Validate TTS settings match the provider schema.

        Raises:
            HTTPException: If settings are invalid for the provider
        """
        from pydantic import ValidationError

        if not settings:
            return  # No settings to validate

        provider_type = TTSProviderType(provider or "elevenlabs")

        try:
            if provider_type == TTSProviderType.ELEVENLABS:
                ElevenLabsSettings(**settings)
            elif provider_type == TTSProviderType.CARTESIA:
                CartesiaSettings(**settings)
        except ValidationError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid TTS settings for {provider_type.value}: {e.errors()}"
            )

    async def _broadcast_all_characters() -> None:
        """Fetch all characters from DB and broadcast to all dashboard clients."""
        async with get_session() as session:
            result = await session.execute(select(Character))
            characters = list(result.scalars().all())
            char_dicts = [_character_to_response(c).model_dump() for c in characters]
            await manager.broadcast_character_sync(char_dicts)

    @app.post("/api/characters", status_code=201)
    async def create_character(request: CharacterCreate) -> Character:
        """Create a new character."""
        logger.info(f"POST /api/characters - creating \"{request.name}\"")

        # Validate TTS settings before saving
        _validate_tts_settings(request.tts_provider, request.tts_settings)

        async with get_session() as session:
            # Check if character already exists
            result = await session.execute(
                select(Character).where(Character.name == request.name)
            )
            if result.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Character already exists")

            # Serialize tts_settings dict to JSON string for storage
            data = request.model_dump()
            if data.get("tts_settings") is not None:
                data["tts_settings"] = json.dumps(data["tts_settings"])

            character = Character(**data)
            session.add(character)
            await session.commit()
            await session.refresh(character)
            await manager._notify_dashboard()
            await _broadcast_all_characters()
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
        logger.debug(f"PUT /api/characters/{name} - updating")

        async with get_session() as session:
            result = await session.execute(
                select(Character).where(Character.name == name)
            )
            character = result.scalar_one_or_none()
            if not character:
                raise HTTPException(status_code=404, detail="Character not found")

            # Optimistic concurrency control - reject if record was modified since client loaded it
            if request.expected_updated_at is not None:
                if character.updated_at != request.expected_updated_at:
                    raise HTTPException(
                        status_code=409,
                        detail="Character was modified by another client. Please refresh and try again."
                    )

            # Validate TTS settings if being updated
            # Use new provider if specified, otherwise use character's current provider
            provider_for_validation = request.tts_provider if request.tts_provider is not None else character.tts_provider
            if request.tts_settings is not None:
                _validate_tts_settings(provider_for_validation, request.tts_settings)

            update_data = request.model_dump(exclude_unset=True, exclude={"expected_updated_at"})
            # Serialize tts_settings dict to JSON string for storage
            if "tts_settings" in update_data and update_data["tts_settings"] is not None:
                update_data["tts_settings"] = json.dumps(update_data["tts_settings"])
            for key, value in update_data.items():
                setattr(character, key, value)
            character.updated_at = datetime.utcnow()

            await session.commit()
            await session.refresh(character)
            await manager._notify_dashboard()
            await _broadcast_all_characters()
            return character

    @app.delete("/api/characters/{name}")
    async def delete_character(name: str) -> dict:
        """Delete a character. Disconnects any active connection."""
        logger.info(f"DELETE /api/characters/{name}")

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
            await _broadcast_all_characters()
            return {"success": True, "deleted": name}

    @app.post("/api/characters/{name}/speak")
    async def character_speak(name: str, request: SpeakRequest) -> dict:
        """Speak text directly using character's voice (no AI).

        This endpoint:
        1. Looks up the character configuration
        2. Streams TTS audio to the connected browser
        """
        start_time = time.time()
        text_preview = request.text[:50] + "..." if len(request.text) > 50 else request.text
        logger.info(f"POST /api/characters/{name}/speak - \"{text_preview}\" ({len(request.text)} chars)")

        # Look up character
        async with get_session() as session:
            result = await session.execute(
                select(Character).where(Character.name == name)
            )
            character = result.scalar_one_or_none()
            if not character:
                raise HTTPException(status_code=404, detail="Character not found")

        # Get TTS provider and settings
        try:
            provider, settings = get_character_tts_config(character)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Check appropriate API key
        if provider == TTSProviderType.ELEVENLABS:
            if not os.environ.get("ELEVENLABS_API_KEY"):
                raise HTTPException(
                    status_code=500, detail="ELEVENLABS_API_KEY environment variable not set"
                )
        elif provider == TTSProviderType.CARTESIA:
            if not os.environ.get("CARTESIA_API_KEY"):
                raise HTTPException(
                    status_code=500, detail="CARTESIA_API_KEY environment variable not set"
                )

        # Verify character is connected
        if not manager.is_connected(name):
            raise HTTPException(
                status_code=400, detail=f"Character '{name}' is not connected"
            )

        # Create TTS and text display configs
        tts_config = TTSStreamConfig(
            provider=provider,
            settings=settings,
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

        # Acquire lock for entire streaming operation to prevent concurrent requests
        async with generation_locks[name]:
            if name in active_generations:
                await cancel_active_generation(name)
                await harness.stop_stream(name)
            active_generations[name] = streamer

            try:
                await streamer.stream(request.text)
                await harness._log_playback(name, request.text, "stream")
                elapsed = time.time() - start_time
                logger.info(f"POST /api/characters/{name}/speak - completed in {elapsed:.2f}s")
                return {"success": True, "character": name}
            except (ElevenLabsWSError, CartesiaWSError) as e:
                await harness.stop_stream(name)
                logger.error(f"POST /api/characters/{name}/speak - TTS error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
            except Exception as e:
                await harness.stop_stream(name)
                logger.error(f"POST /api/characters/{name}/speak - error: {e}")
                raise HTTPException(status_code=500, detail=f"TTS error: {e}")
            finally:
                active_generations.pop(name, None)

    @app.post("/api/characters/{name}/chat")
    async def character_chat(name: str, request: ChatRequest) -> ChatResponse:
        """Chat with a character - streams LLM response through TTS to browser.

        This endpoint:
        1. Looks up the character configuration
        2. Validates system_prompt is set (required for AI chat)
        3. Streams LLM response tokens through TTS (ElevenLabs or Cartesia)
        4. Sends audio and text to the browser in real-time
        """
        start_time = time.time()
        msg_preview = request.message[:50] + "..." if len(request.message) > 50 else request.message
        logger.info(f"POST /api/characters/{name}/chat - \"{msg_preview}\"")

        # Check OpenRouter API key (required for LLM)
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise HTTPException(
                status_code=500, detail="OPENROUTER_API_KEY environment variable not set"
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

        # Get TTS provider and settings
        try:
            provider, settings = get_character_tts_config(character)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Check appropriate TTS API key
        if provider == TTSProviderType.ELEVENLABS:
            if not os.environ.get("ELEVENLABS_API_KEY"):
                raise HTTPException(
                    status_code=500, detail="ELEVENLABS_API_KEY environment variable not set"
                )
        elif provider == TTSProviderType.CARTESIA:
            if not os.environ.get("CARTESIA_API_KEY"):
                raise HTTPException(
                    status_code=500, detail="CARTESIA_API_KEY environment variable not set"
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

        # Get Twitch chat context if enabled (using EventSub)
        twitch_chat_context = None
        if twitch_seconds > 0 and eventsub_manager.is_connected:
            twitch_chat_context = await eventsub_manager.get_chat_context(
                seconds=twitch_seconds,
                max_messages=character.twitch_chat_max_messages,
            )

        # Get conversation history if memory is enabled
        history = None
        if character.memory_enabled:
            all_history = conversation_memory.get(name, [])
            # Include user/assistant/context messages, converting context to user role
            history = []
            for m in all_history:
                role = m.get("role")
                if role in ("user", "assistant"):
                    history.append({"role": role, "content": m["content"]})
                elif role == "context":
                    # Include Twitch chat context as a user message so LLM remembers it
                    history.append({"role": "user", "content": f"[Twitch chat at the time]:\n{m['content']}"})

        # Create TTS and text display configs
        tts_config = TTSStreamConfig(
            provider=provider,
            settings=settings,
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
        images = None
        if request.images:
            images = [{"data": img.data, "media_type": img.media_type} for img in request.images]

        pipeline_config = ChatPipelineConfig(
            system_prompt=character.system_prompt,
            model=character.model,
            provider=character.provider,
            temperature=character.temperature,
            max_tokens=character.max_tokens,
            twitch_chat_context=twitch_chat_context,
            conversation_history=history,
            images=images,
        )

        # Create and run pipeline
        pipeline = ChatPipeline(
            config=pipeline_config,
            tts_streamer=tts_streamer,
        )

        # Acquire lock for entire pipeline operation to prevent concurrent requests
        async with generation_locks[name]:
            if name in active_generations:
                # Cancel the previous generation - it will save its own interrupted state
                await cancel_active_generation(name)
                await harness.stop_stream(name)
            active_generations[name] = pipeline

            try:
                response_text = await pipeline.run(request.message)

                # Store conversation in memory
                # Store twitch context if present
                if twitch_chat_context:
                    await save_conversation_message(
                        name, "context", twitch_chat_context, character.persist_memory
                    )
                # Build user content - multimodal if images present
                if images:
                    user_content: str | list = [{"type": "text", "text": request.message}]
                    for img in images:
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{img['media_type']};base64,{img['data']}"}
                        })
                else:
                    user_content = request.message
                await save_conversation_message(
                    name, "user", user_content, character.persist_memory
                )

                # Check if we were cancelled (interrupted by stop button or new chat)
                if pipeline._cancelled:
                    # Save as interrupted - browser will update content with actual spoken text
                    spoken_text = pipeline.get_spoken_text()
                    if spoken_text:
                        msg_idx, db_id = await save_conversation_message(
                            character_name=name,
                            role="assistant",
                            content=spoken_text,  # Will be updated by browser's stream_stopped
                            persist=character.persist_memory,
                            interrupted=True,
                            generated_text=response_text,  # Full LLM response for strikethrough
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

                elapsed = time.time() - start_time
                response_preview = response_text[:50] + "..." if len(response_text) > 50 else response_text
                logger.info(f"POST /api/characters/{name}/chat - completed in {elapsed:.2f}s - \"{response_preview}\"")

                return ChatResponse(
                    success=True,
                    character=name,
                    response_text=response_text,
                    twitch_chat_context=twitch_chat_context,
                )

            except Exception as e:
                # Force stop streams on error and clean up pending state
                pending_interrupted.pop(name, None)
                await harness.stop_stream(name)
                logger.error(f"POST /api/characters/{name}/chat - error: {e}")
                raise HTTPException(status_code=500, detail=f"Chat error: {e}")
            finally:
                active_generations.pop(name, None)

    @app.post("/api/characters/{name}/stop")
    async def stop_character_generation(name: str) -> dict:
        """Stop any active generation (speak/chat) for a character.

        Note: The interrupted message is saved by the original chat endpoint
        when it detects it was cancelled, not here.
        """
        was_active = False
        spoken_text = None

        async with generation_locks[name]:
            if name in active_generations:
                was_active = True
                # Cancel the generation (sets _cancelled=True)
                spoken_text = await cancel_active_generation(name)

        # Always send stop command to browser - audio may still be playing
        # even if generation has already completed
        await harness.stop_stream(name)

        if was_active:
            logger.info(f"POST /api/characters/{name}/stop - generation cancelled")
        else:
            logger.debug(f"POST /api/characters/{name}/stop - no active generation")

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

    # =========================================================================
    # Santa API Routes
    # =========================================================================

    @app.get("/api/santa/config")
    async def get_santa_config() -> SantaConfigResponse:
        """Get Santa configuration."""
        async with get_session() as session:
            result = await session.execute(select(SantaConfig).limit(1))
            config = result.scalar_one_or_none()
            if not config:
                config = SantaConfig()
                session.add(config)
                await session.commit()
                await session.refresh(config)

            return SantaConfigResponse(
                enabled=config.enabled,
                character_name=config.character_name,
                reward_id=config.reward_id,
                chat_vote_seconds=config.chat_vote_seconds,
                max_followups=config.max_followups,
                response_timeout_seconds=config.response_timeout_seconds,
                debounce_seconds=config.debounce_seconds,
            )

    @app.put("/api/santa/config")
    async def update_santa_config(request: SantaConfigUpdate) -> SantaConfigResponse:
        """Update Santa configuration."""
        nonlocal santa_manager

        async with get_session() as session:
            result = await session.execute(select(SantaConfig).limit(1))
            config = result.scalar_one_or_none()
            if not config:
                config = SantaConfig()
                session.add(config)

            # Track if enabled state changed
            old_enabled = config.enabled
            old_reward_id = config.reward_id

            update_data = request.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(config, key, value)
            config.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(config)

            # Update santa_manager with new settings if it exists
            if santa_manager:
                santa_manager.max_followups = config.max_followups
                santa_manager.response_timeout = config.response_timeout_seconds
                santa_manager.debounce_seconds = config.debounce_seconds
                santa_manager.chat_vote_seconds = config.chat_vote_seconds
                santa_manager.character_name = config.character_name

            # Enable/disable reward based on enabled state
            reward_id = config.reward_id
            if reward_id and eventsub_manager.is_connected:
                if config.enabled and not old_enabled:
                    # Santa was just enabled - enable the reward
                    await eventsub_manager.enable_reward(reward_id)
                    logger.info(f"Santa enabled - enabled reward {reward_id}")
                elif not config.enabled and old_enabled:
                    # Santa was just disabled - disable the reward
                    await eventsub_manager.disable_reward(reward_id)
                    logger.info(f"Santa disabled - disabled reward {reward_id}")

            return SantaConfigResponse(
                enabled=config.enabled,
                character_name=config.character_name,
                reward_id=config.reward_id,
                chat_vote_seconds=config.chat_vote_seconds,
                max_followups=config.max_followups,
                response_timeout_seconds=config.response_timeout_seconds,
                debounce_seconds=config.debounce_seconds,
            )

    @app.get("/api/santa/session")
    async def get_santa_session() -> SantaSessionStatus:
        """Get current Santa session status."""
        if not santa_manager:
            return SantaSessionStatus(active=False)

        status = santa_manager.get_session_status()
        return SantaSessionStatus(**status)

    @app.post("/api/santa/session/message")
    async def santa_session_message(request: SantaMessageRequest) -> dict:
        """Send a message to the active Santa session (dashboard override)."""
        if not santa_manager:
            raise HTTPException(status_code=500, detail="Santa manager not initialized")

        if not santa_manager.is_active:
            raise HTTPException(status_code=400, detail="No active Santa session")

        success = await santa_manager.send_message(request.message)
        return {"success": success}

    @app.post("/api/santa/session/verdict")
    async def santa_session_verdict(request: SantaVerdictRequest) -> dict:
        """Force a verdict on the active Santa session (skip chat voting)."""
        if not santa_manager:
            raise HTTPException(status_code=500, detail="Santa manager not initialized")

        if not santa_manager.is_active:
            raise HTTPException(status_code=400, detail="No active Santa session")

        success = await santa_manager.force_verdict(request.verdict)
        if success:
            # Finalize session after verdict
            await finalize_santa_session()
        return {"success": success}

    @app.post("/api/santa/session/cancel")
    async def santa_session_cancel() -> dict:
        """Cancel the active Santa session."""
        if not santa_manager:
            raise HTTPException(status_code=500, detail="Santa manager not initialized")

        if not santa_manager.is_active:
            return {"success": True, "message": "No active session to cancel"}

        await santa_manager.cancel_session("cancelled")
        await finalize_santa_session()
        return {"success": True}

    @app.post("/api/santa/start")
    async def santa_start() -> dict:
        """Start listening for channel point redemptions."""
        # Get Twitch config
        async with get_session() as session:
            result = await session.execute(select(TwitchConfig).limit(1))
            twitch_config = result.scalar_one_or_none()

        if not twitch_config:
            raise HTTPException(status_code=400, detail="Twitch not configured. Go to /twitch to sign in.")

        if not twitch_config.user_id:
            raise HTTPException(status_code=400, detail="Twitch user ID not set. Re-authenticate at /twitch.")

        # Get Santa config for reward_id
        async with get_session() as session:
            result = await session.execute(select(SantaConfig).limit(1))
            santa_config = result.scalar_one_or_none()

        try:
            await eventsub_manager.start(
                access_token=twitch_config.access_token,
                client_id=os.environ.get("TWITCH_CLIENT_ID", "h1x5odjr6qy1m8sesgev1p9wcssz63"),
                broadcaster_user_id=twitch_config.user_id,
                reward_id=santa_config.reward_id if santa_config else None,
                on_redemption=handle_channel_point_redemption,
            )
            return {"success": True, "message": "EventSub started"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to start EventSub: {e}")

    @app.post("/api/santa/stop")
    async def santa_stop() -> dict:
        """Stop listening for channel point redemptions."""
        await eventsub_manager.stop()
        return {"success": True, "message": "EventSub stopped"}

    @app.get("/api/santa/rewards")
    async def get_santa_rewards() -> dict:
        """Get available channel point rewards."""
        if not eventsub_manager.is_connected:
            return {"rewards": [], "message": "EventSub not connected"}

        rewards = await eventsub_manager.get_rewards()
        return {"rewards": rewards}

    @app.get("/api/santa/eventsub/status")
    async def get_eventsub_status() -> dict:
        """Get EventSub connection status."""
        return {
            "connected": eventsub_manager.is_connected,
        }

    @app.post("/api/santa/interrupt")
    async def santa_interrupt(request: dict) -> dict:
        """Send a Mall Director interruption through Santa (uses speech lock)."""
        message = request.get("message", "").strip()
        if not message:
            raise HTTPException(status_code=400, detail="Message required")

        if not santa_manager:
            raise HTTPException(status_code=500, detail="Santa manager not initialized")

        success = await santa_manager.interrupt_with_message(message)
        if success:
            return {"success": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to send interruption")

    @app.post("/api/santa/toggle")
    async def toggle_santa_enabled() -> dict:
        """Toggle Santa enabled state and immediately enable/disable reward."""
        async with get_session() as session:
            result = await session.execute(select(SantaConfig).limit(1))
            config = result.scalar_one_or_none()

            if not config:
                raise HTTPException(status_code=400, detail="Santa not configured")

            # Toggle the enabled state
            config.enabled = not config.enabled
            session.add(config)
            await session.commit()
            await session.refresh(config)

            new_enabled = config.enabled
            reward_id = config.reward_id

        # Enable/disable reward on Twitch
        if reward_id and eventsub_manager.is_connected:
            if new_enabled:
                await eventsub_manager.enable_reward(reward_id)
                logger.info(f"Santa enabled - enabled reward {reward_id}")
            else:
                await eventsub_manager.disable_reward(reward_id)
                logger.info(f"Santa disabled - disabled reward {reward_id}")

        return {"success": True, "enabled": new_enabled}

    @app.post("/api/santa/reward/create")
    async def create_santa_reward(
        title: str = "Talk to Santa",
        cost: int = 100,
        prompt: str = "Tell Santa your Christmas wish!",
    ) -> dict:
        """Create a new channel point reward for Santa wishes."""
        if not eventsub_manager.is_connected:
            raise HTTPException(status_code=400, detail="EventSub not connected")

        result = await eventsub_manager.create_reward(
            title=title,
            cost=cost,
            prompt=prompt,
            is_user_input_required=True,
            is_enabled=True,
        )

        if result:
            # Auto-save this reward to config
            async with get_session() as session:
                db_result = await session.execute(select(SantaConfig).limit(1))
                config = db_result.scalar_one_or_none()
                if config:
                    config.reward_id = result["id"]
                    session.add(config)
                    await session.commit()

            return {"success": True, "reward": result}
        else:
            raise HTTPException(status_code=500, detail="Failed to create reward")

    return app
