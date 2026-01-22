"""Audio playback with controls for TTS output."""

from __future__ import annotations

import io
import logging
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class AudioPlayer:
    """Audio playback with pause/resume/skip capabilities."""

    def __init__(self):
        self._audio_buffer = io.BytesIO()
        self._playing = False
        self._paused = False
        self._skip_requested = False
        self._play_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._playback_process: subprocess.Popen | None = None

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        return self._playing

    @property
    def is_paused(self) -> bool:
        """Check if playback is paused."""
        return self._paused

    def play_audio(self, audio_data: bytes) -> None:
        """Play audio data.

        Args:
            audio_data: MP3 audio data to play.
        """
        with self._lock:
            if self._playing:
                self.skip()
                time.sleep(0.1)

            self._audio_buffer = io.BytesIO(audio_data)
            self._paused = False
            self._skip_requested = False
            self._playing = True

        self._play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self._play_thread.start()

    def play_stream(self, audio_chunks: list[bytes]) -> None:
        """Play audio from a list of chunks.

        Args:
            audio_chunks: List of audio data chunks.
        """
        audio_data = b"".join(audio_chunks)
        self.play_audio(audio_data)

    def _play_loop(self) -> None:
        """Playback loop using system audio player."""
        try:
            audio_data = self._audio_buffer.read()
            if not audio_data:
                return

            # Write to temporary file
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = Path(f.name)
                f.write(audio_data)

            try:
                self._play_with_system_player(temp_path)
            finally:
                # Clean up temp file
                try:
                    temp_path.unlink()
                except OSError:
                    pass

        except Exception as e:
            logger.error("Playback error: %s", e)
        finally:
            with self._lock:
                self._playing = False
                self._playback_process = None

    def _play_with_system_player(self, audio_path: Path) -> None:
        """Play audio file using system player.

        Args:
            audio_path: Path to the audio file.
        """
        import platform

        system = platform.system()

        try:
            if system == "Darwin":
                # macOS: use afplay
                self._playback_process = subprocess.Popen(
                    ["afplay", str(audio_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif system == "Linux":
                # Linux: try mpv, then ffplay, then paplay
                players = [
                    ["mpv", "--no-video", "--really-quiet", str(audio_path)],
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(audio_path)],
                    ["paplay", str(audio_path)],
                ]
                for cmd in players:
                    try:
                        self._playback_process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        break
                    except FileNotFoundError:
                        continue
                else:
                    logger.error("No audio player found. Install mpv, ffplay, or pulseaudio.")
                    return
            elif system == "Windows":
                # Windows: use built-in media player
                import os

                os.startfile(str(audio_path))  # noqa: S606
                # Can't track process on Windows with startfile
                time.sleep(5)  # Rough estimate for audio length
                return
            else:
                logger.error("Unsupported platform: %s", system)
                return

            # Wait for playback with pause/skip support
            while self._playback_process and self._playback_process.poll() is None:
                if self._skip_requested:
                    self._terminate_playback()
                    break

                while self._paused and not self._skip_requested:
                    time.sleep(0.1)

                time.sleep(0.1)

        except FileNotFoundError as e:
            logger.error("Audio player not found: %s", e)
        except Exception as e:
            logger.error("Playback failed: %s", e)

    def _terminate_playback(self) -> None:
        """Terminate the current playback process."""
        if self._playback_process:
            try:
                self._playback_process.terminate()
                self._playback_process.wait(timeout=1.0)
            except Exception:
                try:
                    self._playback_process.kill()
                except Exception:
                    pass

    def pause(self) -> None:
        """Pause playback."""
        with self._lock:
            self._paused = True
        logger.debug("Playback paused")

    def resume(self) -> None:
        """Resume playback."""
        with self._lock:
            self._paused = False
        logger.debug("Playback resumed")

    def toggle_pause(self) -> None:
        """Toggle pause/resume."""
        with self._lock:
            self._paused = not self._paused
        logger.debug("Playback %s", "paused" if self._paused else "resumed")

    def skip(self) -> None:
        """Skip current playback."""
        with self._lock:
            self._skip_requested = True
        self._terminate_playback()
        logger.debug("Playback skipped")

    def wait_until_done(self, timeout: float | None = None) -> None:
        """Wait for playback to complete.

        Args:
            timeout: Maximum time to wait in seconds.
        """
        if self._play_thread:
            self._play_thread.join(timeout=timeout)

    def stop(self) -> None:
        """Stop all playback and cleanup."""
        self.skip()
        self.wait_until_done(timeout=2.0)
