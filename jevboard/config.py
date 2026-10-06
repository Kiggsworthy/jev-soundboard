"""Settings. Every knob can come from an env var (JEVBOARD_<NAME>), a TOML config file
(`jevboard.toml` in the current folder, or --config PATH), or the default below, in that
order of precedence.

    JEVBOARD_TRIGGER=chill jevboard
    jevboard --config family-call.toml

API keys come from the environment (or a local `.env`), never from code.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

DEFAULT_CONTEXT = "a live FaceTime call between friends"
DEFAULT_VIBE = "be a funny hype sidekick: punctuate jokes, roast fails and brags, celebrate wins and great ideas"


@dataclass
class Config:
    # What the sidekick is listening to, and how it should behave.
    context: str = DEFAULT_CONTEXT
    vibe: str = DEFAULT_VIBE
    trigger: str = "normal"  # chill | normal | trigger_happy

    # Jev, the decision model: one fast typed call per slice of speech.
    jev_url: str = "https://api.typesafe.ai/v1/systemone"
    jev_model: str = "jev-latest"
    timeout: float = 3.0  # seconds; a late answer is a useless answer
    jev_price_per_mtok: float = 0.042  # USD per million input tokens (output is free), for the cost meter

    # Speech-to-text (the only non-Jev piece; see jevboard/transcribe.py).
    transcriber: str = "openai-realtime"
    transcribe_model: str = "gpt-4o-mini-transcribe"
    transcribe_price_per_minute: float = 0.003
    language: str = "en"

    # Timing and anti-repeat.
    slice_seconds: float = 1.2  # transcribe on a fixed clock, not on pauses
    window_seconds: float = 25.0  # how much recent conversation the model sees
    silence_rms: float = 300.0  # int16 RMS; quieter slices are dropped instead of transcribed
    min_gap: float = 4.0  # seconds between automatic clips
    recent: int = 25  # how many recently played clips can't repeat (capped at half the board)

    # How audio gets in and out: "local" (system audio devices: FaceTime, Discord desktop, Zoom,
    # anything) or "discord" (a bot in a Discord voice channel). See jevboard/transports/.
    transport: str = "local"

    # Discord bot (docs/DISCORD.md).
    discord_command: str = "soundboard"  # the slash-command group: /soundboard join, /soundboard vibe ...
    discord_listen: str = "local"  # local | native (experimental, see docs/DISCORD.md) | off (manual buttons only)
    discord_guild_ids: str = ""  # optional comma-separated server IDs: commands show up instantly there

    # Audio devices: a name fragment ("BlackHole 2ch"), an index, or empty for the system default.
    # See docs/audio-setup.md. `jevboard devices` lists them; `jevboard doctor` checks them.
    listen_device: str = ""  # where the call's audio arrives (e.g. a loopback device)
    output_device: str = ""  # where clips go (e.g. a loopback device the call uses as its mic)
    mic_device: str = ""  # optional: your real mic, passed through into output_device and heard by Jev
    monitor_device: str = ""  # optional: your headphones, so you hear the clips too
    device_rate: int = 48000
    api_rate: int = 24000  # what the Realtime API wants
    gain: float = 0.9

    # Files.
    clips_dir: Path = Path("clips")
    state_dir: Path = Path("state")

    # Control panel.
    panel_host: str = "127.0.0.1"  # set 0.0.0.0 to reach it from your phone on the same network
    panel_port: int = 8787

    # Keys: environment only, never echoed.
    typesafe_api_key: str = field(default="", repr=False)  # TYPESAFE_API_KEY
    openai_api_key: str = field(default="", repr=False)  # OPENAI_API_KEY (transcription only)
    discord_bot_token: str = field(default="", repr=False)  # DISCORD_BOT_TOKEN (Discord transport only)

    def guild_ids(self) -> list[int]:
        return [int(part) for part in self.discord_guild_ids.replace(" ", "").split(",") if part.isdigit()]


SECRET_ENV = {"typesafe_api_key": "TYPESAFE_API_KEY", "openai_api_key": "OPENAI_API_KEY",
              "discord_bot_token": "DISCORD_BOT_TOKEN"}


def load_dotenv(path: Path = Path(".env")) -> None:
    """Load KEY=value lines into os.environ (existing variables win). Values are never printed."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def _coerce(value, default):
    if isinstance(default, bool):
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(default, int):
        return int(value)
    if isinstance(default, float):
        return float(value)
    if isinstance(default, Path):
        return Path(value).expanduser()
    return str(value)


def load_config(path: Path | None = None, env: dict | None = None) -> Config:
    """Defaults <- config file <- environment."""
    env = os.environ if env is None else env
    values: dict = {}
    if path is None and Path("jevboard.toml").is_file():
        path = Path("jevboard.toml")
    if path is not None:
        data = tomllib.loads(Path(path).read_text())
        values.update(data.get("jevboard", data))
    for secret in SECRET_ENV:
        values.pop(secret, None)  # keys come from the environment only
    defaults = Config()
    kwargs = {}
    for f in fields(Config):
        default = getattr(defaults, f.name)
        if f.name in SECRET_ENV:
            raw = env.get(SECRET_ENV[f.name])
        else:
            raw = env.get(f"JEVBOARD_{f.name.upper()}", values.get(f.name))
        if raw is not None and raw != "":
            kwargs[f.name] = _coerce(raw, default)
    config = Config(**kwargs)
    config.trigger = config.trigger.replace("-", "_")
    if config.trigger not in ("chill", "normal", "trigger_happy"):
        raise ValueError(f"trigger must be chill, normal or trigger-happy (got {config.trigger!r})")
    if config.discord_listen not in ("local", "native", "off"):
        raise ValueError(f"discord_listen must be local, native or off (got {config.discord_listen!r})")
    return config
