"""Audio recording using sounddevice."""

import logging
import math
import queue
import threading
from collections import deque
from typing import Deque, Optional

import numpy as np

_SOUNDDEVICE_IMPORT_ERROR: Optional[Exception] = None
try:
    import sounddevice as sd
except Exception as exc:
    sd = None
    _SOUNDDEVICE_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)


class RecorderError(Exception):
    """Audio recorder error."""
    pass


class AudioRecorder:
    """Records audio from the microphone."""

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BLOCKSIZE = 1024  # ~64ms at 16kHz
    DTYPE = "float32"

    def __init__(
        self,
        sample_rate: int = 16000,
        max_recording_seconds: Optional[int] = None,
        device: Optional[str] = None,
    ):
        """Initialize the recorder.

        Args:
            sample_rate: Audio sample rate.
            max_recording_seconds: Maximum recording duration in seconds.
            device: Input device name (None = system default).
        """
        self.sample_rate = sample_rate
        self.max_recording_seconds = max_recording_seconds
        self.device = device
        self._recording = False
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: Optional["sd.InputStream"] = None
        self._recorded_chunks: Deque[np.ndarray] = deque()
        self._max_chunks = self._compute_max_chunks()
        self._lock = threading.Lock()

    def _compute_max_chunks(self) -> Optional[int]:
        """Compute max chunks based on recording duration."""
        if not self.max_recording_seconds:
            return None
        max_seconds = max(1, int(self.max_recording_seconds))
        chunks = max_seconds * self.sample_rate / self.BLOCKSIZE
        return max(1, int(math.ceil(chunks)))

    def is_available(self) -> bool:
        """Check if audio recording is available."""
        if sd is None:
            return False

        try:
            devices = sd.query_devices()
            return any(d.get("max_input_channels", 0) > 0 for d in devices)
        except Exception:
            return False

    def get_devices(self) -> list[dict]:
        """Get available input devices.

        Returns:
            List of device info dictionaries.
        """
        if sd is None:
            return []

        try:
            devices = sd.query_devices()
            return [
                {"name": d["name"], "index": i, "channels": d["max_input_channels"]}
                for i, d in enumerate(devices)
                if d["max_input_channels"] > 0
            ]
        except Exception:
            return []

    def resolve_device(self) -> Optional[int]:
        """Resolve device name to device index.

        Returns:
            Device index, or None if not found or using default.
        """
        if not self.device:
            return None

        devices = self.get_devices()
        # Exact match
        for d in devices:
            if d["name"] == self.device:
                return d["index"]
        # Substring match (case-insensitive)
        device_lower = self.device.lower()
        for d in devices:
            if device_lower in d["name"].lower():
                return d["index"]
        return None

    def start(self) -> bool:
        """Start recording audio.

        Returns:
            True if recording started successfully.
        """
        if sd is None:
            logger.error("sounddevice not available")
            return False

        if self._recording:
            return True

        try:
            self._audio_queue = queue.Queue(maxsize=32)
            if self._max_chunks:
                self._recorded_chunks = deque(maxlen=self._max_chunks)
            else:
                self._recorded_chunks = deque()

            def callback(indata, frames, time_info, status):
                if status:
                    logger.debug("Audio callback status: %s", status)
                try:
                    self._audio_queue.put_nowait(indata.copy())
                except queue.Full:
                    logger.debug("Audio queue full; dropping chunk")
                with self._lock:
                    self._recorded_chunks.append(indata.copy())

            device_index = self.resolve_device()
            if self.device and device_index is None:
                logger.warning("Input device '%s' not found, using system default", self.device)

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.CHANNELS,
                dtype=self.DTYPE,
                blocksize=self.BLOCKSIZE,
                callback=callback,
                device=device_index,
            )
            self._stream.start()
            self._recording = True
            return True

        except Exception:
            logger.exception("Failed to start audio recording")
            return False

    def stop(self) -> Optional[np.ndarray]:
        """Stop recording and return all recorded audio.

        Returns:
            Numpy array of all recorded audio, or None if no audio.
        """
        if not self._recording or self._stream is None:
            return None

        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            logger.debug("Failed to stop audio stream cleanly", exc_info=True)

        self._stream = None
        self._recording = False

        with self._lock:
            if not self._recorded_chunks:
                return None

            # Concatenate all chunks
            audio = np.concatenate(list(self._recorded_chunks))
            self._recorded_chunks = deque()
            return np.squeeze(audio)

    def get_duration(self) -> float:
        """Get current recording duration in seconds."""
        with self._lock:
            total_samples = sum(len(chunk) for chunk in self._recorded_chunks)
            return total_samples / self.sample_rate

    @property
    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._recording

    @property
    def audio_queue(self) -> "queue.Queue[np.ndarray]":
        """Get the audio chunk queue for streaming."""
        return self._audio_queue


def get_sounddevice_import_error() -> Optional[Exception]:
    """Return the sounddevice import error, if any."""
    return _SOUNDDEVICE_IMPORT_ERROR
