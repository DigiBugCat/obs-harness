# OBS Harness

Push audio and animated text to OBS via browser sources. Features AI-powered characters with text-to-speech and optional Twitch chat awareness.

## Features

- **Audio Playback** - Play audio files or stream live audio to browser sources
- **Text Overlays** - Animated text with typewriter, fade, slide, bounce, and wave effects
- **AI Characters** - Persistent characters with LLM chat and TTS voice responses
- **Twitch Integration** - Characters can read and respond to live Twitch chat
- **Web Dashboard** - Monitor channels, manage characters, and test controls
- **Text Editor** - Visual editor for creating text animation presets
- **REST API** - Trigger playback and chat from external services
- **Mountable** - Designed to integrate into larger FastAPI applications

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- OBS Studio with Browser Source support

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/obs-harness.git
   cd obs-harness
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Create environment file**
   ```bash
   cp .env.example .env
   # Or create manually:
   echo "ELEVENLABS_API_KEY=your_key_here" > .env
   echo "OPENROUTER_API_KEY=your_key_here" >> .env
   ```

4. **Get API keys**
   - [ElevenLabs](https://elevenlabs.io/) - For text-to-speech (required for voice features)
   - [OpenRouter](https://openrouter.ai/) - For LLM chat completions (required for AI chat)

## Environment Variables

Create a `.env` file in the project root:

```env
# Required for TTS
ELEVENLABS_API_KEY=sk_...

# Required for AI chat
OPENROUTER_API_KEY=sk-or-...

# Optional - defaults to public client ID
TWITCH_CLIENT_ID=your_twitch_client_id
```

## Quick Start

1. **Start the server**
   ```bash
   uv run obs-harness
   ```

2. **Open the dashboard**

   Navigate to http://localhost:8080/

3. **Create a character**

   Use the dashboard to create a character with:
   - Name (used as channel identifier)
   - ElevenLabs voice ID
   - OpenRouter model (e.g., `anthropic/claude-3.5-sonnet`)
   - System prompt for AI personality

4. **Add browser source in OBS**

   See [OBS Setup](#obs-setup) below.

5. **Test it out**

   Use the dashboard controls or API to trigger speech and text.

## CLI Options

```bash
uv run obs-harness [OPTIONS]

Options:
  --host TEXT       Host to bind to (default: 127.0.0.1)
  --port INTEGER    Port to bind to (default: 8080)
  --db TEXT         Database URL (default: sqlite+aiosqlite:///obs_harness.db)
  --static-dir PATH Path to static files directory
  --reload          Enable auto-reload for development
```

**Examples:**
```bash
# Development with auto-reload
uv run obs-harness --reload

# Accessible from network
uv run obs-harness --host 0.0.0.0 --port 8080

# Custom database location
uv run obs-harness --db sqlite+aiosqlite:///data/myapp.db
```

## OBS Setup

1. **Add a Browser Source**
   - Sources panel → Add → Browser

2. **Configure the source**
   - URL: `http://localhost:8080/channel/{character_name}`
   - Width: `1920`
   - Height: `1080`
   - Check **"Control audio via OBS"** (important!)

3. **Position and size**
   - Resize/position the source as needed for your scene
   - Audio will play through OBS audio mixer

4. **Multiple characters**
   - Add separate browser sources for each character
   - Each uses a different channel URL

## Web Pages

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Main control panel for characters and channels |
| Channel | `/channel/{name}` | Browser source endpoint for OBS |
| Editor | `/editor` | Visual text animation preset editor |
| Twitch | `/twitch` | Twitch OAuth setup and configuration |
| API Docs | `/docs` | Interactive API documentation |

## Character System

Characters are persistent entities that combine voice, text styling, and AI configuration.

### Creating Characters

Use the dashboard or API to create characters with:
- **name** - Unique identifier (used in channel URLs)
- **voice_id** - ElevenLabs voice ID
- **model** - OpenRouter model ID (e.g., `anthropic/claude-3.5-sonnet`)
- **system_prompt** - AI personality and instructions
- **twitch_chat_enabled** - Whether to include Twitch chat in AI context

### Character Endpoints

```bash
# Direct TTS (no AI)
POST /api/characters/{name}/speak
{"text": "Hello, world!"}

# AI chat with TTS response
POST /api/characters/{name}/chat
{"message": "Tell me a joke"}

# Update character
PUT /api/characters/{name}
{"system_prompt": "You are a pirate...", "model": "anthropic/claude-3.5-sonnet"}
```

## Twitch Integration

Characters can "read" live Twitch chat and incorporate it into their AI responses.

### Setup

1. Navigate to `/twitch` in your browser
2. Click "Connect with Twitch" to authorize
3. Enter the channel name to monitor
4. Enable `twitch_chat_enabled` on characters that should see chat

### How It Works

- Recent chat messages are stored in a ring buffer
- When a character with `twitch_chat_enabled` receives a chat request, recent messages are injected into the system prompt
- The AI can then reference or respond to chat activity

## API Examples

### Play Audio File

```bash
curl -X POST http://localhost:8080/api/channel/alice/play \
  -H "Content-Type: application/json" \
  -d '{"file": "greeting.wav", "volume": 0.8}'
```

### Show Text Overlay

```bash
curl -X POST http://localhost:8080/api/channel/alice/text \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello!",
    "style": "typewriter",
    "duration": 3000
  }'
```

### Character Speech (TTS)

```bash
curl -X POST http://localhost:8080/api/characters/alice/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, I am Alice!"}'
```

### AI Chat

```bash
curl -X POST http://localhost:8080/api/characters/alice/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What do you think about the weather?"}'
```

## Integration

### Mount in a Larger FastAPI App

```python
from fastapi import FastAPI
from obs_harness import create_app

main_app = FastAPI()
obs_app = create_app(db_url="sqlite+aiosqlite:///data/app.db")

# Mount under /obs prefix
main_app.mount("/obs", obs_app)

# Access the harness API
harness = obs_app.state.harness
```

### Programmatic Audio Streaming

```python
harness = obs_app.state.harness

# Start a stream
await harness.stream_start("alice", sample_rate=24000, channels=1)

# Stream PCM16 audio chunks
async for chunk in tts_engine.generate("Hello world"):
    await harness.stream_audio("alice", chunk)

# End the stream
await harness.stream_end("alice")
```

### Programmatic Text Display

```python
harness = obs_app.state.harness

# Show text with animation
await harness.text(
    channel="alice",
    text="Breaking news!",
    style="slide",
    duration=5000
)

# Clear text
await harness.clear_text("alice")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        OBS Harness                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────┐    ┌─────────────┐    ┌──────────────────────┐   │
│  │ REST API │───>│ OBSHarness  │───>│ ConnectionManager    │   │
│  └──────────┘    └─────────────┘    │ (WebSocket Hub)      │   │
│                                     └──────────┬───────────┘   │
│  ┌──────────┐    ┌─────────────┐              │               │
│  │ Chat API │───>│ChatPipeline │              ▼               │
│  └──────────┘    │ LLM → TTS   │    ┌──────────────────────┐   │
│                  └──────┬──────┘    │ Browser Sources      │   │
│                         │           │ (channel.html)       │   │
│                         └──────────>│ - Web Audio API      │   │
│                                     │ - Canvas Text        │   │
│  ┌──────────┐                       └──────────────────────┘   │
│  │ Twitch   │──> Chat Buffer ──> AI System Prompt              │
│  └──────────┘                                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                     ┌────────────────┐
                     │   OBS Studio   │
                     │ Browser Source │
                     └────────────────┘
```

## Text Animation Styles

| Style | Description |
|-------|-------------|
| `typewriter` | Characters appear one at a time |
| `fade` | Text fades in |
| `slide` | Text slides in from a direction |
| `bounce` | Text bounces into view |
| `wave` | Characters animate in a wave pattern |

Use the `/editor` page to preview and customize text animations.

## Database

SQLite database with the following tables:
- `Character` - AI character configurations
- `TextPreset` - Saved text animation presets
- `PlaybackLog` - History of audio/text playback
- `TwitchConfig` - Twitch OAuth tokens and channel settings

Database is created automatically on first run.

## Development

```bash
# Run with auto-reload
uv run obs-harness --reload

# Run directly with Python
uv run python -m obs_harness
```

## License

MIT
