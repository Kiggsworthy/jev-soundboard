"""`jevboard doctor`: checks keys, tools, audio devices and routing before you go live.
Keys are only ever reported as set / not set.

    jevboard doctor          # offline checks
    jevboard doctor --live   # also checks the keys against the APIs (one tiny Jev call, well under a cent)
"""

from __future__ import annotations

import asyncio
import importlib.util
import platform
import shutil
import time

from .board import load_index
from .config import Config

LOOPBACK_HINTS = ("blackhole", "loopback", "soundflower", "vb-cable", "cable input", "cable output", "monitor of")
SPEAKER_HINTS = ("speaker", "display audio", "hdmi", "tv")


class Report:
    def __init__(self):
        self.errors = 0
        self.warnings = 0

    def ok(self, text: str) -> None:
        print(f"  ok    {text}")

    def warn(self, text: str) -> None:
        self.warnings += 1
        print(f"  warn  {text}")

    def fail(self, text: str) -> None:
        self.errors += 1
        print(f"  FAIL  {text}")

    def info(self, text: str) -> None:
        print(f"        {text}")


def check_keys(config: Config, report: Report) -> None:
    print("Keys")
    if config.typesafe_api_key:
        report.ok("TYPESAFE_API_KEY is set (Jev makes every clip decision)")
    else:
        report.fail("TYPESAFE_API_KEY is not set: get one at https://typesafe.ai and put it in .env")
    listens = config.transport == "local" or config.discord_listen != "off"
    if config.openai_api_key:
        report.ok("OPENAI_API_KEY is set (speech-to-text)")
    elif listens:
        report.fail("OPENAI_API_KEY is not set: speech-to-text (the only non-Jev piece) needs it")
    if config.transport == "discord":
        if config.discord_bot_token:
            report.ok("DISCORD_BOT_TOKEN is set")
        else:
            report.fail("DISCORD_BOT_TOKEN is not set: see docs/DISCORD.md")


def check_tools(config: Config, report: Report) -> None:
    print("Tools")
    if shutil.which("ffmpeg"):
        report.ok("ffmpeg found (your own clips, `jevboard clips add`)")
    else:
        report.warn("ffmpeg not found: built-in sounds still work, your own clips won't (brew install ffmpeg)")
    if shutil.which("yt-dlp") or importlib.util.find_spec("yt_dlp"):
        report.ok("yt-dlp found (clips add from a URL)")
    else:
        report.info("yt-dlp not installed (only needed for `jevboard clips add <url>`)")
    if config.transport == "discord":
        if importlib.util.find_spec("discord") is None:
            report.fail("py-cord isn't installed: uv sync --extra discord")
        else:
            import discord

            try:
                if not discord.opus.is_loaded():
                    discord.opus._load_default()
                if discord.opus.is_loaded():
                    report.ok("Opus codec loaded (Discord voice)")
                else:
                    report.fail("Opus codec not found: brew install opus (macOS) / apt install libopus0")
            except Exception:  # noqa: BLE001
                report.fail("Opus codec not found: brew install opus (macOS) / apt install libopus0")
            if importlib.util.find_spec("davey") is None:
                report.fail("davey isn't installed (Discord's DAVE encryption): uv sync --extra discord")


def check_devices(config: Config, report: Report) -> None:
    uses_local = config.transport == "local" or (config.transport == "discord" and config.discord_listen == "local")
    if not uses_local:
        return
    print("Audio devices")
    try:
        from . import audio
    except OSError as exc:
        report.fail(f"PortAudio isn't available ({exc}); on Linux: apt install libportaudio2")
        return
    names = {}
    for role, setting, kind in (("listen", config.listen_device, "input"), ("output", config.output_device, "output"),
                                ("mic", config.mic_device, "input"), ("monitor", config.monitor_device, "output")):
        if role in ("mic", "monitor") and not setting:
            continue
        if role == "output" and config.transport == "discord":
            continue  # the bot plays straight into the channel
        try:
            names[role] = audio.device_name(setting, kind)
            report.ok(f"{role:7} -> {names[role]}" + ("" if setting else "  (system default)"))
        except Exception as exc:  # noqa: BLE001
            report.fail(f"{role:7} -> {exc}")
    all_names = [d["name"] for d in audio.devices()]
    loopbacks = [n for n in all_names if any(h in n.lower() for h in LOOPBACK_HINTS)]
    if loopbacks:
        report.ok(f"loopback devices: {', '.join(sorted(set(loopbacks)))}")
    elif platform.system() == "Darwin":
        report.warn("no loopback device found: install BlackHole (brew install blackhole-2ch blackhole-16ch), "
                    "see docs/AUDIO-SETUP.md")
    listen, output = names.get("listen"), names.get("output")
    if listen and output and listen == output:
        report.fail(f"listen and output are the same device ({listen}): Jev would hear its own clips in a loop")
    if not config.listen_device:
        report.warn("listening to the default input (probably your mic): fine for a quick test, "
                    "but a call needs a loopback device (docs/AUDIO-SETUP.md)")
    if config.transport == "local" and not config.output_device:
        report.warn("clips play to your default output, so only you hear them, not the call "
                    "(set output_device to the loopback your call app uses as its mic)")
    if "mic" in names:
        if names["mic"] == listen:
            report.fail("mic_device is also the listen device: everyone would be heard twice")
        if output and not any(h in output.lower() for h in LOOPBACK_HINTS):
            report.warn(f"your mic is passed through to {output}, which isn't a loopback device: "
                        "is that really what your call app uses as its microphone?")
        monitor = names.get("monitor", "")
        if monitor and any(h in monitor.lower() for h in SPEAKER_HINTS):
            report.warn(f"monitor is {monitor} while your mic is live: use headphones or you'll get feedback")
        report.info("mic safety: with your mic passed through, wear headphones. If the call plays out of "
                    "speakers, your mic picks it up and everyone hears an echo.")


def check_clips(config: Config, report: Report) -> None:
    print("Clips")
    from .effects import DESCRIPTIONS

    clips = load_index(config.clips_dir)
    report.ok(f"{len(DESCRIPTIONS)} built-in sounds + {len(clips)} of your own from {config.clips_dir}/index.json")


async def check_live(config: Config, report: Report) -> None:
    import aiohttp

    from .jev import Jev, build_state, check_key

    print("Live")
    if config.typesafe_api_key:
        ok, detail = await check_key(config)
        (report.ok if ok else report.fail)(f"TypeSafe key accepted ({detail})" if ok else f"TypeSafe key: {detail}")
        if ok:
            jev = Jev(config)
            started = time.monotonic()
            decision = await jev.decide(build_state(config.context, config.vibe, ["he just tripped over the dog, again"],
                                                    None, []), {"sad_trombone": "a fail", "airhorn": "a big win"}, [])
            await jev.close()
            if decision is None:
                report.fail("a test decision failed (see the warning above)")
            else:
                report.ok(f"Jev answered in {time.monotonic() - started:.2f}s: react {decision.react:.2f}, "
                          f"clip {decision.clip}")
    if config.openai_api_key:
        url = f"https://api.openai.com/v1/models/{config.transcribe_model}"
        try:
            async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {config.openai_api_key}"}) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        report.ok(f"OpenAI key works and can use {config.transcribe_model}")
                    else:
                        report.fail(f"OpenAI key / {config.transcribe_model}: HTTP {response.status}")
        except Exception as exc:  # noqa: BLE001
            report.fail(f"OpenAI: {exc}")


def run(config: Config, live: bool = False) -> int:
    report = Report()
    print(f"jevboard doctor (transport: {config.transport})")
    check_keys(config, report)
    check_tools(config, report)
    check_devices(config, report)
    check_clips(config, report)
    if live:
        asyncio.run(check_live(config, report))
    print(f"\n{report.errors} problem(s), {report.warnings} warning(s)")
    return 1 if report.errors else 0
