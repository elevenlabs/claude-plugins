---
description: Set up elevenlabs-tts - check environment, install dependencies, configure voice
---

# elevenlabs-tts Setup

This skill guides users through setting up elevenlabs-tts by checking prerequisites and installing dependencies.

## Instructions

Follow these steps IN ORDER. Do not skip ahead.

### Step 1: Check Python Installation

Run this command to check Python version:

```bash
python3 --version 2>/dev/null || python --version 2>/dev/null || echo "NOT_FOUND"
```

**Evaluate the result:**

- If output is `NOT_FOUND` or command fails: Python is not installed. Go to Step 2.
- If version is 3.9.x or lower: Python is too old. Go to Step 2.
- If version is 3.10 or higher: Python is ready. Skip to Step 3.

### Step 2: Install/Upgrade Python (if needed)

If Python is missing or below 3.10, **run the appropriate installation command**.

**macOS:**

First check if Homebrew is installed:
```bash
command -v brew >/dev/null && echo "brew installed" || echo "brew not installed"
```

If Homebrew is installed, run:
```bash
brew install python@3.12
```

If Homebrew is NOT installed, run:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
Then after Homebrew installs, run `brew install python@3.12`.

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip
```

**Linux (Fedora/RHEL):**
```bash
sudo dnf install -y python3.12 python3-pip
```

**Windows:**

Windows requires manual installation. Tell the user:
- Download Python from: https://www.python.org/downloads/
- Check "Add Python to PATH" during installation
- Restart terminal after installation

After installation completes, **verify** Python is now available:
```bash
python3 --version 2>/dev/null || python --version 2>/dev/null
```

### Step 3: Check for uv or create venv

Check if uv is available:
```bash
command -v uv >/dev/null && echo "uv installed" || echo "uv not installed"
```

If uv is installed, use it for dependency management. If not, create a virtual environment:
```bash
python3 -m venv ${CLAUDE_PLUGIN_ROOT}/.venv
```

### Step 4: Install Dependencies

If uv is available:
```bash
cd ${CLAUDE_PLUGIN_ROOT} && uv sync
```

Otherwise, install with pip:
```bash
${CLAUDE_PLUGIN_ROOT}/.venv/bin/pip install -e ${CLAUDE_PLUGIN_ROOT}
```

### Step 5: Configure ElevenLabs API Key

Open the ElevenLabs API keys page in the user's browser:
```bash
open "https://elevenlabs.io/app/developers/api-keys" 2>/dev/null || xdg-open "https://elevenlabs.io/app/developers/api-keys" 2>/dev/null || start "https://elevenlabs.io/app/developers/api-keys" 2>/dev/null || echo "Please open: https://elevenlabs.io/app/developers/api-keys"
```

Ask the user to paste their ElevenLabs API key from that page.

Once they provide the key, save it to the config:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
config = Config.load()
config.api_key = 'USER_API_KEY_HERE'
config.save()
print('API key saved.')
"
```

Alternatively, they can set the `ELEVENLABS_API_KEY` environment variable.

### Step 6: Test API Connection

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
from elevenlabs_tts.elevenlabs_client import ElevenLabsClient
config = Config.load()
client = ElevenLabsClient(config.get_api_key(), config)
if client.test_connection():
    print('API connection successful!')
else:
    print('API connection failed. Check your API key.')
"
```

### Step 7: Configure Preferences

Now that the API is connected, ask the user about their preferences. Use single-select questions.

#### Voice Selection

Ask if they want to keep the default voice or choose another:
- **Default (Rachel)** - keep the default voice
- **Choose voice** - show available voices

If they want to choose, list available voices:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
from elevenlabs_tts.elevenlabs_client import ElevenLabsClient
config = Config.load()
client = ElevenLabsClient(config.get_api_key(), config)
voices = client.get_voices()
for v in voices[:10]:
    print(f'{v[\"voice_id\"]}: {v[\"name\"]}')
"
```

Save the chosen voice:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
config = Config.load()
config.voice_id = 'VOICE_ID_HERE'
config.save()
"
```

#### Auto-Read Setting

Ask if they want Claude responses read automatically:
- **Yes (Recommended)** - automatically read all Claude responses
- **No** - only read when triggered manually

Save the choice:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
config = Config.load()
config.auto_read = True  # or False
config.save()
"
```

#### Code Block Handling

Ask how to handle code blocks:
- **Skip code blocks (Recommended)** - say "[code block]" instead of reading code
- **Read code blocks** - read code aloud (can be verbose)

Save the choice:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
config = Config.load()
config.skip_code_blocks = True  # or False
config.save()
"
```

### Step 8: Start the Daemon

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_tts.daemon start --background
```

### Success

When setup completes successfully, show the user their configuration:
```
Setup complete!

Your settings:
- Voice: [voice name]
- Auto-read: [on/off]
- Skip code blocks: [yes/no]

Hotkeys:
- Toggle auto-read: Ctrl+Shift+T
- Pause/Resume: Ctrl+Shift+P
- Skip current: Ctrl+Shift+S

Claude's responses will now be read aloud!

Run /elevenlabs-tts:config anytime to change these settings.
```

## Common Errors

**PortAudio errors (audio not working):**

macOS:
```bash
brew install portaudio
```

Linux:
```bash
sudo apt install libportaudio2  # Debian/Ubuntu
sudo dnf install portaudio      # Fedora
```

**No audio player found (Linux):**
```bash
sudo apt install mpv  # or ffmpeg for ffplay
```
