# OBS Audio Harness

Push audio and animated text to OBS via browser sources. Designed as a mountable sub-application for streaming automation.

## Installation

```bash
uv sync
```

## Quick Start

```bash
# Start the server
uv run obs-harness

# With custom options
uv run obs-harness --host 0.0.0.0 --port 8080
```

Then:
1. Open the dashboard: http://localhost:8000/
2. Add Browser Sources in OBS with URL: `http://localhost:8000/channel/{name}`
3. Enable "Control audio via OBS" in browser source settings

## Features

- **Audio Playback**: Play audio files on individual channels
- **Audio Streaming**: Stream audio bytes from Python (TTS, live audio)
- **Text Overlays**: Animated text with typewriter, fade, slide, bounce, wave effects
- **Web Dashboard**: Monitor channels and test controls
- **Text Editor**: Visual editor for creating text animation presets
- **REST API**: Trigger from external services

## Integration

### Mount in a larger FastAPI app

```python
from fastapi import FastAPI
from obs_harness import create_app

main_app = FastAPI()
obs_app = create_app(db_url="sqlite+aiosqlite:///data/app.db")

# Mount under /obs prefix
main_app.mount("/obs", obs_app)

# Access harness from main app
harness = obs_app.state.harness
await harness.play("alice", "greeting.wav")
```

### Stream TTS audio

```python
harness = obs_app.state.harness

# Start stream
await harness.stream_start("alice", sample_rate=24000, channels=1)

# Stream audio chunks
async for chunk in tts_engine.generate("Hello world"):
    await harness.stream_audio("alice", chunk)

# End stream
await harness.stream_end("alice")
```

### REST API

```bash
# Play audio
curl -X POST http://localhost:8000/api/channel/alice/play \
  -H "Content-Type: application/json" \
  -d '{"file": "greeting.wav", "volume": 0.8}'

# Show text
curl -X POST http://localhost:8000/api/channel/alice/text \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello!", "style": "typewriter", "duration": 3000}'
```

## OBS Setup

1. Add Browser Source
2. URL: `http://localhost:8000/channel/{name}`
3. Width: 1920, Height: 1080
4. Check "Control audio via OBS"
5. Rename source to channel name

## API Documentation

Once running, visit http://localhost:8000/docs for interactive API docs.
