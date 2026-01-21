# ElevenLabs STT Skill for Claude Code

Speech-to-text input for Claude Code using ElevenLabs API.

## Installation

1. Add the marketplace: `/plugin marketplace add elevenlabs/claude-plugins`
2. Install the plugin: `/plugin install elevenlabs-stt`
3. Allow microphone access when prompted

## Setup

1. Run `/elevenlabs-stt:setup` to install dependencies and configure API key
2. Run `/elevenlabs-stt:start` to start the daemon
3. Press `Ctrl+Shift+Space` to start recording, press again to stop

## Configuration

Configuration is stored at `~/.claude/plugins/elevenlabs-stt/config.toml`.

The API key can be set via:
- `ELEVENLABS_API_KEY` environment variable
- Config file

## Commands

- `/elevenlabs-stt:setup` - Initial setup
- `/elevenlabs-stt:start` - Start daemon
- `/elevenlabs-stt:stop` - Stop daemon
- `/elevenlabs-stt:status` - Show status
- `/elevenlabs-stt:config` - Configure settings
