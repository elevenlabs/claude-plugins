"""Main daemon process for elevenlabs-stt."""

import argparse
import json
import logging
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from .config import Config
from .elevenlabs_client import ElevenLabsClient, ElevenLabsError
from .hotkey import HotkeyListener, HotkeyError
from .keyboard import output_text, test_injection
from .recorder import AudioRecorder, RecorderError
from .sound_effects import play_sound
from .streaming import StreamingSession, StreamingError

logger = logging.getLogger(__name__)


class STTDaemon:
    """Main daemon that coordinates all STT components."""

    def __init__(self, config: Optional[Config] = None):
        """Initialize the daemon.

        Args:
            config: Configuration, or load from file if None.
        """
        self.config = config or Config.load()
        self._running = False
        self._recording = False

        # Components
        self._recorder: Optional[AudioRecorder] = None
        self._client: Optional[ElevenLabsClient] = None
        self._hotkey: Optional[HotkeyListener] = None

        # Recording state
        self._record_start_time: float = 0

        # Threading
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._transcribe_queue: "queue.Queue[Optional[object]]" = queue.Queue(maxsize=2)
        self._transcribe_thread: Optional[threading.Thread] = None

        # Streaming mode
        self._streaming_session: Optional[StreamingSession] = None

        # Streaming commit aggregation - output immediately, update if more commits arrive
        self._commit_buffer: list[str] = []
        self._displayed_text: str = ""  # Track what's currently displayed
        self._commit_lock = threading.Lock()

    def _init_components(self) -> bool:
        """Initialize all components.

        Returns:
            True if all components initialized successfully.
        """
        # Check API key
        api_key = self.config.get_api_key()
        if not api_key:
            logger.error("ElevenLabs API key is required. Set ELEVENLABS_API_KEY or run setup.")
            return False

        try:
            self._recorder = AudioRecorder(
                sample_rate=self.config.sample_rate,
                max_recording_seconds=self.config.max_recording_seconds,
            )
            if not self._recorder.is_available():
                logger.error("No audio input device available")
                return False

            self._client = ElevenLabsClient(api_key)

            self._hotkey = HotkeyListener(
                hotkey=self.config.hotkey,
                on_start=self._on_recording_start,
                on_stop=self._on_recording_stop,
                mode=self.config.activation_mode,
            )
        except HotkeyError as exc:
            logger.error("Hotkey error: %s", exc)
            return False
        except Exception as exc:
            logger.error("Failed to initialize: %s", exc)
            return False

        self._start_transcription_worker()
        return True

    def _start_transcription_worker(self) -> None:
        """Start the transcription worker thread."""
        if self._transcribe_thread is not None:
            return

        self._transcribe_thread = threading.Thread(
            target=self._transcribe_worker,
            name="elevenlabs-stt-transcribe",
            daemon=True,
        )
        self._transcribe_thread.start()

    def _transcribe_worker(self) -> None:
        """Worker thread to process transcription requests."""
        while not self._stop_event.is_set():
            try:
                item = self._transcribe_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if item is None:
                break

            audio = item
            if self._client is None:
                continue

            try:
                text = self._client.transcribe(
                    audio,
                    sample_rate=self.config.sample_rate,
                    model_id=self.config.model_id,
                    language_code=self.config.language_code or None,
                )
            except ElevenLabsError as e:
                logger.error("Transcription failed: %s", e)
                if self.config.sound_effects:
                    play_sound("error")
                continue
            except Exception:
                logger.exception("Transcription failed")
                if self.config.sound_effects:
                    play_sound("error")
                continue

            text = text.strip()
            if text:
                if not output_text(text, self.config):
                    logger.warning("Failed to output transcription")
            elif self.config.sound_effects:
                play_sound("warning")

    def _on_recording_start(self):
        """Called when recording should start."""
        with self._lock:
            if self._recording:
                return

            self._recording = True
            self._record_start_time = time.time()

            # Start recording
            if self._recorder and self._recorder.start():
                if self.config.sound_effects:
                    play_sound("start")
                logger.info("Recording started")

                # For streaming mode, start streaming session
                if self.config.transcription_mode == "streaming":
                    self._start_streaming_session()
            else:
                logger.error("Audio recorder failed to start")
                self._recording = False
                if self.config.sound_effects:
                    play_sound("error")

    def _on_recording_stop(self):
        """Called when recording should stop."""
        audio = None
        with self._lock:
            if not self._recording:
                return

            self._recording = False

            # Stop streaming session first (if active)
            if self._streaming_session:
                self._streaming_session.stop(commit=True)
                self._streaming_session = None

            # Clear commit state (text already output, just reset tracking)
            self._clear_commit_state()

            # Stop recording
            if self._recorder:
                audio = self._recorder.stop()

            if self.config.sound_effects:
                play_sound("stop")

            logger.info("Recording stopped")

        # For non-streaming modes, transcribe the audio
        if self.config.transcription_mode != "streaming":
            if audio is not None and len(audio) > 0:
                try:
                    self._transcribe_queue.put_nowait(audio)
                except queue.Full:
                    logger.warning("Dropping transcription; queue is full")
            elif self.config.sound_effects:
                play_sound("warning")

    def _start_streaming_session(self) -> None:
        """Start a streaming transcription session."""
        if self._streaming_session is not None:
            return

        api_key = self.config.get_api_key()
        if not api_key:
            logger.error("No API key for streaming")
            return

        if not self._recorder:
            logger.error("No recorder available for streaming")
            return

        self._streaming_session = StreamingSession(
            api_key=api_key,
            audio_queue=self._recorder.audio_queue,
            sample_rate=self.config.sample_rate,
            model_id=self.config.model_id,
            language_code=self.config.language_code or None,
            on_partial=self._on_partial_transcript,
            on_committed=self._on_committed_transcript,
            on_error=self._on_streaming_error,
            vad_mode=self.config.streaming_vad_mode,
            vad_silence_threshold_secs=self.config.streaming_vad_silence_secs,
        )

        if not self._streaming_session.start():
            logger.error("Failed to start streaming session")
            self._streaming_session = None
            if self.config.sound_effects:
                play_sound("error")

    def _on_partial_transcript(self, text: str) -> None:
        """Handle partial transcript (for logging only)."""
        logger.debug("Partial: %s", text)

    def _on_committed_transcript(self, text: str) -> None:
        """Handle committed transcript - output immediately, update via diff if needed."""
        logger.info("Committed: %s", text)
        text = text.strip()
        if not text:
            return

        with self._commit_lock:
            # Check if this is a refinement of the last commit (shares prefix)
            if self._commit_buffer:
                last_commit = self._commit_buffer[-1]
                # If new text starts with most of the last commit, it's a refinement
                common_prefix = self._find_common_prefix(last_commit, text)
                if len(common_prefix) >= len(last_commit) * 0.5:
                    # Refinement - replace last commit
                    self._commit_buffer[-1] = text
                else:
                    # New utterance - append
                    self._commit_buffer.append(text)
            else:
                self._commit_buffer.append(text)

            new_text = " ".join(self._commit_buffer)

            # Find common prefix with displayed text and only update the diff
            if self._displayed_text:
                common = self._find_common_prefix(self._displayed_text, new_text)
                chars_to_delete = len(self._displayed_text) - len(common)
                chars_to_type = new_text[len(common):]

                if chars_to_delete > 0:
                    self._delete_chars(chars_to_delete)
                if chars_to_type:
                    logger.info("Typing diff: %s", chars_to_type)
                    output_text(chars_to_type, self.config)
            else:
                logger.info("Outputting: %s", new_text)
                output_text(new_text, self.config)

            self._displayed_text = new_text

    def _find_common_prefix(self, s1: str, s2: str) -> str:
        """Find the common prefix between two strings."""
        min_len = min(len(s1), len(s2))
        for i in range(min_len):
            if s1[i] != s2[i]:
                return s1[:i]
        return s1[:min_len]

    def _delete_chars(self, num_chars: int) -> None:
        """Delete characters by sending backspaces."""
        from .keyboard import delete_text
        if num_chars > 0:
            logger.debug("Deleting %d chars", num_chars)
            delete_text(num_chars, self.config)

    def _clear_commit_state(self) -> None:
        """Clear commit tracking state (called on recording stop)."""
        with self._commit_lock:
            self._commit_buffer.clear()
            self._displayed_text = ""

    def _on_streaming_error(self, error: Exception) -> None:
        """Handle streaming error."""
        logger.error("Streaming error: %s", error)
        if self.config.sound_effects:
            play_sound("error")

    def _check_max_recording_time(self):
        """Check if max recording time has been reached."""
        if not self._recording:
            return

        elapsed = time.time() - self._record_start_time
        max_seconds = self.config.max_recording_seconds

        if max_seconds > 30:
            # Warning at 30 seconds before max
            if elapsed >= max_seconds - 30 and elapsed < max_seconds - 29:
                if self.config.sound_effects:
                    play_sound("warning")

        # Auto-stop at max
        if elapsed >= max_seconds:
            self._on_recording_stop()

    def run(self):
        """Run the daemon main loop."""
        logger.info("elevenlabs-stt daemon starting...")
        logger.info("Hotkey: %s", self.config.hotkey)
        logger.info("Activation: %s", self.config.activation_mode)
        logger.info("Transcription: %s", self.config.transcription_mode)
        if self.config.transcription_mode == "streaming":
            logger.info("Streaming VAD: %s", self.config.streaming_vad_mode)
            logger.info("Streaming VAD silence: %.1fs", self.config.streaming_vad_silence_secs)

        if not self._init_components():
            raise SystemExit(1)

        # Start hotkey listener
        if not self._hotkey.start():
            logger.error("Failed to start hotkey listener")
            raise SystemExit(1)

        self._running = True
        logger.info("Ready for voice input. Press %s to record.", self.config.hotkey)

        # Handle shutdown signals
        def shutdown(signum, frame):
            logger.info("Shutting down...")
            self._running = False

        try:
            signal.signal(signal.SIGINT, shutdown)
            signal.signal(signal.SIGTERM, shutdown)
        except Exception:
            logger.debug("Signal handlers unavailable", exc_info=True)

        # Main loop
        try:
            while self._running:
                self._check_max_recording_time()
                time.sleep(0.1)
        finally:
            self.stop()

    def stop(self):
        """Stop the daemon."""
        self._running = False
        self._stop_event.set()

        # Clear commit state
        self._clear_commit_state()

        try:
            self._transcribe_queue.put_nowait(None)
        except queue.Full:
            pass

        if self._transcribe_thread:
            self._transcribe_thread.join(timeout=1.0)
            if self._transcribe_thread.is_alive():
                logger.warning("Transcribe thread did not exit cleanly")

        # Stop streaming session if active
        if self._streaming_session:
            self._streaming_session.stop(commit=False)
            self._streaming_session = None

        if self._recording and self._recorder:
            self._recorder.stop()

        if self._hotkey:
            self._hotkey.stop()

        if self._client:
            self._client.close()

        logger.info("elevenlabs-stt daemon stopped.")


def get_pid_file() -> Path:
    """Get the PID file path."""
    return Config.get_config_dir() / "daemon.pid"


def _get_plugin_root() -> Path:
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root)
    return Path(__file__).resolve().parents[2]


def _read_pid_file() -> Optional[dict]:
    pid_file = get_pid_file()
    if not pid_file.exists():
        return None

    try:
        raw = pid_file.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        logger.debug("Failed to read PID file", exc_info=True)
        return None
    if not raw:
        return None

    try:
        data = json.loads(raw)
        pid = int(data.get("pid", ""))
        data["pid"] = pid
        return data
    except Exception:
        pass

    try:
        return {"pid": int(raw)}
    except Exception:
        return None


def _write_pid_file(pid: int) -> None:
    data = {
        "pid": pid,
        "command": " ".join(sys.argv),
        "created_at": time.time(),
        "config_dir": str(Config.get_config_dir()),
    }
    pid_file = get_pid_file()
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            dir=str(pid_file.parent),
            encoding="utf-8",
        ) as handle:
            temp_file = Path(handle.name)
            handle.write(json.dumps(data))
        os.replace(temp_file, pid_file)
    finally:
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        return _windows_pid_exists(pid)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def _windows_pid_exists(pid: int) -> bool:
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def _get_process_command(pid: int) -> Optional[str]:
    if os.name == "nt":
        return _get_windows_process_command(pid)

    proc_cmdline = Path(f"/proc/{pid}/cmdline")
    if proc_cmdline.exists():
        try:
            raw = proc_cmdline.read_text(encoding="utf-8", errors="replace")
            command = " ".join(part for part in raw.split("\x00") if part)
            return command or None
        except Exception:
            logger.debug("Failed to read /proc cmdline", exc_info=True)

    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None
        command = result.stdout.strip()
        return command or None
    except Exception:
        return None


def _get_windows_process_command(pid: int) -> Optional[str]:
    try:
        result = subprocess.run(
            ["wmic", "process", "where", f"ProcessId={pid}", "get", "CommandLine"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if len(lines) >= 2:
                return lines[1]
    except Exception:
        logger.debug("wmic lookup failed", exc_info=True)
    return None


def _pid_looks_like_daemon(pid: int) -> bool:
    command = _get_process_command(pid)
    if not command:
        return False
    return "elevenlabs-stt" in command or "elevenlabs_stt" in command


def is_daemon_running() -> bool:
    """Check if daemon is running."""
    pid_file = get_pid_file()
    data = _read_pid_file()
    if not data:
        return False

    try:
        pid = int(data["pid"])
        if pid <= 0:
            pid_file.unlink(missing_ok=True)
            return False
        if not _pid_exists(pid):
            pid_file.unlink(missing_ok=True)
            return False
        command = _get_process_command(pid)
        if command is None:
            return True
        if "elevenlabs-stt" not in command and "elevenlabs_stt" not in command:
            logger.warning("PID file points to non-elevenlabs-stt process; removing stale PID file")
            pid_file.unlink(missing_ok=True)
            return False
        return True
    except PermissionError:
        return True
    except (ValueError, OSError):
        pid_file.unlink(missing_ok=True)
        return False


def _spawn_background() -> bool:
    """Spawn daemon in background using subprocess."""
    log_file = Config.get_config_dir() / "daemon.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("CLAUDE_PLUGIN_ROOT", str(_get_plugin_root()))
    cmd = [sys.executable, "-m", "elevenlabs_stt.daemon", "run"]

    creationflags = 0
    if os.name == "nt":
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)

    try:
        with open(log_file, "a", encoding="utf-8") as log_handle:
            subprocess.Popen(
                cmd,
                env=env,
                stdout=log_handle,
                stderr=log_handle,
                stdin=subprocess.DEVNULL,
                start_new_session=(os.name != "nt"),
                creationflags=creationflags,
            )

        for _ in range(30):
            if is_daemon_running():
                logger.info("Daemon started in background.")
                return True
            time.sleep(0.1)

        logger.warning("Daemon did not start within 3 seconds. Check %s", log_file)
        return False
    except Exception:
        logger.exception("Failed to spawn background daemon")
        return False


def _terminate_process(pid: int) -> bool:
    if os.name == "nt":
        return _taskkill(pid, force=False)
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except PermissionError:
        raise
    except OSError:
        return False


def _force_kill(pid: int) -> None:
    if os.name == "nt":
        _taskkill(pid, force=True)
        return
    kill_signal = signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM
    try:
        os.kill(pid, kill_signal)
    except OSError:
        logger.debug("Force kill failed", exc_info=True)


def _taskkill(pid: int, force: bool) -> bool:
    if pid <= 0:
        return False
    cmd = ["taskkill", "/PID", str(pid), "/T"]
    if force:
        cmd.append("/F")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except Exception:
        logger.debug("taskkill failed", exc_info=True)
        return False


def start_daemon(background: bool = False):
    """Start the daemon."""
    if is_daemon_running():
        logger.info("Daemon is already running.")
        return

    if background:
        if _spawn_background():
            return
        logger.warning("Background spawn failed; running in foreground")

    _write_pid_file(os.getpid())

    try:
        daemon = STTDaemon()
        daemon.run()
    finally:
        get_pid_file().unlink(missing_ok=True)


def stop_daemon():
    """Stop the running daemon."""
    data = _read_pid_file()
    if not data:
        logger.info("Daemon is not running.")
        return

    pid_file = get_pid_file()
    try:
        pid = int(data["pid"])
        command = _get_process_command(pid)
        if command is not None and not _pid_looks_like_daemon(pid):
            logger.warning("PID %s does not look like elevenlabs-stt; refusing to kill", pid)
            pid_file.unlink(missing_ok=True)
            return
        if not _terminate_process(pid):
            logger.warning("Failed to signal daemon (PID %s); leaving PID file intact", pid)
            return
        logger.info("Sent stop signal to daemon (PID %s)", pid)

        # Wait for it to stop
        for _ in range(50):  # 5 seconds
            time.sleep(0.1)
            if not _pid_exists(pid):
                logger.info("Daemon stopped.")
                break
        else:
            logger.warning("Daemon did not stop gracefully, forcing...")
            _force_kill(pid)

    except PermissionError:
        logger.warning("Permission denied stopping daemon (PID %s); leaving PID file intact", pid)
        return
    except (ValueError, OSError):
        logger.info("Daemon is not running.")
        pid_file.unlink(missing_ok=True)
    else:
        pid_file.unlink(missing_ok=True)


def daemon_status():
    """Print daemon status."""
    running = is_daemon_running()
    if running:
        data = _read_pid_file()
        pid = data["pid"] if data else "unknown"
        logger.info("Daemon is running (PID %s)", pid)
    else:
        logger.info("Daemon is not running.")

    config = Config.load()
    logger.info("Config path: %s", Config.get_config_path())
    logger.info("Hotkey: %s", config.hotkey)
    logger.info("Activation: %s", config.activation_mode)
    logger.info("Transcription: %s", config.transcription_mode)

    api_key = config.get_api_key()
    if api_key:
        logger.info("API key: configured")
    else:
        logger.warning("API key: not configured")

    if config.output_mode == "auto":
        injection_ready = test_injection()
        output_label = "injection" if injection_ready else "clipboard"
        logger.info("Output mode: auto (%s)", output_label)
    else:
        logger.info("Output mode: %s", config.output_mode)

    if running:
        logger.info("Hotkey readiness: managed by daemon")
        return

    try:
        listener = HotkeyListener(hotkey=config.hotkey, mode=config.activation_mode)
    except HotkeyError as exc:
        logger.warning("Hotkey readiness: %s", exc)
        return

    try:
        if listener.start():
            logger.info("Hotkey readiness: ready")
        else:
            logger.warning("Hotkey readiness: failed to start")
    finally:
        listener.stop()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the daemon."""
    default_log_level = os.environ.get("ELEVENLABS_STT_LOG_LEVEL", "INFO")
    parser = argparse.ArgumentParser(description="elevenlabs-stt daemon")
    parser.add_argument(
        "command",
        choices=["start", "stop", "status", "run"],
        help="Command to execute",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Run daemon in background",
    )
    parser.add_argument(
        "--log-level",
        default=default_log_level,
        help="Logging level (default: ELEVENLABS_STT_LOG_LEVEL or INFO).",
    )

    args = parser.parse_args(argv)
    setup_logging(args.log_level)

    if args.command == "start":
        start_daemon(background=args.background)
    elif args.command == "stop":
        stop_daemon()
    elif args.command == "status":
        daemon_status()
    elif args.command == "run":
        # Run in foreground (for debugging)
        start_daemon(background=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
