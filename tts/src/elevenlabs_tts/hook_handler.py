"""Handler for Claude Code hooks."""

from __future__ import annotations

import argparse
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
    """Main entry point for hook handler."""
    logging.basicConfig(
        level=logging.DEBUG if "--debug" in sys.argv else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="ElevenLabs TTS hook handler")
    parser.add_argument("event", choices=["stop"], help="Hook event type")
    parser.add_argument(
        "--transcript-path",
        required=True,
        help="Path to transcript JSONL file",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    try:
        if args.event == "stop":
            handle_stop_hook(args.transcript_path)
        return 0
    except Exception as e:
        logger.error("Hook handler error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
