---
description: Start the TTS daemon
---

# Start elevenlabs-tts Daemon

Start the text-to-speech daemon.

## Instructions

When the user runs `/elevenlabs-tts:start`:

### Step 1: Detect Python

Find the working Python command:
```bash
python3 --version 2>/dev/null && echo "USE_PYTHON3" || python --version 2>/dev/null && echo "USE_PYTHON" || echo "NOT_FOUND"
```

- If output contains `USE_PYTHON3`, use `python3` for subsequent commands
- If output contains `USE_PYTHON`, use `python` for subsequent commands
- If output is `NOT_FOUND`, tell user: "Python not found. Please run `/elevenlabs-tts:setup` first."

### Step 2: Check daemon status

Using the detected Python command:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_tts.daemon status
```
(Replace `python3` with `python` if that's what was detected)

### Step 3: Start if not running

If daemon is not running:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_tts.daemon start --background
```

### Step 4: Confirm and show usage

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_tts.daemon status
```

Show usage reminder:
```
elevenlabs-tts daemon started.

Usage:
  Claude's responses will be read aloud automatically.

Hotkeys:
  Toggle auto-read: Ctrl+Shift+T
  Pause/Resume: Ctrl+Shift+P
  Skip current: Ctrl+Shift+S
```
