# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run the server
uv run obs-harness
uv run obs-harness --host 0.0.0.0 --port 8080 --reload

# Run with Python directly
uv run python -m obs_harness

# Build TypeScript frontend (required after changing frontend/src/*.ts)
cd frontend && npm install && npm run build

# Type check TypeScript without building
cd frontend && npm run typecheck
```

## Environment Variables

Required in `.env`:
- `ELEVENLABS_API_KEY` - For ElevenLabs TTS (optional if using Cartesia)
- `CARTESIA_API_KEY` - For Cartesia TTS (optional if using ElevenLabs)
- `OPENROUTER_API_KEY` - For LLM chat completions

Optional:
- `TWITCH_CLIENT_ID` - Defaults to `h1x5odjr6qy1m8sesgev1p9wcssz63` (public client)

## Architecture

FastAPI application for pushing audio and animated text to OBS via browser sources. Designed as a mountable sub-application.

### Core Components

**`app.py`** - Main module:
- `create_app(db_url, static_dir)` - Factory function returning FastAPI instance
- `ConnectionManager` - WebSocket hub managing browser source connections per channel
- `OBSHarness` - Python API for controlling audio/text (attached to `app.state.harness`)

**`chat_pipeline.py`** - Orchestrates LLM → TTS → Browser streaming with sentence boundary detection

**`tts/provider.py`** - TTS provider abstraction:
- `TTSProviderClient` protocol implemented by both providers
- `create_tts_client(provider, settings)` factory function
- `ElevenLabsSettings` / `CartesiaSettings` Pydantic models for validation

**`tts/elevenlabs_ws.py` / `tts/cartesia_ws.py`** - WebSocket TTS clients with word timing support

**`twitch_chat.py`** - IRC-based Twitch chat (uses TwitchIO)

**`twitch_eventsub.py`** - EventSub WebSocket client for channel points and chat events

**`santa_session.py`** - Mall Santa feature: state machine for multi-turn wish-granting conversations triggered by channel point redemptions

**`routes/moderators.py`** - Moderator management API for multi-tenant access control

**Data Flow:**
```
# Simple audio/text
Python API / REST → OBSHarness → ConnectionManager → WebSocket → Browser Sources → OBS

# Chat pipeline (LLM + TTS)
User Message → OpenRouter LLM (streaming) → ChatPipeline → TTS Provider → Browser Audio
                                         └→ Browser Text (progressive reveal with word timing)
```

### Key Patterns

**Mountable Sub-App**:
```python
main_app.mount("/obs", create_app())
harness = obs_app.state.harness  # Access the control API
```

**WebSocket Protocol**: JSON commands for control, binary frames for audio streaming:
- Server→Browser: `{"action": "play"|"stop"|"text"|"stream_start"|"text_chunk"|...}`
- Browser→Server: `{"event": "ended"|"stream_ended"|"text_complete"|"error"}`

**Audio Streaming**: PCM16 format for real-time TTS:
```python
await harness.stream_start(channel, sample_rate=24000, channels=1)
await harness.stream_audio(channel, pcm_bytes)
await harness.stream_end(channel)
```

**TTS Provider Selection**: Characters store `tts_provider` ("elevenlabs" | "cartesia") and `tts_settings` (JSON blob validated by provider-specific Pydantic models)

### Character System

Characters are persistent entities with voice, text styling, and AI configuration:
- `POST /api/characters/{name}/speak` - Direct TTS (no AI)
- `POST /api/characters/{name}/chat` - AI chat with TTS response
- Characters store provider settings, OpenRouter model, system prompt, and text display settings
- Optional conversation memory (in-memory or persisted to `ConversationMessage` table)

### Database

SQLite via SQLModel (async with aiosqlite). Tables:
- `Character` - AI character configurations with TTS provider settings
- `TextPreset` - Saved text animation presets
- `PlaybackLog` - History of audio/text playback
- `TwitchConfig` - OAuth tokens and channel settings
- `ConversationMessage` - Persisted conversation history (when `persist_memory=True`)
- `SantaModerator` - Cross-channel moderator permissions
- `SantaConfig` - Per-channel Santa feature configuration
- `SantaSession` - Active Santa session state

### Frontend

TypeScript sources in `frontend/src/`, built outputs in `static/js/` (don't edit JS files directly):

- `frontend/src/channel.ts` → `static/js/channel.js` - Browser source handler (Web Audio API)
- `frontend/src/text-animator.ts` → `static/js/text-animator.js` - Canvas-based text animations
- `frontend/src/dashboard.ts` → `static/js/dashboard.js` - Dashboard WebSocket client
- `frontend/src/santa.ts` → `static/js/santa.js` - Santa dashboard client

### Multi-Tenant Auth

Cookie-based authentication with `tenant_id` (Twitch user ID):
- `/api/auth/twitch/callback` sets `tenant_id` cookie after OAuth
- `require_auth` dependency extracts tenant from cookie
- `?channel=` query param allows viewing another channel (with moderator access)
- `SantaModerator` table stores cross-channel permissions

### Web Pages

- `/` - Main dashboard (characters, playback controls)
- `/configuration` - Twitch OAuth, channel settings, moderator management
- `/santa` - Santa Timmy dashboard (channel point redemptions)
- `/editor` - Text animation preset editor
- `/channel/{name}` - Browser source for OBS
