"""ElevenLabs Speech-to-Text API client."""

import logging
import tempfile
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
from scipy.io import wavfile

logger = logging.getLogger(__name__)


class ElevenLabsError(Exception):
    """Error from ElevenLabs API."""
    pass


class ElevenLabsClient:
    """Client for ElevenLabs Speech-to-Text API."""

    BASE_URL = "https://api.elevenlabs.io/v1/speech-to-text"

    def __init__(self, api_key: str):
        """Initialize the client.

        Args:
            api_key: ElevenLabs API key.
        """
        self.api_key = api_key
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        model_id: str = "scribe_v2",
        language_code: Optional[str] = None,
    ) -> str:
        """Transcribe audio using ElevenLabs API.

        Args:
            audio: Audio data as numpy array (float32 or int16).
            sample_rate: Sample rate of the audio.
            model_id: ElevenLabs model ID to use.
            language_code: Optional language code (e.g., "en"). None for auto-detect.

        Returns:
            Transcribed text.

        Raises:
            ElevenLabsError: If transcription fails.
        """
        if not self.api_key:
            raise ElevenLabsError("ElevenLabs API key is required")

        # Save audio to temporary WAV file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Convert float32 to int16 if needed
            if audio.dtype == np.float32:
                audio_int16 = (audio * 32767).astype(np.int16)
            elif audio.dtype == np.float64:
                audio_int16 = (audio * 32767).astype(np.int16)
            else:
                audio_int16 = audio.astype(np.int16)

            wavfile.write(str(tmp_path), sample_rate, audio_int16)

            return self.transcribe_file(
                tmp_path,
                model_id=model_id,
                language_code=language_code,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    def transcribe_file(
        self,
        audio_path: Path,
        model_id: str = "scribe_v2",
        language_code: Optional[str] = None,
    ) -> str:
        """Transcribe audio file using ElevenLabs API.

        Args:
            audio_path: Path to audio file.
            model_id: ElevenLabs model ID to use.
            language_code: Optional language code (e.g., "en"). None for auto-detect.

        Returns:
            Transcribed text.

        Raises:
            ElevenLabsError: If transcription fails.
        """
        if not self.api_key:
            raise ElevenLabsError("ElevenLabs API key is required")

        client = self._get_client()

        headers = {
            "xi-api-key": self.api_key,
        }

        # Prepare multipart form data
        data = {
            "model_id": model_id,
            "timestamps_granularity": "none",
        }
        if language_code:
            data["language_code"] = language_code

        try:
            with open(audio_path, "rb") as f:
                files = {"file": (audio_path.name, f, "audio/wav")}
                response = client.post(
                    self.BASE_URL,
                    headers=headers,
                    data=data,
                    files=files,
                )

            if response.status_code != 200:
                error_msg = f"ElevenLabs API error: {response.status_code}"
                try:
                    error_data = response.json()
                    if "detail" in error_data:
                        error_msg = f"{error_msg} - {error_data['detail']}"
                except Exception:
                    error_msg = f"{error_msg} - {response.text}"
                raise ElevenLabsError(error_msg)

            result = response.json()
            return result.get("text", "")

        except httpx.HTTPError as e:
            raise ElevenLabsError(f"HTTP error: {e}") from e

    def test_connection(self) -> bool:
        """Test API connection by making a simple request.

        Returns:
            True if API key is valid.
        """
        if not self.api_key:
            return False

        client = self._get_client()
        headers = {"xi-api-key": self.api_key}

        try:
            # Use the user endpoint to verify API key
            response = client.get(
                "https://api.elevenlabs.io/v1/user",
                headers=headers,
            )
            return response.status_code == 200
        except Exception:
            return False
