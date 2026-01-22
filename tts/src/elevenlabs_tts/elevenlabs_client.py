"""ElevenLabs Text-to-Speech API client."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Iterator

import httpx

if TYPE_CHECKING:
    from elevenlabs_tts.config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.elevenlabs.io/v1"


class ElevenLabsClient:
    """Client for ElevenLabs Text-to-Speech API."""

    def __init__(self, api_key: str, config: "Config"):
        self.api_key = api_key
        self.config = config
        self._client = httpx.Client(timeout=60.0)

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def test_connection(self) -> bool:
        """Test if the API key is valid.

        Returns:
            True if the connection is successful, False otherwise.
        """
        try:
            response = self._client.get(
                f"{BASE_URL}/user",
                headers={"xi-api-key": self.api_key},
            )
            return response.status_code == 200
        except Exception as e:
            logger.error("Connection test failed: %s", e)
            return False

    def get_voices(self) -> list[dict]:
        """Get list of available voices.

        Returns:
            List of voice dictionaries with 'voice_id' and 'name' keys.
        """
        try:
            response = self._client.get(
                f"{BASE_URL}/voices",
                headers={"xi-api-key": self.api_key},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("voices", [])
        except Exception as e:
            logger.error("Failed to get voices: %s", e)
            return []

    def stream(self, text: str) -> Iterator[bytes]:
        """Stream TTS audio, yielding audio chunks.

        Args:
            text: Text to convert to speech.

        Yields:
            Audio data chunks (MP3 format by default).
        """
        url = f"{BASE_URL}/text-to-speech/{self.config.voice_id}/stream"

        try:
            with self._client.stream(
                "POST",
                url,
                headers={"xi-api-key": self.api_key},
                params={"output_format": self.config.output_format},
                json={
                    "text": text,
                    "model_id": self.config.model_id,
                    "voice_settings": {
                        "stability": self.config.stability,
                        "similarity_boost": self.config.similarity_boost,
                        "speed": self.config.speed,
                    },
                },
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=1024):
                    if chunk:
                        yield chunk
        except httpx.HTTPStatusError as e:
            logger.error("TTS API error: %s - %s", e.response.status_code, e.response.text)
            raise
        except Exception as e:
            logger.error("TTS stream failed: %s", e)
            raise

    def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio (non-streaming).

        Args:
            text: Text to convert to speech.

        Returns:
            Complete audio data.
        """
        url = f"{BASE_URL}/text-to-speech/{self.config.voice_id}"

        try:
            response = self._client.post(
                url,
                headers={"xi-api-key": self.api_key},
                params={"output_format": self.config.output_format},
                json={
                    "text": text,
                    "model_id": self.config.model_id,
                    "voice_settings": {
                        "stability": self.config.stability,
                        "similarity_boost": self.config.similarity_boost,
                        "speed": self.config.speed,
                    },
                },
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as e:
            logger.error("TTS API error: %s - %s", e.response.status_code, e.response.text)
            raise
        except Exception as e:
            logger.error("TTS synthesis failed: %s", e)
            raise
