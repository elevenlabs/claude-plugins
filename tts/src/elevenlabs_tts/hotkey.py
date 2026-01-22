"""Global hotkey listener for TTS controls."""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

from pynput import keyboard

logger = logging.getLogger(__name__)


def parse_hotkey(hotkey_str: str) -> set[keyboard.Key | keyboard.KeyCode]:
    """Parse a hotkey string into pynput keys.

    Args:
        hotkey_str: Hotkey string like "ctrl+shift+t".

    Returns:
        Set of pynput Key/KeyCode objects.
    """
    keys: set[keyboard.Key | keyboard.KeyCode] = set()

    for part in hotkey_str.lower().split("+"):
        part = part.strip()
        if not part:
            continue

        # Modifiers
        if part in ("ctrl", "control"):
            keys.add(keyboard.Key.ctrl)
        elif part in ("cmd", "command", "super", "win"):
            keys.add(keyboard.Key.cmd)
        elif part in ("alt", "option"):
            keys.add(keyboard.Key.alt)
        elif part in ("shift",):
            keys.add(keyboard.Key.shift)
        # Special keys
        elif part == "space":
            keys.add(keyboard.Key.space)
        elif part == "tab":
            keys.add(keyboard.Key.tab)
        elif part == "enter":
            keys.add(keyboard.Key.enter)
        elif part == "esc":
            keys.add(keyboard.Key.esc)
        # Regular characters
        elif len(part) == 1:
            keys.add(keyboard.KeyCode.from_char(part))
        else:
            logger.warning("Unknown key: %s", part)

    return keys


def normalize_key(key: keyboard.Key | keyboard.KeyCode) -> keyboard.Key | keyboard.KeyCode:
    """Normalize key to handle left/right variants."""
    if isinstance(key, keyboard.Key):
        name = key.name
        # Normalize left/right variants
        if name in ("ctrl_l", "ctrl_r"):
            return keyboard.Key.ctrl
        if name in ("alt_l", "alt_r"):
            return keyboard.Key.alt
        if name in ("shift_l", "shift_r"):
            return keyboard.Key.shift
        if name in ("cmd_l", "cmd_r"):
            return keyboard.Key.cmd
    return key


class HotkeyListener:
    """Listens for global hotkeys and triggers callbacks."""

    def __init__(
        self,
        on_toggle: Callable[[], None] | None = None,
        on_pause: Callable[[], None] | None = None,
        on_skip: Callable[[], None] | None = None,
        hotkey_toggle: str = "ctrl+shift+t",
        hotkey_pause: str = "ctrl+shift+p",
        hotkey_skip: str = "ctrl+shift+s",
    ):
        self._on_toggle = on_toggle
        self._on_pause = on_pause
        self._on_skip = on_skip

        self._hotkey_toggle = parse_hotkey(hotkey_toggle)
        self._hotkey_pause = parse_hotkey(hotkey_pause)
        self._hotkey_skip = parse_hotkey(hotkey_skip)

        self._current_keys: set[keyboard.Key | keyboard.KeyCode] = set()
        self._listener: keyboard.Listener | None = None
        self._event_queue: queue.Queue[str] = queue.Queue(maxsize=8)
        self._worker_thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start listening for hotkeys."""
        if self._running:
            return

        self._running = True
        self._current_keys.clear()

        # Start event worker
        self._worker_thread = threading.Thread(target=self._event_worker, daemon=True)
        self._worker_thread.start()

        # Start keyboard listener
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        logger.info("Hotkey listener started")

    def stop(self) -> None:
        """Stop listening for hotkeys."""
        self._running = False

        if self._listener:
            self._listener.stop()
            self._listener = None

        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)

        logger.info("Hotkey listener stopped")

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        """Handle key press events."""
        normalized = normalize_key(key)
        with self._lock:
            self._current_keys.add(normalized)
            self._check_hotkeys()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        """Handle key release events."""
        normalized = normalize_key(key)
        with self._lock:
            self._current_keys.discard(normalized)

    def _check_hotkeys(self) -> None:
        """Check if any hotkey combination is pressed."""
        if self._hotkey_toggle and self._hotkey_toggle <= self._current_keys:
            self._queue_event("toggle")
        elif self._hotkey_pause and self._hotkey_pause <= self._current_keys:
            self._queue_event("pause")
        elif self._hotkey_skip and self._hotkey_skip <= self._current_keys:
            self._queue_event("skip")

    def _queue_event(self, event: str) -> None:
        """Queue an event for processing."""
        try:
            self._event_queue.put_nowait(event)
        except queue.Full:
            logger.warning("Event queue full, dropping event: %s", event)

    def _event_worker(self) -> None:
        """Process events from the queue."""
        while self._running:
            try:
                event = self._event_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                if event == "toggle" and self._on_toggle:
                    self._on_toggle()
                elif event == "pause" and self._on_pause:
                    self._on_pause()
                elif event == "skip" and self._on_skip:
                    self._on_skip()
            except Exception as e:
                logger.error("Error handling event %s: %s", event, e)
