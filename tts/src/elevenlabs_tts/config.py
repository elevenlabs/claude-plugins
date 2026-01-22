"""Configuration management for elevenlabs-tts using Pydantic."""

import os
import sys
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

if sys.version_info >= (3, 11):
    import tomllib as tomli
else:
    try:
        import tomli
    except ImportError:
        tomli = None

try:
    import tomli_w
except ImportError:
    tomli_w = None


class Config(BaseModel):
    """ElevenLabs TTS configuration."""

    # API settings
    api_key: str = Field(default="", description="ElevenLabs API key")
    voice_id: str = Field(
        default="21m00Tcm4TlvDq8ikWAM", description="ElevenLabs voice ID (default: Rachel)"
    )
    model_id: str = Field(default="eleven_multilingual_v2", description="TTS model")

    # Audio settings
    output_format: Literal["mp3_44100_128", "mp3_22050_32", "pcm_16000", "pcm_24000"] = Field(
        default="mp3_44100_128", description="Audio output format"
    )
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech speed multiplier")

    # Voice settings
    stability: float = Field(default=0.5, ge=0.0, le=1.0, description="Voice stability")
    similarity_boost: float = Field(default=0.75, ge=0.0, le=1.0, description="Similarity boost")

    # Behavior settings
    auto_read: bool = Field(default=True, description="Automatically read Claude responses")
    hotkey_toggle: str = Field(default="ctrl+shift+t", description="Toggle TTS on/off")
    hotkey_pause: str = Field(default="ctrl+shift+p", description="Pause/resume playback")
    hotkey_skip: str = Field(default="ctrl+shift+s", description="Skip current playback")

    # Filtering
    skip_code_blocks: bool = Field(default=True, description="Skip reading code blocks")
    max_text_length: int = Field(default=5000, ge=100, le=50000, description="Maximum text length")

    # Feedback
    sound_effects: bool = Field(default=True, description="Play audio feedback sounds")

    @field_validator("voice_id")
    @classmethod
    def validate_voice_id(cls, v: str) -> str:
        if not v or not v.strip():
            return "21m00Tcm4TlvDq8ikWAM"  # Rachel
        return v.strip()

    @field_validator("speed")
    @classmethod
    def validate_speed(cls, v: float) -> float:
        return max(0.5, min(2.0, v))

    def get_api_key(self) -> str:
        """Get API key from environment or config."""
        return os.environ.get("ELEVENLABS_API_KEY", "") or self.api_key

    @classmethod
    def get_config_dir(cls) -> Path:
        """Get the configuration directory path."""
        override = os.environ.get("ELEVENLABS_TTS_CONFIG_DIR")
        if override:
            return Path(override).expanduser()
        return Path.home() / ".claude" / "plugins" / "elevenlabs-tts"

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the configuration file path."""
        return cls.get_config_dir() / "config.toml"

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from file, or return defaults."""
        config_path = cls.get_config_path()
        if not config_path.exists():
            return cls()

        if tomli is None:
            return cls()

        try:
            with open(config_path, "rb") as f:
                data = tomli.load(f)

            config_data = data.get("elevenlabs-tts", {})
            return cls(**config_data)
        except Exception:
            return cls()

    def save(self) -> bool:
        """Save configuration to file."""
        if tomli_w is None:
            return False

        config_path = self.get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "elevenlabs-tts": {
                "api_key": self.api_key,
                "voice_id": self.voice_id,
                "model_id": self.model_id,
                "output_format": self.output_format,
                "speed": self.speed,
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "auto_read": self.auto_read,
                "hotkey_toggle": self.hotkey_toggle,
                "hotkey_pause": self.hotkey_pause,
                "hotkey_skip": self.hotkey_skip,
                "skip_code_blocks": self.skip_code_blocks,
                "max_text_length": self.max_text_length,
                "sound_effects": self.sound_effects,
            }
        }

        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb",
                delete=False,
                dir=str(config_path.parent),
            ) as handle:
                temp_file = Path(handle.name)
                tomli_w.dump(data, handle)
            os.replace(temp_file, config_path)
            return True
        except Exception:
            return False
        finally:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except OSError:
                    pass
