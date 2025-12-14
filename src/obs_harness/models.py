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


class Channel(SQLModel, table=True):
    """A channel configuration stored in the database."""

    id: int | None = SQLField(default=None, primary_key=True)
    name: str = SQLField(unique=True, index=True)
    description: str | None = SQLField(default=None)
    default_volume: float = SQLField(default=1.0)
    default_text_style: str = SQLField(default="typewriter")
    elevenlabs_voice_id: str | None = SQLField(default=None)
    mute_state: bool = SQLField(default=False)
    color: str = SQLField(default="#e94560")
    icon: str = SQLField(default="🔊")
    created_at: datetime = SQLField(default_factory=datetime.utcnow)
    updated_at: datetime | None = SQLField(default=None)


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


class ChannelStatus(BaseModel):
    """Status information for a channel."""

    name: str
    connected: bool
    playing: bool = False
    streaming: bool = False


class ChannelCreate(BaseModel):
    """Request to create a channel."""

    name: str
    description: str | None = None
    default_volume: float = Field(default=1.0, ge=0.0, le=1.0)
    default_text_style: str = "typewriter"
    elevenlabs_voice_id: str | None = None
    mute_state: bool = False
    color: str = "#e94560"
    icon: str = "🔊"


class ChannelUpdate(BaseModel):
    """Request to update a channel."""

    description: str | None = None
    default_volume: float | None = Field(default=None, ge=0.0, le=1.0)
    default_text_style: str | None = None
    elevenlabs_voice_id: str | None = None
    mute_state: bool | None = None
    color: str | None = None
    icon: str | None = None


class ChannelResponse(BaseModel):
    """Full channel information response."""

    id: int
    name: str
    description: str | None
    default_volume: float
    default_text_style: str
    elevenlabs_voice_id: str | None
    mute_state: bool
    color: str
    icon: str
    connected: bool = False
    playing: bool = False
    streaming: bool = False
    created_at: datetime


class TTSRequest(BaseModel):
    """Request to generate and play TTS on a channel."""

    text: str
    show_text: bool = True
    text_style: str | None = None
    text_duration: int | None = None  # Auto-calculated if not provided


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


class BrowserEvent(BaseModel):
    """Event message from browser to server."""

    event: str
    file: str | None = None
    message: str | None = None
