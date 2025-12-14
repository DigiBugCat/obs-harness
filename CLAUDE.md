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
```

## Environment Variables

Required in `.env`:
- `ELEVENLABS_API_KEY` - For TTS audio generation
- `OPENROUTER_API_KEY` - For LLM chat completions

Optional (Twitch integration configured via `/twitch` page):
- `TWITCH_CLIENT_ID` - Defaults to `h1x5odjr6qy1m8sesgev1p9wcssz63` (public client, no secret needed)

## Architecture

This is a FastAPI application for pushing audio and animated text to OBS via browser sources. It's designed as a mountable sub-application for larger streaming automation systems.

### Core Components

**`app.py`** - The main module containing:
- `create_app(db_url, static_dir)` - Factory function returning a FastAPI instance
- `ConnectionManager` - WebSocket hub managing browser source connections per channel
- `OBSHarness` - Python API for controlling audio/text (attached to `app.state.harness`)

**`chat_pipeline.py`** - Orchestrates LLM → TTS → Browser streaming:
- `ChatPipeline` - Streams LLM tokens, buffers sentences, sends to TTS, forwards audio to browser
- Sentence boundary detection for natural TTS chunking

**`elevenlabs.py` / `elevenlabs_ws.py`** - ElevenLabs TTS integration (REST and WebSocket)

**`openrouter.py`** - OpenRouter LLM client with streaming support

**`twitch_chat.py`** - Twitch chat integration:
- `TwitchChatManager` - Manages connection lifecycle and chat buffer
- `ChatBuffer` - In-memory ring buffer storing recent chat messages
- Characters can have `twitch_chat_enabled` to inject recent chat into AI prompts

**Data Flow:**
```
# Simple audio/text
Python API / REST → OBSHarness → ConnectionManager → WebSocket → Browser Sources → OBS

# Chat pipeline (LLM + TTS)
User Message → OpenRouter LLM (streaming) → ChatPipeline → ElevenLabs TTS → Browser Audio
                                         └→ Browser Text (progressive reveal)
```

### Key Patterns

**Mountable Sub-App**: The harness is designed to be mounted in a larger FastAPI application:
```python
main_app.mount("/obs", create_app())
harness = obs_app.state.harness  # Access the control API
```

**WebSocket Protocol**: JSON commands for control, binary frames for audio streaming:
- Server→Browser: `{"action": "play"|"stop"|"text"|"stream_start"|"text_chunk"|...}`
- Browser→Server: `{"event": "ended"|"stream_ended"|"text_complete"|"error"}`

**Audio Streaming**: For real-time audio (TTS), use PCM16 format:
```python
await harness.stream_start(channel, sample_rate=24000, channels=1)
await harness.stream_audio(channel, pcm_bytes)
await harness.stream_end(channel)
```

### Character System

Characters are persistent entities with voice, text styling, and AI configuration:
- `POST /api/characters/{name}/speak` - Direct TTS (no AI)
- `POST /api/characters/{name}/chat` - AI chat with TTS response
- Characters store ElevenLabs voice_id, OpenRouter model, system prompt, and text display settings

### Frontend

- `static/js/channel.js` - Browser source handler (audio + text + streaming via Web Audio API)
- `static/js/text-animator.js` - Canvas-based text animations (typewriter, fade, slide, bounce, wave)
- `static/js/dashboard.js` - Dashboard WebSocket client

### Twitch Integration

Characters can "read" Twitch chat by enabling `twitch_chat_enabled`. When enabled:
- Recent chat messages (configurable window) are injected into the AI system prompt
- Configure via `/twitch` page (OAuth implicit grant flow)
- Token stored in `TwitchConfig` table, auto-connects on startup

### Database

SQLite via SQLModel (async with aiosqlite). Tables: `Character`, `TextPreset`, `PlaybackLog`, `TwitchConfig`.
