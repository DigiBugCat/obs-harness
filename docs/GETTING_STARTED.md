# Getting Started with OBS Harness

This guide will walk you through setting up OBS Harness to add AI-powered characters with voice and text overlays to your stream.

## What You'll Need

- **OBS Studio** (or compatible streaming software)
- **Python 3.13+** with [uv](https://docs.astral.sh/uv/)
- **ElevenLabs account** - For text-to-speech ([sign up free](https://elevenlabs.io/))
- **OpenRouter account** - For AI chat ([sign up free](https://openrouter.ai/))
- **Twitch account** (optional) - For chat integration

---

## Step 1: Installation

```bash
# Clone the repository
git clone https://github.com/DigiBugCat/obs-harness.git
cd obs-harness

# Install dependencies
uv sync
```

---

## Step 2: Get API Keys

### ElevenLabs (Required for voice)

1. Go to [elevenlabs.io](https://elevenlabs.io/) and sign up
2. Click your profile icon → **Profile + API key**
3. Copy your API key

### OpenRouter (Required for AI chat)

1. Go to [openrouter.ai](https://openrouter.ai/) and sign up
2. Go to **Keys** in the sidebar
3. Create a new key and copy it

---

## Step 3: Configure Environment

Create a `.env` file in the project root:

```bash
# Required
ELEVENLABS_API_KEY=sk_your_elevenlabs_key_here
OPENROUTER_API_KEY=sk-or-your_openrouter_key_here
```

---

## Step 4: Start the Server

```bash
uv run obs-harness
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8080
```

Open **http://localhost:8080** in your browser to access the dashboard.

---

## Step 5: Create Your First Character

1. In the dashboard, click **+ New Character**
2. Fill in the basics:
   - **Name**: `MyCharacter` (this becomes the channel URL)
   - **Voice**: Select from your ElevenLabs voices
   - **System Prompt**: Describe the character's personality, e.g.:
     ```
     You are a friendly stream assistant. Keep responses short and entertaining.
     Be playful and engage with chat. Use 1-2 sentences max.
     ```
3. Click **Create**

---

## Step 6: Set Up OBS Browser Source

1. In OBS, add a new **Browser Source**
2. Set the URL to:
   ```
   http://localhost:8080/channel/MyCharacter
   ```
   (Replace `MyCharacter` with your character's name)
3. Set dimensions: **1920 x 1080** (or match your canvas)
4. Check **"Shutdown source when not visible"** (optional, saves resources)

---

## Step 7: Test Your Character

Back in the dashboard:

1. Click your character to open it
2. Click the **Chat** button
3. Type a message like "Hello! Introduce yourself"
4. Click **Send**

You should see:
- Text appearing in your OBS browser source
- Audio playing through OBS
- The AI response in the chat window

---

## Step 8: Twitch Chat Integration (Optional)

Let your character see and respond to Twitch chat:

1. Go to **http://localhost:8080/twitch**
2. Click **Sign in with Twitch**
3. Authorize the app
4. Enter your channel name

Then in your character settings:
- Enable **Twitch Chat**
- Set the time window (how many seconds of chat to include)

Now when you chat with your character, it will see recent Twitch messages!

---

## Common Use Cases

### Stream Alerts / Reactions

Use the **Speak** button to make your character say specific things:
```
"Thanks for the sub!"
"Welcome to the stream!"
```

### Interactive Chat Bot

With Twitch integration enabled, viewers can trigger responses:
1. Set up a chat bot or StreamElements command
2. Have it call the API:
   ```bash
   curl -X POST http://localhost:8080/api/characters/MyCharacter/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "A viewer asked: what game are we playing?"}'
   ```

### Multiple Characters

Create different characters for different purposes:
- **Narrator** - Announces events, reads donations
- **Sidekick** - Reacts to gameplay, jokes with chat
- **Mascot** - Channel mascot with unique personality

Each character gets its own browser source URL.

---

## Customization

### Text Appearance

In character settings, customize:
- Font family and size
- Color and stroke (outline)
- Position on screen
- Animation style (typewriter, fade, slide, etc.)

### Voice Settings

Fine-tune the voice:
- **Stability** - Higher = more consistent, Lower = more expressive
- **Similarity** - How closely to match the original voice
- **Style** - Exaggeration of the voice's style (if supported)
- **Speed** - 0.7x to 1.2x playback speed

### AI Behavior

Adjust in character settings:
- **Model** - Different AI models (Claude, GPT, etc.)
- **Temperature** - Higher = more creative, Lower = more focused
- **Max Tokens** - Limit response length

---

## Troubleshooting

### No audio in OBS

1. Check that the browser source is visible
2. In OBS, right-click the source → **Properties** → Enable audio
3. Check OBS audio mixer - the browser source should show activity

### Character not responding

1. Check the server console for errors
2. Verify API keys are correct in `.env`
3. Make sure the character has a system prompt (required for chat)

### Text not showing

1. Verify browser source dimensions match your canvas
2. Check character text settings (position, color, size)
3. Try the **Speak** button to test basic functionality

### Connection issues

1. Make sure the server is running (`uv run obs-harness`)
2. Check the dashboard shows "Connected" for your character
3. Refresh the OBS browser source

---

## Next Steps

- Read the full [API Reference](API.md) for automation
- Explore the [Text Editor](/editor) for custom animations
- Check out integration examples in the README

---

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/DigiBugCat/obs-harness/issues)
- **API Docs**: http://localhost:8080/docs (when server is running)
