"""Keyboard output: direct injection or clipboard fallback."""

import logging
import time
from typing import Optional

try:
    from pynput.keyboard import Controller, Key
    _PYNPUT_AVAILABLE = True
    _PYNPUT_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:
    Controller = None
    Key = None
    _PYNPUT_AVAILABLE = False
    _PYNPUT_IMPORT_ERROR = exc

from .config import Config, is_wayland
from .sound_effects import play_sound

logger = logging.getLogger(__name__)

# Global keyboard controller
_keyboard: Optional[Controller] = None
_injection_capable: Optional[bool] = None
_injection_checked_at: Optional[float] = None
_injection_cache_ttl = 300.0
_pynput_warned = False


def get_keyboard() -> Controller:
    """Get the global keyboard controller."""
    global _keyboard
    if not _PYNPUT_AVAILABLE:
        raise RuntimeError("pynput unavailable; keyboard injection disabled")
    if _keyboard is None:
        _keyboard = Controller()
    return _keyboard


def _warn_pynput_missing() -> None:
    global _pynput_warned
    if _pynput_warned:
        return
    message = "pynput unavailable; falling back to clipboard output"
    if _PYNPUT_IMPORT_ERROR:
        message = f"{message} ({_PYNPUT_IMPORT_ERROR})"
    logger.warning(message)
    _pynput_warned = True


def test_injection() -> bool:
    """Test if keyboard injection works.

    Returns:
        True if injection appears to work, False otherwise.
    """
    global _injection_capable, _injection_checked_at
    now = time.monotonic()
    if (
        _injection_capable is not None
        and _injection_checked_at is not None
        and now - _injection_checked_at < _injection_cache_ttl
    ):
        return _injection_capable

    # On Wayland, injection typically doesn't work
    if is_wayland():
        _injection_capable = False
        _injection_checked_at = now
        return _injection_capable

    if not _PYNPUT_AVAILABLE:
        _warn_pynput_missing()
        _injection_capable = False
        _injection_checked_at = now
        return _injection_capable

    try:
        kb = get_keyboard()
        # Try a simple key press/release
        kb.press(Key.shift)
        kb.release(Key.shift)
        _injection_capable = True
        _injection_checked_at = now
        return _injection_capable
    except Exception:
        _injection_capable = False
        _injection_checked_at = now
        return _injection_capable


def output_text(
    text: str,
    config: Optional[Config] = None,
) -> bool:
    """Output transcribed text using the best available method.

    Args:
        text: The text to output.
        config: Configuration (uses default if not provided).

    Returns:
        True if text was output successfully, False otherwise.
    """
    if config is None:
        config = Config.load()

    # Determine output mode
    mode = config.output_mode
    if mode == "auto":
        mode = "injection" if test_injection() else "clipboard"
        logger.debug("Output mode auto-selected: %s", mode)

    if mode == "injection":
        if not _PYNPUT_AVAILABLE:
            _warn_pynput_missing()
            return _output_via_clipboard(text, config)
        return _output_via_injection(text, config)
    else:
        return _output_via_clipboard(text, config)


def _output_via_injection(text: str, config: Config) -> bool:
    """Output text by simulating keyboard input.

    Args:
        text: The text to type.
        config: Configuration.

    Returns:
        True if successful, False otherwise.
    """
    try:
        if not _PYNPUT_AVAILABLE:
            _warn_pynput_missing()
            return _output_via_clipboard(text, config)

        # Type the text
        kb = get_keyboard()
        kb.type(text)

        if config.sound_effects:
            play_sound("complete")

        return True
    except Exception:
        # Fall back to clipboard on any error
        logger.warning("Injection failed; falling back to clipboard", exc_info=True)
        return _output_via_clipboard(text, config)


def delete_text(num_chars: int, config: Optional[Config] = None) -> bool:
    """Delete text by sending backspace keys.

    Args:
        num_chars: Number of characters to delete.
        config: Configuration (uses default if not provided).

    Returns:
        True if successful, False otherwise.
    """
    if num_chars <= 0:
        return True

    if config is None:
        config = Config.load()

    # Only works with injection mode
    mode = config.output_mode
    if mode == "auto":
        mode = "injection" if test_injection() else "clipboard"

    if mode != "injection" or not _PYNPUT_AVAILABLE:
        logger.debug("Cannot delete text in clipboard mode")
        return False

    try:
        kb = get_keyboard()
        for _ in range(num_chars):
            kb.press(Key.backspace)
            kb.release(Key.backspace)
        return True
    except Exception:
        logger.warning("Failed to delete text", exc_info=True)
        return False


def _output_via_clipboard(text: str, config: Config) -> bool:
    """Output text by copying to clipboard.

    Args:
        text: The text to copy.
        config: Configuration.

    Returns:
        True if successful, False otherwise.
    """
    try:
        try:
            import pyperclip
        except ImportError:
            logger.error("pyperclip not installed; clipboard output unavailable")
            return False
        if hasattr(pyperclip, "is_available") and not pyperclip.is_available():
            logger.error("No clipboard mechanism available")
            return False

        pyperclip.copy(text)

        if config.sound_effects:
            play_sound("complete")

        return True
    except Exception:
        if config.sound_effects:
            play_sound("error")
        logger.warning("Clipboard output failed", exc_info=True)
        return False
