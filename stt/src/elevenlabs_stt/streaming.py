"""Realtime streaming transcription via WebSocket."""

import base64
import json
import logging
import queue
import threading
from typing import Callable, Optional

import numpy as np
from websockets.sync.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class StreamingError(Exception):
    """Streaming transcription error."""

    pass


class StreamingSession:
    """Manages a single streaming transcription session.

    Connects to ElevenLabs realtime WebSocket, sends audio chunks,
    and receives transcripts.
    """

    WEBSOCKET_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"

    def __init__(
        self,
        api_key: str,
        audio_queue: "queue.Queue[np.ndarray]",
        sample_rate: int = 16000,
        model_id: str = "scribe_v2",
        language_code: Optional[str] = None,
        on_partial: Optional[Callable[[str], None]] = None,
        on_committed: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        vad_mode: bool = True,
        vad_silence_threshold_secs: float = 1.5,
    ):
        """Initialize streaming session.

        Args:
            api_key: ElevenLabs API key.
            audio_queue: Queue providing audio chunks (numpy float32 arrays).
            sample_rate: Audio sample rate (must be 16000).
            model_id: ElevenLabs model ID.
            language_code: Optional language code for transcription.
            on_partial: Callback for partial transcript updates.
            on_committed: Callback for committed (final) transcripts.
            on_error: Callback for errors.
            vad_mode: Use VAD for auto-commit (True) or manual commit (False).
            vad_silence_threshold_secs: Silence threshold for VAD commit.
        """
        self.api_key = api_key
        self.audio_queue = audio_queue
        self.sample_rate = sample_rate
        self.model_id = model_id
        self.language_code = language_code
        self.on_partial = on_partial
        self.on_committed = on_committed
        self.on_error = on_error
        self.vad_mode = vad_mode
        self.vad_silence_threshold_secs = vad_silence_threshold_secs

        self._ws = None
        self._running = False
        self._stop_event = threading.Event()
        self._send_thread: Optional[threading.Thread] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        """Start the streaming session.

        Returns:
            True if session started successfully.
        """
        if self._running:
            return True

        try:
            url = self._build_url()

            self._ws = ws_connect(
                url,
                additional_headers={"xi-api-key": self.api_key},
                close_timeout=5,
            )

            self._running = True
            self._stop_event.clear()

            self._send_thread = threading.Thread(
                target=self._send_loop,
                name="elevenlabs-stt-ws-send",
                daemon=True,
            )
            self._send_thread.start()

            self._recv_thread = threading.Thread(
                target=self._recv_loop,
                name="elevenlabs-stt-ws-recv",
                daemon=True,
            )
            self._recv_thread.start()

            logger.info("Streaming session started")
            return True

        except Exception as e:
            logger.error("Failed to start streaming session: %s", e)
            self._running = False
            if self.on_error:
                self.on_error(StreamingError(f"Connection failed: {e}"))
            return False

    def _build_url(self) -> str:
        """Build WebSocket URL with query parameters."""
        # Realtime API requires scribe_v2_realtime model
        realtime_model = "scribe_v2_realtime"
        params = [
            f"model_id={realtime_model}",
            f"sample_rate={self.sample_rate}",
        ]
        if self.language_code:
            params.append(f"language_code={self.language_code}")
        if self.vad_mode:
            params.append("commit_strategy=vad")
            params.append(f"vad_silence_threshold_secs={self.vad_silence_threshold_secs}")
        else:
            params.append("commit_strategy=manual")

        return f"{self.WEBSOCKET_URL}?{'&'.join(params)}"

    def _send_loop(self) -> None:
        """Send audio chunks to WebSocket."""
        logger.debug("Send loop started")
        chunks_sent = 0
        while not self._stop_event.is_set() and self._running:
            try:
                try:
                    chunk = self.audio_queue.get(timeout=0.05)
                except queue.Empty:
                    continue

                if chunk is None:
                    break

                # Flatten in case of multi-dimensional array
                chunk = np.squeeze(chunk)

                if chunk.dtype == np.float32:
                    pcm_int16 = (chunk * 32767).astype(np.int16)
                elif chunk.dtype == np.float64:
                    pcm_int16 = (chunk * 32767).astype(np.int16)
                else:
                    pcm_int16 = chunk.astype(np.int16)

                audio_b64 = base64.b64encode(pcm_int16.tobytes()).decode("ascii")

                message = {
                    "message_type": "input_audio_chunk",
                    "audio_base_64": audio_b64,
                    "commit": False,
                    "sample_rate": self.sample_rate,
                }

                with self._lock:
                    if self._ws and self._running:
                        self._ws.send(json.dumps(message))
                        chunks_sent += 1
                        if chunks_sent % 50 == 0:
                            logger.debug("Sent %d audio chunks", chunks_sent)

            except ConnectionClosed:
                logger.debug("WebSocket connection closed during send")
                break
            except Exception as e:
                logger.error("Error sending audio chunk: %s", e)
                if self.on_error:
                    self.on_error(e)
                break

    def _recv_loop(self) -> None:
        """Receive transcript messages from WebSocket."""
        logger.debug("Recv loop started")
        while not self._stop_event.is_set() and self._running:
            try:
                with self._lock:
                    ws = self._ws
                if not ws:
                    logger.debug("No WebSocket in recv loop")
                    break

                try:
                    raw = ws.recv(timeout=0.1)
                except TimeoutError:
                    continue

                logger.debug("Received raw message: %s", raw[:200] if len(raw) > 200 else raw)
                message = json.loads(raw)
                msg_type = message.get("message_type", "")

                if msg_type == "partial_transcript":
                    text = message.get("text", "")
                    if text and self.on_partial:
                        self.on_partial(text)

                elif msg_type == "committed_transcript":
                    text = message.get("text", "")
                    if text and self.on_committed:
                        self.on_committed(text)

                elif msg_type in ("auth_error", "quota_exceeded", "rate_limited", "input_error"):
                    error_msg = message.get("message", msg_type)
                    logger.error("WebSocket error: %s - %s", msg_type, error_msg)
                    if self.on_error:
                        self.on_error(StreamingError(f"{msg_type}: {error_msg}"))

                elif msg_type == "session_started":
                    logger.debug("Session started: %s", message)

            except ConnectionClosed:
                logger.debug("WebSocket connection closed during recv")
                break
            except Exception as e:
                logger.error("Error receiving message: %s", e)
                break

    def stop(self, commit: bool = True) -> None:
        """Stop the streaming session.

        Args:
            commit: If True and not using VAD, send manual commit before closing.
        """
        self._stop_event.set()
        self._running = False

        with self._lock:
            if self._ws:
                try:
                    if commit and not self.vad_mode:
                        self._ws.send(
                            json.dumps(
                                {
                                    "message_type": "input_audio_chunk",
                                    "audio_base_64": "",
                                    "commit": True,
                                    "sample_rate": self.sample_rate,
                                }
                            )
                        )
                    self._ws.close()
                except Exception:
                    logger.debug("Error closing WebSocket", exc_info=True)
                finally:
                    self._ws = None

        if self._send_thread:
            self._send_thread.join(timeout=1.0)
        if self._recv_thread:
            self._recv_thread.join(timeout=1.0)

        logger.info("Streaming session stopped")

    @property
    def is_active(self) -> bool:
        """Check if session is active."""
        return self._running
