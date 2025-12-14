"""Database schemas and API models for OBS Harness."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField
from sqlmodel import SQLModel


# =============================================================================
# Database Models (SQLModel)
# =============================================================================


class TextPreset(SQLModel, table=True):
    """A saved text animation preset."""

    id: int | None = SQLField(default=None, primary_key=True)
    name: str = SQLField(unique=True, index=True)
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
    channel: str = SQLField(index=True)
    content: str  # filename or text content
    content_type: str  # "audio", "stream", "text"
    timestamp: datetime = SQLField(default_factory=datetime.utcnow)


class Character(SQLModel, table=True):
    """A character with voice settings and optional AI personality."""

    id: int | None = SQLField(default=None, primary_key=True)
    name: str = SQLField(unique=True, index=True)
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

    # Voice settings (required for TTS)
    elevenlabs_voice_id: str = SQLField()
    voice_stability: float = SQLField(default=0.5)
    voice_similarity_boost: float = SQLField(default=0.75)
    voice_style: float = SQLField(default=0.0)
    voice_speed: float = SQLField(default=1.0)

    # AI settings (optional - for chat endpoint)
    system_prompt: str | None = SQLField(default=None)
    model: str = SQLField(default="anthropic/claude-sonnet-4.5")
    temperature: float = SQLField(default=0.7)
    max_tokens: int = SQLField(default=1024)

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

    # Voice settings
    voice_stability: float = Field(default=0.5, ge=0.0, le=1.0)
    voice_similarity_boost: float = Field(default=0.75, ge=0.0, le=1.0)
    voice_style: float = Field(default=0.0, ge=0.0, le=1.0)
    voice_speed: float = Field(default=1.0, ge=0.5, le=2.0)

    # AI settings (optional)
    system_prompt: str | None = None
    model: str = "anthropic/claude-sonnet-4.5"
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=8192)


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

    # Voice settings
    elevenlabs_voice_id: str | None = None
    voice_stability: float | None = Field(default=None, ge=0.0, le=1.0)
    voice_similarity_boost: float | None = Field(default=None, ge=0.0, le=1.0)
    voice_style: float | None = Field(default=None, ge=0.0, le=1.0)
    voice_speed: float | None = Field(default=None, ge=0.5, le=2.0)

    # AI settings
    system_prompt: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)


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

    # Voice settings
    elevenlabs_voice_id: str
    voice_stability: float
    voice_similarity_boost: float
    voice_style: float
    voice_speed: float

    # AI settings
    system_prompt: str | None
    model: str
    temperature: float
    max_tokens: int

    # Status
    connected: bool = False
    playing: bool = False
    streaming: bool = False

    created_at: datetime


class ChatRequest(BaseModel):
    """Request to chat with a character."""

    message: str
    show_text: bool = True


class ChatResponse(BaseModel):
    """Response from character chat."""

    success: bool
    character: str
    response_text: str  # Full response for logging


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


class TextChunkCommand(BaseModel):
    """WebSocket command to send a text chunk for streaming display."""

    action: Literal["text_chunk"] = "text_chunk"
    text: str


class TextStreamEndCommand(BaseModel):
    """WebSocket command to end streaming text display."""

    action: Literal["text_stream_end"] = "text_stream_end"


class BrowserEvent(BaseModel):
    """Event message from browser to server."""

    event: str
    file: str | None = None
    message: str | None = None
