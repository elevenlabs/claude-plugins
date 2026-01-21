"""Configuration management for elevenlabs-stt using Pydantic."""

import os
import platform
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
    """ElevenLabs STT configuration."""

    # API settings
    api_key: str = Field(default="", description="ElevenLabs API key")
    model_id: str = Field(default="scribe_v2", description="ElevenLabs STT model")
    language_code: str = Field(default="", description="Language code (empty = auto-detect)")

    # Hotkey settings
    hotkey: str = Field(default="ctrl+shift+space", description="Hotkey combination")
    activation_mode: Literal["push-to-talk", "toggle"] = Field(
        default="toggle", description="Hotkey activation mode"
    )
    transcription_mode: Literal["streaming", "batch"] = Field(
        default="streaming", description="Transcription mode"
    )

    # Legacy field for backwards compatibility
    mode: str = Field(default="", description="Deprecated - use activation_mode and transcription_mode")

    # Audio settings
    sample_rate: int = Field(default=16000, description="Audio sample rate")
    max_recording_seconds: int = Field(default=300, ge=1, le=600, description="Max recording duration")

    # Output settings
    output_mode: Literal["injection", "clipboard", "auto"] = Field(
        default="auto", description="Text output method"
    )

    # Feedback settings
    sound_effects: bool = Field(default=True, description="Play audio feedback sounds")

    # Streaming mode settings
    streaming_vad_mode: bool = Field(
        default=True, description="Use VAD auto-commit in streaming mode"
    )
    streaming_vad_silence_secs: float = Field(
        default=1.0, ge=0.5, le=5.0, description="Silence threshold for VAD commit"
    )

    @field_validator("hotkey")
    @classmethod
    def validate_hotkey(cls, v: str) -> str:
        if not v or not v.strip():
            return "ctrl+shift+space"
        return v.strip()

    @field_validator("activation_mode")
    @classmethod
    def validate_activation_mode(cls, v: str) -> str:
        if v not in ("push-to-talk", "toggle"):
            return "toggle"
        return v

    @field_validator("transcription_mode")
    @classmethod
    def validate_transcription_mode(cls, v: str) -> str:
        if v not in ("streaming", "batch"):
            return "streaming"
        return v

    @field_validator("sample_rate")
    @classmethod
    def validate_sample_rate(cls, v: int) -> int:
        if v != 16000:
            return 16000
        return v

    def get_api_key(self) -> str:
        """Get API key from environment or config."""
        return os.environ.get("ELEVENLABS_API_KEY", "") or self.api_key

    @classmethod
    def get_config_dir(cls) -> Path:
        """Get the configuration directory path."""
        override = os.environ.get("ELEVENLABS_STT_CONFIG_DIR")
        if override:
            return Path(override).expanduser()
        return Path.home() / ".claude" / "plugins" / "elevenlabs-stt"

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

            config_data = data.get("elevenlabs-stt", {})

            # Migrate legacy "mode" field to new fields
            if "mode" in config_data and config_data["mode"]:
                old_mode = config_data["mode"]
                if old_mode == "streaming":
                    config_data.setdefault("transcription_mode", "streaming")
                    config_data.setdefault("activation_mode", "toggle")
                elif old_mode == "push-to-talk":
                    config_data.setdefault("transcription_mode", "batch")
                    config_data.setdefault("activation_mode", "push-to-talk")
                elif old_mode == "toggle":
                    config_data.setdefault("transcription_mode", "batch")
                    config_data.setdefault("activation_mode", "toggle")
                config_data["mode"] = ""  # Clear legacy field

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
            "elevenlabs-stt": {
                "api_key": self.api_key,
                "model_id": self.model_id,
                "language_code": self.language_code,
                "hotkey": self.hotkey,
                "activation_mode": self.activation_mode,
                "transcription_mode": self.transcription_mode,
                "sample_rate": self.sample_rate,
                "max_recording_seconds": self.max_recording_seconds,
                "output_mode": self.output_mode,
                "sound_effects": self.sound_effects,
                "streaming_vad_mode": self.streaming_vad_mode,
                "streaming_vad_silence_secs": self.streaming_vad_silence_secs,
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


def get_platform() -> str:
    """Get the current platform identifier."""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Linux":
        return "linux"
    elif system == "Windows":
        return "windows"
    return "unknown"


def is_wayland() -> bool:
    """Check if running under Wayland on Linux."""
    if get_platform() != "linux":
        return False
    return os.environ.get("XDG_SESSION_TYPE") == "wayland"
