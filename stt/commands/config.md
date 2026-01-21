---
description: Configure elevenlabs-stt settings
---

# Configure elevenlabs-stt

Change elevenlabs-stt settings.

## Instructions

When the user runs `/elevenlabs-stt:config`:

### Step 1: Detect Python

Find the working Python command:
```bash
python3 --version 2>/dev/null && echo "USE_PYTHON3" || python --version 2>/dev/null && echo "USE_PYTHON" || echo "NOT_FOUND"
```

- If output contains `USE_PYTHON3`, use `python3` for subsequent commands
- If output contains `USE_PYTHON`, use `python` for subsequent commands
- If output is `NOT_FOUND`, tell user: "Python not found. Please run `/elevenlabs-stt:setup` first."

### Step 2: Show current configuration

Using the detected Python command:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_stt.config import Config
config = Config.load()
print('Current Configuration:')
print(f'  Hotkey: {config.hotkey}')
print(f'  Transcription mode: {config.transcription_mode}')
print(f'  Activation mode: {config.activation_mode}')
print(f'  Model: {\"scribe_v2_realtime\" if config.transcription_mode == \"streaming\" else config.model_id}')
print(f'  Language: {config.language_code or \"auto-detect\"}')
print(f'  Output: {config.output_mode}')
print(f'  Sound effects: {config.sound_effects}')
print(f'  Max recording: {config.max_recording_seconds}s')
print(f'  API key: {\"configured\" if config.get_api_key() else \"not configured\"}')
"
```
(Replace `python3` with `python` if that's what was detected)

### Step 3: Ask user what to change

Ask the user which ONE setting they want to change. Use a single-select question (not multi-select). When they select an option, immediately proceed to that setting's configuration.

Options to offer:
- Transcription mode - switch between streaming (realtime) or batch
- Activation mode - switch between toggle or push-to-talk
- Hotkey - change the key combination
- Language - set language for transcription
- Sound effects - turn on or off
- API key - update ElevenLabs API key

#### Transcription Mode Selection

When user selects Transcription mode, offer these options:
- Streaming (Recommended) - realtime transcription, text appears as you speak
- Batch - record first, transcribe when finished

#### Activation Mode Selection

When user selects Activation mode, offer these options:
- Toggle (Recommended) - press hotkey to start, press again to stop
- Push-to-talk - hold hotkey while speaking, release to stop

#### Language Selection

When user selects Language, offer these options:
- Auto-detect (empty string) - automatically detect language
- English ("en")
- Spanish ("es")
- German ("de")
- Other - let user type a language code (e.g., "fr", "ja", "zh")

### Step 4: Update configuration

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -c "
from elevenlabs_stt.config import Config
config = Config.load()
# Update fields as needed
# config.hotkey = 'new_hotkey'
# config.transcription_mode = 'streaming'
# config.activation_mode = 'toggle'
# config.language_code = 'en'
config.save()
print('Configuration saved.')
"
```

### Step 5: Restart daemon if running

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_stt.daemon stop
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/exec.py -m elevenlabs_stt.daemon start --background
```

## Configuration Options

| Option | Values | Description |
|--------|--------|-------------|
| hotkey | e.g., "ctrl+shift+space" | Key combination to trigger recording |
| transcription_mode | "streaming", "batch" | Realtime streaming vs record-then-transcribe |
| activation_mode | "toggle", "push-to-talk" | Press to start/stop vs hold to record |
| model_id | "scribe_v2" / "scribe_v2_realtime" | ElevenLabs STT model (auto-selected based on transcription mode) |
| language_code | e.g., "en", "" | Language code (empty = auto-detect) |
| output_mode | "auto", "injection", "clipboard" | How to output text |
| sound_effects | true, false | Play audio feedback |
| max_recording_seconds | 1-600 | Maximum recording duration |
| streaming_vad_mode | true, false | Use VAD auto-commit in streaming mode |
| streaming_vad_silence_secs | 0.5-5.0 | Silence threshold for VAD commit |
| api_key | string | ElevenLabs API key |

## Mode Descriptions

### Transcription Modes
- **streaming**: Realtime transcription via WebSocket. Text appears as you speak. VAD auto-commits on silence.
- **batch**: Record audio first, then transcribe when recording stops. Better for noisy environments.

### Activation Modes
- **toggle**: Press hotkey once to start recording, press again to stop.
- **push-to-talk**: Hold the hotkey while speaking, release to stop.
