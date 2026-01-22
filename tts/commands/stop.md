---
description: Stop the TTS daemon
---

# Stop elevenlabs-tts Daemon

Stop the text-to-speech daemon.

## Instructions

When the user runs `/elevenlabs-tts:stop`:

### Step 1: Detect Python

Find the working Python command:
```bash
python3 --version 2>/dev/null && echo "USE_PYTHON3" || python --version 2>/dev/null && echo "USE_PYTHON" || echo "NOT_FOUND"
```

- If output contains `USE_PYTHON3`, use `python3` for subsequent commands
- If output contains `USE_PYTHON`, use `python` for subsequent commands
- If output is `NOT_FOUND`, tell user: "Python not found. Please run `/elevenlabs-tts:setup` first."

### Step 2: Stop the daemon

Using the detected Python command:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_tts.daemon stop
```
(Replace `python3` with `python` if that's what was detected)

### Step 3: Confirm status

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_tts.daemon status
```

### Step 4: Show message

```
elevenlabs-tts daemon stopped.

To start again: /elevenlabs-tts:start
```
