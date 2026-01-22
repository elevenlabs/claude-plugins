"""TTS daemon for Claude Code."""

from __future__ import annotations

import argparse
import logging
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from elevenlabs_tts.audio_player import AudioPlayer
from elevenlabs_tts.config import Config
from elevenlabs_tts.elevenlabs_client import ElevenLabsClient
from elevenlabs_tts.hotkey import HotkeyListener
from elevenlabs_tts.ipc import IpcServer, get_socket_path
from elevenlabs_tts.sound_effects import play_sound

logger = logging.getLogger(__name__)


def _get_plugin_root() -> Path:
    """Get the plugin root directory."""
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root).expanduser()
    return Path(__file__).resolve().parents[2]


class TTSDaemon:
    """Main daemon that coordinates TTS playback."""

    def __init__(self, config: Config):
        self.config = config
        self._running = False
        self._auto_read_enabled = config.auto_read

        # Components (initialized later)
        self._client: ElevenLabsClient | None = None
        self._player: AudioPlayer | None = None
        self._hotkey_listener: HotkeyListener | None = None
        self._ipc_server: IpcServer | None = None

        # Speak queue
        self._speak_queue: queue.Queue[str] = queue.Queue()
        self._speak_thread: threading.Thread | None = None

        # Threading
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def _init_components(self) -> bool:
        """Initialize daemon components.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        api_key = self.config.get_api_key()
        if not api_key:
            logger.error("No API key configured. Run /elevenlabs-tts:setup first.")
            return False

        # Initialize client
        self._client = ElevenLabsClient(api_key, self.config)

        # Test connection
        if not self._client.test_connection():
            logger.error("API connection failed. Check your API key.")
            return False

        # Initialize player
        self._player = AudioPlayer()

        # Initialize hotkey listener
        self._hotkey_listener = HotkeyListener(
            on_toggle=self._on_toggle,
            on_pause=self._on_pause,
            on_skip=self._on_skip,
            hotkey_toggle=self.config.hotkey_toggle,
            hotkey_pause=self.config.hotkey_pause,
            hotkey_skip=self.config.hotkey_skip,
        )

        # Initialize IPC server
        socket_path = get_socket_path()
        self._ipc_server = IpcServer(socket_path, self._on_ipc_message)

        return True

    def _on_toggle(self) -> None:
        """Handle toggle hotkey."""
        with self._lock:
            self._auto_read_enabled = not self._auto_read_enabled
        status = "enabled" if self._auto_read_enabled else "disabled"
        logger.info("Auto-read %s", status)
        if self.config.sound_effects:
            play_sound("start" if self._auto_read_enabled else "stop")

    def _on_pause(self) -> None:
        """Handle pause hotkey."""
        if self._player:
            self._player.toggle_pause()
            if self.config.sound_effects:
                play_sound("start" if not self._player.is_paused else "stop")

    def _on_skip(self) -> None:
        """Handle skip hotkey."""
        if self._player:
            self._player.skip()
            if self.config.sound_effects:
                play_sound("stop")

    def _on_ipc_message(self, message: dict) -> None:
        """Handle IPC message from hook handler.

        Args:
            message: Message dictionary with 'type' and 'text' keys.
        """
        msg_type = message.get("type")
        if msg_type == "speak":
            text = message.get("text", "")
            if text:
                self.speak(text)
        else:
            logger.warning("Unknown IPC message type: %s", msg_type)

    def speak(self, text: str) -> None:
        """Queue text for TTS playback.

        Args:
            text: Text to speak.
        """
        if not self._auto_read_enabled:
            logger.debug("Auto-read disabled, skipping")
            return

        # Filter text
        filtered_text = self._filter_text(text)
        if not filtered_text:
            logger.debug("No text after filtering")
            return

        self._speak_queue.put(filtered_text)
        logger.debug("Queued text for TTS (%d chars)", len(filtered_text))

    def _filter_text(self, text: str) -> str:
        """Filter text for TTS output.

        Args:
            text: Raw text from Claude.

        Returns:
            Filtered text suitable for TTS.
        """
        # Remove code blocks if configured
        if self.config.skip_code_blocks:
            text = re.sub(r"```[\s\S]*?```", "[code block]", text)
            # Keep inline code content but remove backticks
            text = re.sub(r"`([^`]+)`", r"\1", text)

        # Remove markdown formatting
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # bold
        text = re.sub(r"\*([^*]+)\*", r"\1", text)  # italic
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
        text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)  # headers

        # Remove excessive whitespace
        text = re.sub(r"\n\s*\n", "\n\n", text)
        text = text.strip()

        # Truncate if too long
        if len(text) > self.config.max_text_length:
            text = text[: self.config.max_text_length] + "... text truncated."

        return text

    def _speak_worker(self) -> None:
        """Worker thread for TTS playback."""
        while not self._stop_event.is_set():
            try:
                text = self._speak_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self._stream_and_play(text)
            except Exception as e:
                logger.error("TTS playback failed: %s", e)
                if self.config.sound_effects:
                    play_sound("error")

    def _stream_and_play(self, text: str) -> None:
        """Stream TTS audio and play it.

        Args:
            text: Text to convert and play.
        """
        if not self._client or not self._player:
            return

        if self.config.sound_effects:
            play_sound("start")

        # Collect audio chunks
        chunks: list[bytes] = []
        try:
            for chunk in self._client.stream(text):
                if self._stop_event.is_set():
                    return
                chunks.append(chunk)
        except Exception as e:
            logger.error("TTS streaming failed: %s", e)
            if self.config.sound_effects:
                play_sound("error")
            return

        if not chunks:
            logger.warning("No audio data received")
            return

        # Play collected audio
        audio_data = b"".join(chunks)
        self._player.play_audio(audio_data)
        self._player.wait_until_done()

        if self.config.sound_effects:
            play_sound("complete")

    def run(self) -> int:
        """Run the daemon.

        Returns:
            Exit code (0 for success, non-zero for failure).
        """
        if not self._init_components():
            return 1

        self._running = True

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Start components
        if self._ipc_server:
            self._ipc_server.start()

        if self._hotkey_listener:
            self._hotkey_listener.start()

        # Start speak worker
        self._speak_thread = threading.Thread(target=self._speak_worker, daemon=True)
        self._speak_thread.start()

        # Write PID file
        pid_path = self.config.get_config_dir() / "daemon.pid"
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()))

        logger.info("TTS daemon started (PID %d)", os.getpid())
        logger.info("Auto-read: %s", "enabled" if self._auto_read_enabled else "disabled")
        logger.info("Voice: %s", self.config.voice_id)
        logger.info("Toggle hotkey: %s", self.config.hotkey_toggle)
        logger.info("Pause hotkey: %s", self.config.hotkey_pause)
        logger.info("Skip hotkey: %s", self.config.hotkey_skip)

        # Main loop
        try:
            while self._running and not self._stop_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

        self.stop()
        return 0

    def _signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        logger.info("Received signal %d, shutting down...", signum)
        self._running = False
        self._stop_event.set()

    def stop(self) -> None:
        """Stop the daemon and cleanup."""
        self._running = False
        self._stop_event.set()

        if self._hotkey_listener:
            self._hotkey_listener.stop()

        if self._ipc_server:
            self._ipc_server.stop()

        if self._player:
            self._player.stop()

        if self._client:
            self._client.close()

        if self._speak_thread and self._speak_thread.is_alive():
            self._speak_thread.join(timeout=2.0)

        # Remove PID file
        pid_path = self.config.get_config_dir() / "daemon.pid"
        if pid_path.exists():
            try:
                pid_path.unlink()
            except OSError:
                pass

        logger.info("TTS daemon stopped")


def get_pid() -> int | None:
    """Get the PID of a running daemon.

    Returns:
        PID if daemon is running, None otherwise.
    """
    pid_path = Config.get_config_dir() / "daemon.pid"
    if not pid_path.exists():
        return None

    try:
        pid = int(pid_path.read_text().strip())
        # Check if process is running
        os.kill(pid, 0)
        return pid
    except (ValueError, OSError):
        # PID file is stale
        try:
            pid_path.unlink()
        except OSError:
            pass
        return None


def is_running() -> bool:
    """Check if the daemon is running."""
    return get_pid() is not None


def start_daemon(background: bool = False) -> int:
    """Start the TTS daemon.

    Args:
        background: If True, spawn daemon in background.

    Returns:
        Exit code.
    """
    if is_running():
        logger.warning("Daemon is already running (PID %d)", get_pid())
        return 0

    config = Config.load()

    if background:
        return _spawn_background()

    daemon = TTSDaemon(config)
    return daemon.run()


def _spawn_background() -> int:
    """Spawn daemon in background process.

    Returns:
        Exit code.
    """
    plugin_root = _get_plugin_root()
    exec_script = plugin_root / "scripts" / "exec.py"

    if not exec_script.exists():
        logger.error("exec.py not found: %s", exec_script)
        return 1

    # Build command
    cmd = [
        sys.executable,
        str(exec_script),
        "-m",
        "elevenlabs_tts.daemon",
        "start",
    ]

    # Add log level if set
    log_level = os.environ.get("ELEVENLABS_TTS_LOG_LEVEL")
    if log_level:
        cmd.extend(["--log-level", log_level])

    # Spawn detached process
    env = os.environ.copy()
    env.setdefault("CLAUDE_PLUGIN_ROOT", str(plugin_root))

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        logger.info("Daemon spawned in background")
        return 0
    except Exception as e:
        logger.error("Failed to spawn daemon: %s", e)
        return 1


def stop_daemon() -> int:
    """Stop the running daemon.

    Returns:
        Exit code.
    """
    pid = get_pid()
    if pid is None:
        logger.info("Daemon is not running")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
        logger.info("Sent SIGTERM to daemon (PID %d)", pid)

        # Wait for process to exit
        for _ in range(30):  # 3 seconds
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except OSError:
                logger.info("Daemon stopped")
                return 0

        # Force kill if still running
        try:
            os.kill(pid, signal.SIGKILL)
            logger.warning("Force killed daemon (PID %d)", pid)
        except OSError:
            pass

        return 0
    except OSError as e:
        logger.error("Failed to stop daemon: %s", e)
        return 1


def status_daemon() -> int:
    """Print daemon status.

    Returns:
        Exit code.
    """
    pid = get_pid()
    if pid is None:
        print("TTS daemon is not running")
        return 1

    print(f"TTS daemon is running (PID {pid})")

    config = Config.load()
    print(f"Auto-read: {'enabled' if config.auto_read else 'disabled'}")
    print(f"Voice: {config.voice_id}")
    print(f"Toggle hotkey: {config.hotkey_toggle}")
    print(f"Pause hotkey: {config.hotkey_pause}")
    print(f"Skip hotkey: {config.hotkey_skip}")

    return 0


def main() -> int:
    """Main entry point."""
    default_log_level = os.environ.get("ELEVENLABS_TTS_LOG_LEVEL", "INFO")

    parser = argparse.ArgumentParser(description="ElevenLabs TTS daemon")
    parser.add_argument(
        "command",
        choices=["start", "stop", "status", "restart"],
        help="Daemon command",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Run daemon in background",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=default_log_level,
        help="Logging level",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "start":
        return start_daemon(background=args.background)
    elif args.command == "stop":
        return stop_daemon()
    elif args.command == "status":
        return status_daemon()
    elif args.command == "restart":
        stop_daemon()
        time.sleep(0.5)
        return start_daemon(background=args.background)

    return 0


if __name__ == "__main__":
    sys.exit(main())
