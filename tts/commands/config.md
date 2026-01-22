---
description: Configure elevenlabs-tts settings
---

# elevenlabs-tts Configuration

Configure text-to-speech settings.

## Instructions

When the user runs `/elevenlabs-tts:config`:

### Step 1: Detect Python

Find the working Python command:
```bash
python3 --version 2>/dev/null && echo "USE_PYTHON3" || python --version 2>/dev/null && echo "USE_PYTHON" || echo "NOT_FOUND"
```

### Step 2: Show Current Configuration

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
config = Config.load()
print('Current Configuration:')
print(f'  Voice ID: {config.voice_id}')
print(f'  Model: {config.model_id}')
print(f'  Speed: {config.speed}')
print(f'  Auto-read: {config.auto_read}')
print(f'  Skip code blocks: {config.skip_code_blocks}')
print(f'  Max text length: {config.max_text_length}')
print(f'  Sound effects: {config.sound_effects}')
print(f'  Toggle hotkey: {config.hotkey_toggle}')
print(f'  Pause hotkey: {config.hotkey_pause}')
print(f'  Skip hotkey: {config.hotkey_skip}')
"
```

### Step 3: Ask What to Configure

Ask the user what they want to configure:
- **Voice** - change the TTS voice
- **Speed** - adjust speech speed (0.5-2.0)
- **Auto-read** - toggle automatic reading
- **Code blocks** - toggle code block handling
- **Hotkeys** - change hotkey bindings
- **Done** - exit configuration

### Configuration Options

#### Change Voice

List available voices:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
from elevenlabs_tts.elevenlabs_client import ElevenLabsClient
config = Config.load()
client = ElevenLabsClient(config.get_api_key(), config)
voices = client.get_voices()
for v in voices[:15]:
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
print('Voice updated.')
"
```

#### Change Speed

Ask for speed value (0.5-2.0, default 1.0):
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
config = Config.load()
config.speed = 1.0  # User's value here
config.save()
print('Speed updated.')
"
```

#### Toggle Auto-Read

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
config = Config.load()
config.auto_read = not config.auto_read
config.save()
print(f'Auto-read: {\"enabled\" if config.auto_read else \"disabled\"}')
"
```

#### Toggle Code Blocks

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
config = Config.load()
config.skip_code_blocks = not config.skip_code_blocks
config.save()
print(f'Skip code blocks: {config.skip_code_blocks}')
"
```

#### Change Hotkeys

Ask which hotkey to change and the new value:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_tts.config import Config
config = Config.load()
config.hotkey_toggle = 'NEW_HOTKEY'  # e.g., 'ctrl+shift+t'
config.save()
print('Hotkey updated.')
"
```

### Step 4: Restart Daemon

After configuration changes, restart the daemon:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_tts.daemon restart --background
```

Show confirmation:
```
Configuration updated and daemon restarted.
```
