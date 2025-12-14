# OBS Harness API Reference

This document describes the REST API endpoints for controlling audio and text overlays in OBS.

**Base URL:** `http://localhost:8080`

**Interactive Docs:** Visit `/docs` for Swagger UI or `/redoc` for ReDoc.

---

## Table of Contents

- [Characters](#characters)
  - [List Characters](#list-characters)
  - [Create Character](#create-character)
  - [Get Character](#get-character)
  - [Update Character](#update-character)
  - [Delete Character](#delete-character)
  - [Speak (TTS)](#speak-tts)
  - [Chat (AI + TTS)](#chat-ai--tts)
  - [Stop Generation](#stop-generation)
  - [Get Memory](#get-memory)
  - [Clear Memory](#clear-memory)
- [Twitch Integration](#twitch-integration)
  - [Get Status](#get-twitch-status)
  - [Save Token](#save-twitch-token)
  - [Set Channel](#set-twitch-channel)
  - [Disconnect](#disconnect-twitch)
  - [Get Chat](#get-twitch-chat)
- [External Services](#external-services)
  - [ElevenLabs Voices](#elevenlabs-voices)
  - [ElevenLabs Models](#elevenlabs-models)
  - [OpenRouter Providers](#openrouter-providers)
- [Text Presets](#text-presets)
- [History](#history)
- [WebSocket Protocol](#websocket-protocol)

---

## Characters

Characters are the core entities - each has a voice, text styling, and optional AI personality.

### List Characters

```
GET /api/characters
```

Returns all characters with their connection status.

**Response:**
```json
[
  {
    "id": 1,
    "name": "Timmy",
    "description": "A friendly AI assistant",
    "elevenlabs_voice_id": "pqHfZKP75CvOlQylNhV4",
    "model": "anthropic/claude-sonnet-4.5",
    "memory_enabled": true,
    "connected": true,
    "playing": false,
    "streaming": false
  }
]
```

### Create Character

```
POST /api/characters
```

**Request Body:**
```json
{
  "name": "Timmy",
  "elevenlabs_voice_id": "pqHfZKP75CvOlQylNhV4",
  "description": "A friendly AI assistant",
  "system_prompt": "You are Timmy, a cheerful assistant...",
  "model": "anthropic/claude-sonnet-4.5",
  "voice_stability": 0.5,
  "voice_similarity_boost": 0.75,
  "voice_style": 0.0,
  "voice_speed": 1.0,
  "memory_enabled": true,
  "twitch_chat_enabled": false
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | **required** | Unique character name |
| `elevenlabs_voice_id` | string | **required** | ElevenLabs voice ID |
| `description` | string | null | Character description |
| `system_prompt` | string | null | AI personality prompt (required for chat) |
| `model` | string | `anthropic/claude-sonnet-4.5` | OpenRouter model ID |
| `provider` | string | null | OpenRouter provider routing |
| `temperature` | float | 0.7 | LLM temperature (0-2) |
| `max_tokens` | int | 1024 | Max response tokens |
| `voice_stability` | float | 0.5 | Voice stability (0-1) |
| `voice_similarity_boost` | float | 0.75 | Voice clarity (0-1) |
| `voice_style` | float | 0.0 | Voice style exaggeration (0-1) |
| `voice_speed` | float | 1.0 | Speech speed (0.7-1.2) |
| `memory_enabled` | bool | false | Enable conversation memory |
| `persist_memory` | bool | false | Save memory to database |
| `twitch_chat_enabled` | bool | false | Inject Twitch chat into AI context |

### Get Character

```
GET /api/characters/{name}
```

### Update Character

```
PUT /api/characters/{name}
```

All fields are optional - only include fields you want to update.

### Delete Character

```
DELETE /api/characters/{name}
```

---

### Speak (TTS)

Directly speak text using the character's voice (no AI).

```
POST /api/characters/{name}/speak
```

**Request Body:**
```json
{
  "text": "Hello, world!",
  "show_text": true
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | string | **required** | Text to speak |
| `show_text` | bool | true | Show text overlay in OBS |

**Response:**
```json
{
  "success": true,
  "character": "Timmy"
}
```

---

### Chat (AI + TTS)

Send a message to the character's AI and stream the response through TTS.

```
POST /api/characters/{name}/chat
```

**Request Body:**
```json
{
  "message": "Tell me a joke!",
  "show_text": true,
  "twitch_chat_seconds": 60
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `message` | string | **required** | User message |
| `show_text` | bool | true | Show text overlay in OBS |
| `twitch_chat_seconds` | int | null | Override Twitch context window (0 = disabled, null = use character setting) |

**Response:**
```json
{
  "success": true,
  "character": "Timmy",
  "response_text": "Why did the chicken cross the road? To get to the other side!",
  "twitch_chat_context": "[viewer1]: lol\n[viewer2]: nice"
}
```

**Note:** Requires `system_prompt` to be set on the character.

---

### Stop Generation

Stop any active speak/chat generation for a character.

```
POST /api/characters/{name}/stop
```

**Response:**
```json
{
  "success": true,
  "was_active": true
}
```

---

### Get Memory

Get the conversation history for a character.

```
GET /api/characters/{name}/memory
```

**Response:**
```json
{
  "character": "Timmy",
  "message_count": 4,
  "messages": [
    {"role": "context", "content": "[viewer1]: hi\n[viewer2]: hello"},
    {"role": "user", "content": "Tell me a joke"},
    {"role": "assistant", "content": "Why did the chicken...", "interrupted": false},
    {"role": "user", "content": "Another one!"}
  ]
}
```

### Clear Memory

```
DELETE /api/characters/{name}/memory
```

---

## Twitch Integration

Connect to Twitch chat to give characters awareness of viewer conversations.

### Get Twitch Status

```
GET /api/twitch/status
```

**Response:**
```json
{
  "connected": true,
  "channel": "your_channel"
}
```

### Save Twitch Token

Called after OAuth flow completes.

```
POST /api/twitch/token
```

**Request Body:**
```json
{
  "access_token": "oauth_token_here",
  "channel": "your_channel"
}
```

### Set Twitch Channel

Change the channel to listen to.

```
POST /api/twitch/channel
```

**Request Body:**
```json
{
  "channel": "new_channel"
}
```

### Disconnect Twitch

```
POST /api/twitch/disconnect
```

### Get Twitch Chat

Get recent chat messages (for debugging).

```
GET /api/twitch/chat?seconds=60
```

---

## External Services

### ElevenLabs Voices

```
GET /api/elevenlabs/voices
```

Returns available voices from your ElevenLabs account.

### ElevenLabs Models

```
GET /api/elevenlabs/models
```

Returns available TTS models.

### Get Voice Details

```
GET /api/elevenlabs/voices/{voice_id}
```

### OpenRouter Providers

Get available providers for a model.

```
GET /api/openrouter/models/{model}/providers
```

**Example:**
```
GET /api/openrouter/models/anthropic/claude-sonnet-4.5/providers
```

---

## Text Presets

Saved text styling configurations.

### List Presets

```
GET /api/presets
```

### Create Preset

```
POST /api/presets
```

**Request Body:**
```json
{
  "name": "Big Red",
  "style": "typewriter",
  "font_family": "Arial",
  "font_size": 72,
  "color": "#ff0000",
  "stroke_color": "#000000",
  "stroke_width": 2,
  "position_x": 0.5,
  "position_y": 0.5,
  "duration": 5000
}
```

### Delete Preset

```
DELETE /api/presets/{preset_id}
```

---

## History

Get recent playback events.

```
GET /api/history?limit=50
```

**Response:**
```json
[
  {
    "id": 1,
    "channel": "Timmy",
    "content": "Hello world",
    "content_type": "stream",
    "timestamp": "2024-01-15T10:30:00Z"
  }
]
```

---

## WebSocket Protocol

Browser sources connect via WebSocket to receive audio and text commands.

### Endpoints

- `/ws/{channel}` - Browser source connection (for OBS)
- `/ws/dashboard` - Dashboard status updates

### Server → Browser Messages

**Audio Playback:**
```json
{"action": "play", "url": "/audio/file.mp3", "volume": 1.0}
{"action": "stop"}
```

**Audio Streaming (TTS):**
```json
{"action": "stream_start", "sample_rate": 24000, "channels": 1}
// Binary frames: raw PCM audio bytes
{"action": "stream_end"}
{"action": "stop_stream"}
```

**Text Overlay:**
```json
{"action": "text", "text": "Hello!", "style": "typewriter", "duration": 3000}
{"action": "clear_text"}
```

**Text Streaming (synced with TTS):**
```json
{"action": "text_stream_start", "font_family": "Arial", "font_size": 48, "color": "#ffffff"}
{"action": "word_timing", "words": [{"word": "Hello", "start": 0.0, "end": 0.5}]}
{"action": "text_stream_end"}
```

### Browser → Server Messages

```json
{"event": "ended"}           // Audio file finished
{"event": "stream_ended"}    // Audio stream finished
{"event": "stream_stopped", "playback_time": 2.5, "spoken_text": "Hello world", "word_count": 2}
{"event": "text_complete"}   // Text animation finished
{"event": "error", "message": "..."}
```

---

## Error Responses

All endpoints return standard HTTP error codes:

- `400` - Bad request (invalid parameters)
- `404` - Resource not found
- `422` - Validation error (see `detail` for specifics)
- `500` - Server error

**Validation Error Format:**
```json
{
  "detail": [
    {
      "loc": ["body", "voice_speed"],
      "msg": "ensure this value is less than or equal to 1.2",
      "type": "value_error.number.not_le"
    }
  ]
}
```
