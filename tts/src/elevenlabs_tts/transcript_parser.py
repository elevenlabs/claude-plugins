"""Parse Claude Code transcript files to extract assistant messages."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_last_assistant_message(transcript_path: Path) -> str | None:
    """Parse transcript JSONL and extract Claude's last response text.

    Args:
        transcript_path: Path to the transcript JSONL file.

    Returns:
        The text content of the last assistant message, or None if not found.
    """
    if not transcript_path.exists():
        logger.warning("Transcript file not found: %s", transcript_path)
        return None

    messages: list[dict] = []
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msg = json.loads(line)
                        messages.append(msg)
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        logger.error("Failed to read transcript: %s", e)
        return None

    # Find last assistant message
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            text_parts = _extract_text_from_content(content)
            if text_parts:
                return " ".join(text_parts)

    logger.debug("No assistant message found in transcript")
    return None


def _extract_text_from_content(content: list | str) -> list[str]:
    """Extract text blocks from message content.

    Content can be a string or a list of content blocks.
    """
    text_parts: list[str] = []

    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    text = block.get("text", "")
                    if text:
                        text_parts.append(text)

    return text_parts
