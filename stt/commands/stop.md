---
description: Stop the STT daemon
---

# Stop elevenlabs-stt Daemon

Stop the speech-to-text daemon.

## Instructions

When the user runs `/elevenlabs-stt:stop`:

### Step 1: Detect Python

Find the working Python command:
```bash
python3 --version 2>/dev/null && echo "USE_PYTHON3" || python --version 2>/dev/null && echo "USE_PYTHON" || echo "NOT_FOUND"
```

- If output contains `USE_PYTHON3`, use `python3` for subsequent commands
- If output contains `USE_PYTHON`, use `python` for subsequent commands
- If output is `NOT_FOUND`, tell user: "Python not found. Please run `/elevenlabs-stt:setup` first."

### Step 2: Stop the daemon

Using the detected Python command:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_stt.daemon stop
```
(Replace `python3` with `python` if that's what was detected)

### Step 3: Confirm status

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_stt.daemon status
```

### Step 4: Show message

```
elevenlabs-stt daemon stopped.

To start again: /elevenlabs-stt:start
```
