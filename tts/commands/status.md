---
description: Show daemon status and configuration
---

# elevenlabs-tts Status

Show daemon status and current configuration.

## Instructions

When the user runs `/elevenlabs-tts:status`:

### Step 1: Detect Python

Find the working Python command:
```bash
python3 --version 2>/dev/null && echo "USE_PYTHON3" || python --version 2>/dev/null && echo "USE_PYTHON" || echo "NOT_FOUND"
```

- If output contains `USE_PYTHON3`, use `python3` for subsequent commands
- If output contains `USE_PYTHON`, use `python` for subsequent commands
- If output is `NOT_FOUND`, tell user: "Python not found. Please run `/elevenlabs-tts:setup` first."

### Step 2: Show status

Using the detected Python command:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_tts.daemon status
```
(Replace `python3` with `python` if that's what was detected)

### Example Output
```
TTS daemon is running (PID 12345)
Auto-read: enabled
Voice: 21m00Tcm4TlvDq8ikWAM
Toggle hotkey: ctrl+shift+t
Pause hotkey: ctrl+shift+p
Skip hotkey: ctrl+shift+s
```
