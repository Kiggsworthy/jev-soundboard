"""Bring-your-own clips: add, screen and list them. See docs/BUILD-YOUR-CLIP-LIBRARY.md.

    jevboard clips add ~/Downloads/applause.wav --name applause --desc "a great idea or a big win"
    jevboard clips add "https://..." --start 12.3 --end 14.9 --name bruh --desc "..."   # needs yt-dlp
    jevboard clips screen        # (re)screen everything not screened yet
    jevboard clips list

Only add clips you have the right to use. Nothing in clips/ is committed to git.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import aiohttp

from .config import Config

# Family-safe by default: hard swearing, slurs, sexual content, and self-harm taunts.
# Add your own patterns (one regex per line) in clips/banned.txt.
BANNED = [
    r"\bf+u+c+k", r"\bmotherf", r"\bs+h+i+t+", r"\bbitch", r"\bcunt", r"\bcock\b", r"\bpussy",
    r"\bdick\b", r"\bfag", r"\bnigg", r"\bretard", r"\bslut", r"\bwhore", r"\bporn",
    r"\bsex(y|ual)?\b", r"\bkill yourself", r"\bkys\b",
]
TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"
NAME = re.compile(r"^[a-z0-9][a-z0-9_]{0,40}$")


def banned_patterns(clips_dir: Path) -> list[str]:
    extra = clips_dir / "banned.txt"
    patterns = list(BANNED)
    if extra.is_file():
        patterns += [line.strip() for line in extra.read_text().splitlines() if line.strip() and not line.startswith("#")]
    return patterns


def screen_text(text: str, patterns: list[str]) -> list[str]:
    """Patterns that matched (empty means the clip is clean)."""
    return [pattern for pattern in patterns if re.search(pattern, text, re.I)]


def read_index(clips_dir: Path) -> dict:
    path = clips_dir / "index.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def write_index(clips_dir: Path, index: dict) -> None:
    (clips_dir / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n")


def is_url(source: str) -> bool:
    return source.startswith(("http://", "https://"))


def fetch(url: str, folder: Path, start: float | None, end: float | None) -> Path:
    """Download just the audio (and just the section, if given) with yt-dlp."""
    command = [shutil.which("yt-dlp") or "", "-q", "--no-warnings", "--no-playlist", "-x", "--audio-format", "wav",
               "-o", str(folder / "source.%(ext)s")]
    if not command[0]:
        command[:1] = [sys.executable, "-m", "yt_dlp"]
    if start is not None or end is not None:
        command += ["--download-sections", f"*{start or 0}-{end if end is not None else 'inf'}", "--force-keyframes-at-cuts"]
    subprocess.run(command + [url], check=True)
    found = sorted(folder.glob("source.*"))
    if not found:
        raise RuntimeError("yt-dlp didn't produce a file")
    return found[0]


def cut(source: Path, target: Path, start: float | None, end: float | None, max_seconds: float) -> None:
    """Trim, drop leading silence, cap the length, fade the tail, normalize loudness, mono 48 kHz."""
    length = max_seconds if end is None or start is None else min(max_seconds, end - start)
    fade = min(0.25, length / 4)
    filters = ",".join([
        "silenceremove=start_periods=1:start_threshold=-45dB",
        f"atrim=0:{length}",
        f"afade=t=out:st={max(0.0, length - fade)}:d={fade}",
        "loudnorm=I=-18:TP=-1.5",
    ])
    command = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        command += ["-ss", str(start)]
    command += ["-i", str(source), "-af", filters, "-ac", "1", "-ar", "48000", "-b:a", "128k", str(target)]
    subprocess.run(command, check=True)
    if not target.exists() or target.stat().st_size < 2000:
        target.unlink(missing_ok=True)
        raise RuntimeError("the clip came out empty (all silence?); check --start/--end")


async def transcribe(config: Config, path: Path) -> str:
    """OpenAI speech-to-text, used only for screening."""
    form = aiohttp.FormData()
    form.add_field("model", config.transcribe_model)
    form.add_field("response_format", "text")
    form.add_field("file", path.read_bytes(), filename=path.name)
    headers = {"Authorization": f"Bearer {config.openai_api_key}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        for attempt in range(3):
            async with session.post(TRANSCRIBE_URL, data=form, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status == 200:
                    return (await response.text()).strip()
            await asyncio.sleep(2 * (attempt + 1))
    raise RuntimeError(f"transcription failed for {path.name}")


def screen_one(config: Config, path: Path) -> tuple[str, list[str]]:
    text = asyncio.run(transcribe(config, path))
    return text, screen_text(text, banned_patterns(config.clips_dir))


def reject(clips_dir: Path, path: Path) -> None:
    rejected = clips_dir / "rejected"
    rejected.mkdir(exist_ok=True)
    path.rename(rejected / path.name)


def add(config: Config, source: str, name: str, desc: str, start: float | None, end: float | None,
        max_seconds: float, screen: bool) -> int:
    if not NAME.match(name):
        print("Name clips in lower_snake_case: letters, digits and underscores.")
        return 2
    if shutil.which("ffmpeg") is None:
        print("ffmpeg is required (macOS: brew install ffmpeg).")
        return 2
    if screen and not config.openai_api_key:
        print("Screening needs OPENAI_API_KEY. Set it, or pass --no-screen and listen to the clip yourself.")
        return 2
    clips_dir = config.clips_dir
    clips_dir.mkdir(parents=True, exist_ok=True)
    target = clips_dir / f"{name}.mp3"
    with tempfile.TemporaryDirectory() as tmp:
        if is_url(source):
            local = fetch(source, Path(tmp), start, end)
            section = (end - (start or 0)) if end is not None else None
            cut(local, target, 0.0 if section is not None else None, section, max_seconds)
        else:
            cut(Path(source).expanduser(), target, start, end, max_seconds)
    entry = {"file": target.name, "desc": desc, "source": source if is_url(source) else Path(source).name}
    if screen:
        text, hits = screen_one(config, target)
        entry["heard"] = text
        if hits:
            reject(clips_dir, target)
            print(f"REJECTED {name}: heard {text!r} (matched {', '.join(hits)}). Moved to clips/rejected/.")
            return 1
        print(f"screened  {name}: heard {text!r}")
    index = read_index(clips_dir)
    index[name] = entry
    write_index(clips_dir, index)
    print(f"added     {name} -> {target}  ({len(index)} clips in clips/index.json)")
    return 0


def screen_all(config: Config, again: bool = False) -> int:
    if not config.openai_api_key:
        print("Screening needs OPENAI_API_KEY.")
        return 2
    clips_dir = config.clips_dir
    index = read_index(clips_dir)
    patterns = banned_patterns(clips_dir)
    rejected = 0
    for name, info in list(index.items()):
        path = clips_dir / info.get("file", "")
        if not path.is_file():
            print(f"missing   {name}: {path} (removed from the index)")
            del index[name]
            continue
        if "heard" in info and not again:
            continue
        text = asyncio.run(transcribe(config, path))
        info["heard"] = text
        hits = screen_text(text, patterns)
        if hits:
            reject(clips_dir, path)
            del index[name]
            rejected += 1
            print(f"REJECTED  {name}: {text!r}")
        else:
            print(f"ok        {name}: {text!r}")
        write_index(clips_dir, index)
    write_index(clips_dir, index)
    print(f"{len(index)} clips passed, {rejected} rejected")
    return 0


def list_clips(config: Config) -> int:
    from .effects import DESCRIPTIONS

    index = read_index(config.clips_dir)
    print(f"Built-in ({len(DESCRIPTIONS)}):")
    for name, desc in DESCRIPTIONS.items():
        print(f"  {name:16} {desc}")
    print(f"\nYours ({len(index)}, from {config.clips_dir / 'index.json'}):")
    for name, info in index.items():
        flag = "" if "heard" in info else "  [not screened]"
        print(f"  {name:16} {info.get('desc', '')}{flag}")
    return 0
