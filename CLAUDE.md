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

## Architecture

This is a FastAPI application for pushing audio and animated text to OBS via browser sources. It's designed as a mountable sub-application for larger streaming automation systems.

### Core Components

**`app.py`** - The main module containing:
- `create_app(db_url, static_dir)` - Factory function returning a FastAPI instance
- `ConnectionManager` - WebSocket hub managing browser source connections per channel
- `OBSHarness` - Python API for controlling audio/text (attached to `app.state.harness`)

**Data Flow:**
```
Python API / REST → OBSHarness → ConnectionManager → WebSocket → Browser Sources → OBS
```

### Key Patterns

**Mountable Sub-App**: The harness is designed to be mounted in a larger FastAPI application:
```python
main_app.mount("/obs", create_app())
harness = obs_app.state.harness  # Access the control API
```

**WebSocket Protocol**: JSON commands for control, binary frames for audio streaming:
- Server→Browser: `{"action": "play"|"stop"|"text"|"stream_start"|...}`
- Browser→Server: `{"event": "ended"|"stream_ended"|"text_complete"|"error"}`

**Audio Streaming**: For real-time audio (TTS), use PCM16 format:
```python
await harness.stream_start(channel, sample_rate=24000, channels=1)
await harness.stream_audio(channel, pcm_bytes)
await harness.stream_end(channel)
```

### Frontend

- `static/js/channel.js` - Browser source handler (audio + text + streaming via Web Audio API)
- `static/js/text-animator.js` - Canvas-based text animations (typewriter, fade, slide, bounce, wave)
- `static/js/dashboard.js` - Dashboard WebSocket client

### Database

SQLite via SQLModel (async with aiosqlite). Tables: `Channel`, `TextPreset`, `PlaybackLog`.
