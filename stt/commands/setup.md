---
description: Set up elevenlabs-stt - check environment, install dependencies, configure hotkey
---

# elevenlabs-stt Setup

This skill guides users through setting up elevenlabs-stt by checking prerequisites and installing dependencies.

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
from elevenlabs_stt.config import Config
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
from elevenlabs_stt.config import Config
from elevenlabs_stt.elevenlabs_client import ElevenLabsClient
config = Config.load()
client = ElevenLabsClient(config.get_api_key())
if client.test_connection():
    print('API connection successful!')
else:
    print('API connection failed. Check your API key.')
"
```

### Step 7: Check Microphone Permissions (macOS)

On macOS, the terminal needs microphone permission. Tell the user:
```
If you see a microphone permission prompt, click "Allow".
If recording doesn't work, go to:
System Settings > Privacy & Security > Microphone
and enable your terminal app.
```

### Step 8: Start the Daemon

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_stt.daemon start --background
```

### Step 9: Configure Preferences

Now that the daemon is running, ask the user about their preferences. Use single-select questions.

#### Transcription Mode

Ask which transcription mode they prefer:
- **Batch (Recommended)** - record first, transcribe when finished
- **Streaming (Experimental)** - realtime transcription, text appears as you speak

Save the choice:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_stt.config import Config
config = Config.load()
config.transcription_mode = 'streaming'  # or 'batch'
config.save()
"
```

#### Activation Mode

Ask how they want to activate recording:
- **Toggle (Recommended)** - press hotkey to start, press again to stop
- **Push-to-talk** - hold hotkey while speaking, release to stop

Save the choice:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_stt.config import Config
config = Config.load()
config.activation_mode = 'toggle'  # or 'push-to-talk'
config.save()
"
```

#### Hotkey

Ask if they want to customize the hotkey (default: ctrl+shift+space):
- **Keep default (ctrl+shift+space)** - recommended
- **Customize** - let them type a new hotkey combination

If they customize, save it:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_stt.config import Config
config = Config.load()
config.hotkey = 'USER_HOTKEY_HERE'
config.save()
"
```

#### Sound Effects

Ask if they want audio feedback sounds:
- **Yes (Recommended)** - play sounds when recording starts/stops
- **No** - silent operation

Save the choice:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_stt.config import Config
config = Config.load()
config.sound_effects = True  # or False
config.save()
"
```

### Step 10: Restart Daemon with New Config

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_stt.daemon stop
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_stt.daemon start --background
```

### Success

When setup completes successfully, show the user their configuration:
```
Setup complete!

Your settings:
- Transcription: [streaming/batch]
- Activation: [toggle/push-to-talk]
- Hotkey: [hotkey]
- Sound effects: [on/off]

Press [hotkey] to start recording. Your speech will be transcribed and typed into the active window.

Run /elevenlabs-stt:config anytime to change these settings.
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

**"Permission denied" or Accessibility errors (macOS):**
```
macOS requires Accessibility permission for keyboard input.

1. Open System Settings > Privacy & Security > Accessibility
2. Find your terminal app and enable it
3. Re-run: /elevenlabs-stt:setup
```
