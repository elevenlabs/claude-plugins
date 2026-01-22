"""Handler for Claude Code hooks."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from elevenlabs_tts.config import Config
from elevenlabs_tts.ipc import IpcClient, get_socket_path
from elevenlabs_tts.transcript_parser import get_last_assistant_message

logger = logging.getLogger(__name__)


def handle_stop_hook(transcript_path: str) -> None:
    """Handle the Stop hook - extract text and send to daemon.

    Args:
        transcript_path: Path to the transcript JSONL file.
    """
    config = Config.load()

    if not config.auto_read:
        logger.debug("Auto-read disabled, skipping TTS")
        return

    # Parse transcript to get Claude's last response
    text = get_last_assistant_message(Path(transcript_path))
    if not text:
        logger.debug("No assistant message found in transcript")
        return

    # Send to daemon via IPC
    socket_path = get_socket_path()

    success = IpcClient.send(socket_path, {"type": "speak", "text": text})
    if success:
        logger.debug("Text sent to TTS daemon")
    else:
        logger.warning("Failed to send text to TTS daemon")


def main() -> int:
    """Main entry point for hook handler.

    Hook receives JSON via stdin with format:
    {
        "session_id": "...",
        "transcript_path": "~/.claude/projects/.../xxx.jsonl",
        "hook_event_name": "Stop",
        ...
    }
    """
    logging.basicConfig(
        level=logging.DEBUG if "--debug" in sys.argv else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    try:
        # Read hook data from stdin
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            logger.error("No input received from stdin")
            return 1

        hook_data = json.loads(stdin_data)
        transcript_path = hook_data.get("transcript_path", "")

        if not transcript_path:
            logger.error("No transcript_path in hook data")
            return 1

        # Expand ~ in path
        transcript_path = str(Path(transcript_path).expanduser())

        handle_stop_hook(transcript_path)
        return 0
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON from stdin: %s", e)
        return 1
    except Exception as e:
        logger.error("Hook handler error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
