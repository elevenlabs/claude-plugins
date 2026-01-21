---
description: Start the STT daemon
---

# Start elevenlabs-stt Daemon

Start the speech-to-text daemon.

## Instructions

When the user runs `/elevenlabs-stt:start`:

### Step 1: Detect Python

Find the working Python command:
```bash
python3 --version 2>/dev/null && echo "USE_PYTHON3" || python --version 2>/dev/null && echo "USE_PYTHON" || echo "NOT_FOUND"
```

- If output contains `USE_PYTHON3`, use `python3` for subsequent commands
- If output contains `USE_PYTHON`, use `python` for subsequent commands
- If output is `NOT_FOUND`, tell user: "Python not found. Please run `/elevenlabs-stt:setup` first."

### Step 2: Check daemon status

Using the detected Python command:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_stt.daemon status
```
(Replace `python3` with `python` if that's what was detected)

### Step 3: Start if not running

If daemon is not running:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_stt.daemon start --background
```

### Step 4: Confirm and show usage

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_stt.daemon status
```

Show usage reminder:
```
elevenlabs-stt daemon started.

Usage:
  Default hotkey: Ctrl+Shift+Space
  Toggle mode: press to start, press again to stop
  Push-to-talk mode: hold to record, release to stop

Speech is transcribed using ElevenLabs API (scribe_v2 model).
```
