"""Database schemas and API models for OBS Harness."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel

if TYPE_CHECKING:
    from .tts.provider import TTSProviderType


# =============================================================================
# Database Models (SQLModel)
# =============================================================================


class TextPreset(SQLModel, table=True):
    """A saved text animation preset."""

    id: int | None = SQLField(default=None, primary_key=True)
    tenant_id: str = SQLField(default="default", index=True)  # Multi-tenancy
    name: str = SQLField(index=True)  # Unique per tenant (composite constraint)
    style: str = SQLField(default="typewriter")
    font_family: str = SQLField(default="Arial")
    font_size: int = SQLField(default=48)
    color: str = SQLField(default="#ffffff")
    stroke_color: str | None = SQLField(default=None)
    stroke_width: int = SQLField(default=0)
    position_x: float = SQLField(default=0.5)  # 0-1 normalized
    position_y: float = SQLField(default=0.5)  # 0-1 normalized
    duration: int = SQLField(default=3000)  # milliseconds
    created_at: datetime = SQLField(default_factory=datetime.utcnow)


class PlaybackLog(SQLModel, table=True):
    """Log of playback events for history."""

    id: int | None = SQLField(default=None, primary_key=True)
    tenant_id: str = SQLField(default="default", index=True)  # Multi-tenancy
    channel: str = SQLField(index=True)
    content: str  # filename or text content
    content_type: str  # "audio", "stream", "text"
    timestamp: datetime = SQLField(default_factory=datetime.utcnow)


class TwitchConfig(SQLModel, table=True):
    """Twitch configuration (one per tenant)."""

    id: int | None = SQLField(default=None, primary_key=True)
    tenant_id: str = SQLField(default="default", unique=True, index=True)  # Multi-tenancy
    # Auth - the logged-in user (for EventSub channel points)
    access_token: str  # OAuth access token
    refresh_token: str | None = SQLField(default=None)  # OAuth refresh token (auth code flow)
    token_expires_at: datetime | None = SQLField(default=None)  # When access token expires
    user_id: str | None = SQLField(default=None)  # Logged-in user's Twitch ID
    username: str | None = SQLField(default=None)  # Logged-in user's username
    # Chat - which channel to read chat from (can be different from logged-in user)
    channel: str  # Channel to join for chat (without #)
    updated_at: datetime = SQLField(default_factory=datetime.utcnow)


class UserSettings(SQLModel, table=True):
    """Per-tenant user settings including API keys (BYOK)."""

    id: int | None = SQLField(default=None, primary_key=True)
    tenant_id: str = SQLField(unique=True, index=True)

    # API Keys (Bring Your Own Key)
    elevenlabs_api_key: str | None = SQLField(default=None)
    cartesia_api_key: str | None = SQLField(default=None)
    openrouter_api_key: str | None = SQLField(default=None)

    updated_at: datetime = SQLField(default_factory=datetime.utcnow)


class ConversationMessage(SQLModel, table=True):
    """A message in a character's conversation history."""

    id: int | None = SQLField(default=None, primary_key=True)
    tenant_id: str = SQLField(default="default", index=True)  # Multi-tenancy
    character_name: str = SQLField(index=True)  # Foreign key to Character.name
    role: str  # "user", "assistant", or "context"
    content: str  # The message content
    interrupted: bool = SQLField(default=False)  # Was this message interrupted?
    generated_text: str | None = SQLField(default=None)  # Full text if interrupted
    created_at: datetime = SQLField(default_factory=datetime.utcnow)


class Character(SQLModel, table=True):
    """A character with voice settings and optional AI personality."""

    id: int | None = SQLField(default=None, primary_key=True)
    tenant_id: str = SQLField(default="default", index=True)  # Multi-tenancy
    name: str = SQLField(index=True)  # Unique per tenant (composite constraint)
    description: str | None = SQLField(default=None)

    # Display settings
    color: str = SQLField(default="#e94560")
    icon: str = SQLField(default="🔊")

    # Audio settings
    default_volume: float = SQLField(default=1.0)
    mute_state: bool = SQLField(default=False)

    # Text style settings
    default_text_style: str = SQLField(default="typewriter")
    text_font_family: str = SQLField(default="Arial")
    text_font_size: int = SQLField(default=48)
    text_color: str = SQLField(default="#ffffff")
    text_stroke_color: str | None = SQLField(default=None)
    text_stroke_width: int = SQLField(default=0)
    text_position_x: float = SQLField(default=0.5)
    text_position_y: float = SQLField(default=0.5)
    text_duration: int = SQLField(default=3000)

    # TTS Provider settings
    tts_provider: str = SQLField(default="elevenlabs")  # "elevenlabs" | "cartesia"
    tts_settings: str | None = SQLField(default=None)  # JSON blob for provider-specific settings

    # Voice settings (legacy - kept for backwards compatibility with ElevenLabs)
    elevenlabs_voice_id: str = SQLField()
    elevenlabs_model_id: str = SQLField(default="eleven_multilingual_v2")
    voice_stability: float = SQLField(default=0.5)
    voice_similarity_boost: float = SQLField(default=0.75)
    voice_style: float = SQLField(default=0.0)
    voice_speed: float = SQLField(default=1.0)

    # AI settings (optional - for chat endpoint)
    system_prompt: str | None = SQLField(default=None)
    model: str = SQLField(default="anthropic/claude-sonnet-4.5")
    provider: str | None = SQLField(default=None)  # OpenRouter provider routing (None = default)
    temperature: float = SQLField(default=0.7)
    max_tokens: int = SQLField(default=1024)

    # Twitch chat settings
    twitch_chat_enabled: bool = SQLField(default=False)
    twitch_chat_window_seconds: int = SQLField(default=60)
    twitch_chat_max_messages: int = SQLField(default=20)

    # Conversation memory settings
    memory_enabled: bool = SQLField(default=False)
    persist_memory: bool = SQLField(default=False)  # Save memory through restarts

    # WebSocket authentication token for OBS browser sources
    ws_token: str | None = SQLField(default=None, index=True)

    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime | None = SQLField(default=None)


# =============================================================================
# API Request/Response Models (Pydantic)
# =============================================================================


class PlayRequest(BaseModel):
    """Request to play an audio file."""

    file: str
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    loop: bool = False


class StreamStartRequest(BaseModel):
    """Request to start an audio stream."""

    sample_rate: int = Field(default=24000, ge=8000, le=48000)
    channels: int = Field(default=1, ge=1, le=2)
    format: Literal["pcm16"] = "pcm16"


class TextRequest(BaseModel):
    """Request to display animated text."""

    text: str
    style: str = "typewriter"
    duration: int = Field(default=3000, ge=100)  # milliseconds
    position_x: float = Field(default=0.5, ge=0.0, le=1.0)
    position_y: float = Field(default=0.5, ge=0.0, le=1.0)
    font_family: str | None = None
    font_size: int | None = None
    color: str | None = None
    stroke_color: str | None = None
    stroke_width: int | None = None


class VolumeRequest(BaseModel):
    """Request to set volume level."""

    level: float = Field(ge=0.0, le=1.0)


class PresetCreate(BaseModel):
    """Request to create a text preset."""

    name: str
    style: str = "typewriter"
    font_family: str = "Arial"
    font_size: int = 48
    color: str = "#ffffff"
    stroke_color: str | None = None
    stroke_width: int = 0
    position_x: float = 0.5
    position_y: float = 0.5
    duration: int = 3000


class CharacterStatus(BaseModel):
    """Status information for a character."""

    name: str
    connected: bool
    playing: bool = False
    streaming: bool = False


class SpeakRequest(BaseModel):
    """Request to speak text directly (no AI)."""

    text: str
    show_text: bool = True
    text_style: str | None = None
    text_duration: int | None = None  # Auto-calculated if not provided


class CharacterCreate(BaseModel):
    """Request to create a character."""

    name: str
    description: str | None = None
    elevenlabs_voice_id: str

    # Display settings
    color: str = "#e94560"
    icon: str = "🔊"

    # Audio settings
    default_volume: float = Field(default=1.0, ge=0.0, le=1.0)
    mute_state: bool = False

    # Text style settings
    default_text_style: str = "typewriter"
    text_font_family: str = "Arial"
    text_font_size: int = Field(default=48, ge=12, le=200)
    text_color: str = "#ffffff"
    text_stroke_color: str | None = None
    text_stroke_width: int = Field(default=0, ge=0, le=20)
    text_position_x: float = Field(default=0.5, ge=0.0, le=1.0)
    text_position_y: float = Field(default=0.5, ge=0.0, le=1.0)
    text_duration: int = Field(default=3000, ge=500, le=30000)

    # TTS Provider settings
    tts_provider: str = "elevenlabs"  # "elevenlabs" | "cartesia"
    tts_settings: dict | None = None  # Provider-specific settings JSON

    # Voice settings (legacy ElevenLabs fields - used if tts_settings is None)
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    voice_stability: float = Field(default=0.5, ge=0.0, le=1.0)
    voice_similarity_boost: float = Field(default=0.75, ge=0.0, le=1.0)
    voice_style: float = Field(default=0.0, ge=0.0, le=1.0)
    voice_speed: float = Field(default=1.0, ge=0.5, le=2.0)  # Expanded range for Cartesia

    # AI settings (optional)
    system_prompt: str | None = None
    model: str = "anthropic/claude-sonnet-4.5"
    provider: str | None = None  # OpenRouter provider routing (None = default)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=8192)

    # Twitch chat settings
    twitch_chat_enabled: bool = False
    twitch_chat_window_seconds: int = Field(default=60, ge=10, le=300)
    twitch_chat_max_messages: int = Field(default=20, ge=5, le=50)

    # Conversation memory settings
    memory_enabled: bool = False
    persist_memory: bool = False


class CharacterUpdate(BaseModel):
    """Request to update a character."""

    description: str | None = None

    # Display settings
    color: str | None = None
    icon: str | None = None

    # Audio settings
    default_volume: float | None = Field(default=None, ge=0.0, le=1.0)
    mute_state: bool | None = None

    # Text style settings
    default_text_style: str | None = None
    text_font_family: str | None = None
    text_font_size: int | None = Field(default=None, ge=12, le=200)
    text_color: str | None = None
    text_stroke_color: str | None = None
    text_stroke_width: int | None = Field(default=None, ge=0, le=20)
    text_position_x: float | None = Field(default=None, ge=0.0, le=1.0)
    text_position_y: float | None = Field(default=None, ge=0.0, le=1.0)
    text_duration: int | None = Field(default=None, ge=500, le=30000)

    # TTS Provider settings
    tts_provider: str | None = None  # "elevenlabs" | "cartesia"
    tts_settings: dict | None = None  # Provider-specific settings JSON

    # Voice settings (legacy ElevenLabs fields)
    elevenlabs_voice_id: str | None = None
    elevenlabs_model_id: str | None = None
    voice_stability: float | None = Field(default=None, ge=0.0, le=1.0)
    voice_similarity_boost: float | None = Field(default=None, ge=0.0, le=1.0)
    voice_style: float | None = Field(default=None, ge=0.0, le=1.0)
    voice_speed: float | None = Field(default=None, ge=0.5, le=2.0)  # Expanded range

    # AI settings
    system_prompt: str | None = None
    model: str | None = None
    provider: str | None = None  # OpenRouter provider routing (None = default)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)

    # Twitch chat settings
    twitch_chat_enabled: bool | None = None
    twitch_chat_window_seconds: int | None = Field(default=None, ge=10, le=300)
    twitch_chat_max_messages: int | None = Field(default=None, ge=5, le=1000)

    # Conversation memory settings
    memory_enabled: bool | None = None
    persist_memory: bool | None = None

    # Optimistic concurrency control
    expected_updated_at: datetime | None = None  # If provided, update fails if record was modified


class CharacterResponse(BaseModel):
    """Character information response."""

    id: int
    name: str
    description: str | None

    # Display settings
    color: str
    icon: str

    # Audio settings
    default_volume: float
    mute_state: bool

    # Text style settings
    default_text_style: str
    text_font_family: str
    text_font_size: int
    text_color: str
    text_stroke_color: str | None
    text_stroke_width: int
    text_position_x: float
    text_position_y: float
    text_duration: int

    # TTS Provider settings
    tts_provider: str
    tts_settings: dict | None

    # Voice settings (legacy ElevenLabs fields)
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
    voice_stability: float
    voice_similarity_boost: float
    voice_style: float
    voice_speed: float

    # AI settings
    system_prompt: str | None
    model: str
    provider: str | None
    temperature: float
    max_tokens: int

    # Twitch chat settings
    twitch_chat_enabled: bool
    twitch_chat_window_seconds: int
    twitch_chat_max_messages: int

    # Conversation memory settings
    memory_enabled: bool
    persist_memory: bool

    # WebSocket authentication token for OBS browser sources
    ws_token: str | None = None

    # Status
    connected: bool = False
    playing: bool = False
    streaming: bool = False

    created_at: datetime
    updated_at: datetime | None = None


class ImageData(BaseModel):
    """Image data for multimodal chat requests."""

    data: str  # Base64-encoded image data
    media_type: str = "image/png"  # MIME type (image/png, image/jpeg, image/webp, image/gif)


class ChatRequest(BaseModel):
    """Request to chat with a character."""

    message: str
    show_text: bool = True
    twitch_chat_seconds: int | None = Field(default=None, ge=0, le=300)  # Override character default, 0 = disabled
    images: list[ImageData] | None = None  # Optional images for vision models


class ChatResponse(BaseModel):
    """Response from character chat."""

    success: bool
    character: str
    response_text: str  # Full response for logging
    twitch_chat_context: str | None = None  # Truncated Twitch chat that was included


# =============================================================================
# WebSocket Message Models
# =============================================================================


class WSAction(str, Enum):
    """Actions sent from server to browser."""

    PLAY = "play"
    STOP = "stop"
    VOLUME = "volume"
    STREAM_START = "stream_start"
    STREAM_END = "stream_end"
    TEXT = "text"
    CLEAR_TEXT = "clear_text"
    TEXT_STREAM_START = "text_stream_start"
    TEXT_CHUNK = "text_chunk"
    TEXT_STREAM_END = "text_stream_end"


class WSEvent(str, Enum):
    """Events sent from browser to server."""

    ENDED = "ended"
    STREAM_ENDED = "stream_ended"
    TEXT_COMPLETE = "text_complete"
    ERROR = "error"


class PlayCommand(BaseModel):
    """WebSocket command to play audio."""

    action: Literal["play"] = "play"
    file: str
    volume: float = 1.0
    loop: bool = False


class StopCommand(BaseModel):
    """WebSocket command to stop audio."""

    action: Literal["stop"] = "stop"


class VolumeCommand(BaseModel):
    """WebSocket command to set volume."""

    action: Literal["volume"] = "volume"
    level: float


class StreamStartCommand(BaseModel):
    """WebSocket command to start audio stream."""

    action: Literal["stream_start"] = "stream_start"
    sample_rate: int = 24000
    channels: int = 1
    format: str = "pcm16"


class StreamEndCommand(BaseModel):
    """WebSocket command to end audio stream."""

    action: Literal["stream_end"] = "stream_end"


class StopStreamCommand(BaseModel):
    """WebSocket command to forcefully stop audio stream and clear playback."""

    action: Literal["stop_stream"] = "stop_stream"


class TextCommand(BaseModel):
    """WebSocket command to display text."""

    action: Literal["text"] = "text"
    text: str
    style: str = "typewriter"
    duration: int = 3000
    position_x: float = 0.5
    position_y: float = 0.5
    font_family: str = "Arial"
    font_size: int = 48
    color: str = "#ffffff"
    stroke_color: str | None = None
    stroke_width: int = 0


class ClearTextCommand(BaseModel):
    """WebSocket command to clear text overlay."""

    action: Literal["clear_text"] = "clear_text"


class TextStreamStartCommand(BaseModel):
    """WebSocket command to start streaming text display."""

    action: Literal["text_stream_start"] = "text_stream_start"
    font_family: str = "Arial"
    font_size: int = 48
    color: str = "#ffffff"
    stroke_color: str | None = None
    stroke_width: int = 0
    position_x: float = 0.5
    position_y: float = 0.5
    instant_reveal: bool = False  # If True, show all text immediately


class TextChunkCommand(BaseModel):
    """WebSocket command to send a text chunk for streaming display."""

    action: Literal["text_chunk"] = "text_chunk"
    text: str


class TextStreamEndCommand(BaseModel):
    """WebSocket command to end streaming text display."""

    action: Literal["text_stream_end"] = "text_stream_end"


class WordTimingItem(BaseModel):
    """A single word with timing information."""

    word: str
    start: float  # seconds from audio start
    end: float


class WordTimingCommand(BaseModel):
    """WebSocket command to send word timing data for synced text reveal."""

    action: Literal["word_timing"] = "word_timing"
    words: list[WordTimingItem]


class BrowserEvent(BaseModel):
    """Event message from browser to server."""

    event: str
    file: str | None = None
    message: str | None = None


# =============================================================================
# TTS Provider Helper Functions
# =============================================================================


def get_character_tts_config(character: Character) -> tuple[TTSProviderType, dict]:
    """Get TTS provider and settings for a character.

    Handles backwards compatibility by falling back to legacy ElevenLabs fields
    if tts_settings is not set.

    Args:
        character: The character to get TTS config for

    Returns:
        Tuple of (provider_type, settings_dict)

    Raises:
        ValueError: If provider is Cartesia but tts_settings is not set,
                    or if tts_settings contains invalid JSON
    """
    from .tts.provider import TTSProviderType

    provider = TTSProviderType(character.tts_provider or "elevenlabs")

    # If tts_settings is set, use it
    if character.tts_settings:
        try:
            settings = json.loads(character.tts_settings)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Character '{character.name}' has invalid tts_settings JSON: {e}"
            )
        return provider, settings

    # Backwards compatibility: construct from legacy ElevenLabs fields
    if provider == TTSProviderType.ELEVENLABS:
        return provider, {
            "voice_id": character.elevenlabs_voice_id,
            "model_id": character.elevenlabs_model_id,
            "stability": character.voice_stability,
            "similarity_boost": character.voice_similarity_boost,
            "style": character.voice_style,
            "speed": character.voice_speed,
        }
    elif provider == TTSProviderType.CARTESIA:
        # Cartesia requires tts_settings to be set
        raise ValueError(
            f"Character '{character.name}' uses Cartesia but has no tts_settings configured"
        )

    raise ValueError(f"Unknown TTS provider: {provider}")


# =============================================================================
# Twitch API Models
# =============================================================================


class TwitchTokenRequest(BaseModel):
    """Request to save Twitch OAuth token."""

    access_token: str
    user_id: str  # Logged-in user's Twitch ID
    username: str  # Logged-in user's username
    channel: str  # Channel to monitor for chat


class TwitchChannelRequest(BaseModel):
    """Request to set Twitch channel to monitor."""

    channel: str


class TwitchStatusResponse(BaseModel):
    """Twitch connection status response."""

    connected: bool
    channel: str | None = None  # Chat channel being monitored
    user_id: str | None = None  # Logged-in user ID
    username: str | None = None  # Logged-in username
    token_expires_at: datetime | None = None  # When access token expires
    has_refresh_token: bool = False  # Whether we can auto-refresh


# =============================================================================
# Moderator Models
# =============================================================================


class Moderator(SQLModel, table=True):
    """Moderator allowlist for dashboard access.

    Allows broadcasters to grant moderators access to their dashboard.
    Moderators can control playback and characters but cannot create/delete
    characters or modify configuration.
    """

    id: int | None = SQLField(default=None, primary_key=True)
    broadcaster_tenant_id: str = SQLField(index=True)  # Broadcaster who grants access
    moderator_user_id: str = SQLField(index=True)  # Twitch user ID of moderator
    moderator_username: str  # Display username for UI
    created_at: datetime = SQLField(default_factory=datetime.utcnow)


class ModeratorAdd(BaseModel):
    """Request to add a moderator to the allowlist."""

    username: str  # Twitch username to add


class ModeratorResponse(BaseModel):
    """Moderator information in responses."""

    user_id: str
    username: str
    added_at: datetime


class AccessibleChannel(BaseModel):
    """A channel the user can access (own or as moderator)."""

    tenant_id: str
    username: str
    is_own: bool


# =============================================================================
# API Key Models
# =============================================================================


class ApiKey(SQLModel, table=True):
    """API key for programmatic access to tenant resources.

    Keys are stored as SHA-256 hashes for security.
    The full key is only shown once at creation time.
    """

    id: int | None = SQLField(default=None, primary_key=True)
    tenant_id: str = SQLField(index=True)  # Owner of this key
    key_hash: str = SQLField(index=True)  # SHA-256 hash of the key
    key_prefix: str  # First 8 chars for identification (e.g., "obs_abc1...")
    label: str  # User-provided label (e.g., "Stream Deck", "Discord Bot")
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    last_used_at: datetime | None = SQLField(default=None)


class ApiKeyCreate(BaseModel):
    """Request to create a new API key."""

    label: str


class ApiKeyResponse(BaseModel):
    """API key information in responses (without the actual key)."""

    id: int
    key_prefix: str
    label: str
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreated(BaseModel):
    """Response when creating a new API key (includes the full key ONCE)."""

    id: int
    key: str  # Full key - only shown once!
    key_prefix: str
    label: str
    created_at: datetime


