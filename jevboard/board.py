"""The soundboard: the built-in effects plus your own clips from `clips/index.json`.

    {
      "bruh": {"file": "bruh.mp3", "desc": "a friend says something cringe"},
      "applause": {"file": "applause.wav", "desc": "a great idea or a big win"}
    }

Only use clips you have the rights to. A clip with the same name as a built-in effect
replaces it.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .effects import DESCRIPTIONS, EFFECTS, RATE

log = logging.getLogger("jevboard.board")


@dataclass
class Clip:
    name: str
    desc: str
    file: Path | None = None  # None for a built-in effect


def load_index(clips_dir: Path) -> dict[str, Clip]:
    """Read clips/index.json. Bad entries and missing files are skipped with a warning."""
    index_path = Path(clips_dir) / "index.json"
    if not index_path.is_file():
        return {}
    try:
        raw = json.loads(index_path.read_text())
    except json.JSONDecodeError as exc:
        log.warning("%s isn't valid JSON (%s); ignoring your clips", index_path, exc)
        return {}
    if not isinstance(raw, dict):
        log.warning("%s should be an object of name -> {file, desc}; ignoring it", index_path)
        return {}
    clips: dict[str, Clip] = {}
    for name, info in raw.items():
        if not isinstance(info, dict) or not isinstance(info.get("file"), str):
            log.warning("clip %r needs a \"file\"; skipped", name)
            continue
        path = Path(clips_dir) / info["file"]
        if not path.is_file():
            log.warning("clip %r: %s not found; skipped", name, path)
            continue
        clips[str(name)] = Clip(str(name), str(info.get("desc") or name), path)
    return clips


def decode(path: Path, rate: int = RATE) -> np.ndarray:
    """Any audio file -> mono float32 at `rate`, loudness-normalized so clips match (needs ffmpeg)."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-af", "loudnorm=I=-18", "-ac", "1", "-ar", str(rate), "-f", "f32le", "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


class Soundboard:
    def __init__(self, clips_dir: Path | None = None, include_effects: bool = True):
        self.entries: dict[str, Clip] = {}
        self.cache: dict[str, np.ndarray] = {}
        if include_effects:
            self.entries.update({name: Clip(name, desc) for name, desc in DESCRIPTIONS.items()})
        if clips_dir is not None:
            clips = load_index(clips_dir)
            if clips and shutil.which("ffmpeg") is None:
                log.warning("ffmpeg isn't installed, so your %d clips can't be decoded; using built-ins only", len(clips))
                clips = {}
            self.entries.update(clips)

    def names(self) -> list[str]:
        return sorted(self.entries)

    def menu(self) -> dict[str, str]:
        """name -> when to use it, for the decision model."""
        return {name: self.entries[name].desc for name in self.names()}

    def samples(self, name: str) -> np.ndarray | None:
        entry = self.entries.get(name)
        if entry is None:
            return None
        if entry.file is None:
            return EFFECTS[name]
        if name not in self.cache:
            try:
                self.cache[name] = decode(entry.file)
            except (subprocess.CalledProcessError, OSError) as exc:
                log.warning("couldn't decode %s: %s", entry.file, exc)
                return None
        return self.cache[name]

    def preload(self) -> None:
        """Decode every clip up front so the first play isn't late."""
        for name in self.names():
            self.samples(name)
