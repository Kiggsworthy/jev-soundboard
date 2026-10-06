"""The `jevboard` command.

    jevboard                 start (local transport: FaceTime, Discord desktop, Zoom, ...)
    jevboard discord         start the Discord bot
    jevboard doctor [--live] check keys, tools and audio routing
    jevboard devices         list audio devices
    jevboard try "line" ...  feed text lines to Jev and see what it would play (no audio needed)
    jevboard effects         list / play / export the built-in sounds
    jevboard clips ...       add, screen and list your own clips
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import wave
from dataclasses import replace
from pathlib import Path

import numpy as np

from .config import load_config, load_dotenv


def _config(args):
    load_dotenv()
    config = load_config(Path(args.config) if args.config else None)
    if getattr(args, "trigger", None):
        config.trigger = args.trigger.replace("-", "_")
    return config


def cmd_run(args, transport_name: str | None = None) -> int:
    from . import app
    from .transports import make_transport

    config = _config(args)
    if transport_name:
        config = replace(config, transport=transport_name)
    try:
        transport = make_transport(config)
        asyncio.run(app.run(config, transport))
    except RuntimeError as exc:
        print(f"error: {exc}\nRun `jevboard doctor` for a full check.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


def cmd_doctor(args) -> int:
    from . import doctor

    config = _config(args)
    if args.discord:
        config = replace(config, transport="discord")
    return doctor.run(config, live=args.live)


def cmd_devices(args) -> int:
    from .audio import list_devices

    print(list_devices())
    print("\nPut a name fragment (or the number) in listen_device / output_device / mic_device / monitor_device.")
    return 0


def cmd_try(args) -> int:
    """Text in, decisions out: test your clip descriptions and vibe without a call."""
    from .app import build
    from .transports.fake import FakeTransport

    config = replace(_config(args), min_gap=0.0)
    transport = FakeTransport(config, receives=False)
    sidekick, _ = build(config, transport)
    if args.play:
        from .transports.local import LocalTransport

        speaker = LocalTransport(config, play_audio=True, hear_audio=False)
        speaker.start()
        sidekick.play = lambda samples: (transport.play(samples), speaker.play(samples))
    lines = args.lines or [line.strip() for line in sys.stdin if line.strip()]

    def show(line, decision, took):
        verdict = decision.clip or "none"
        print(f"{took:5.2f}s  react {decision.react:.2f}  {verdict:16}  ← {line}")

    sidekick.on_decision = show
    sidekick.on_event = lambda line: print(f"        {line}")

    async def go():
        for line in lines:
            await sidekick.heard(line)
            if args.play:
                await asyncio.sleep(1.5)
        await sidekick.jev.close()

    asyncio.run(go())
    print(f"\n{sidekick.cost.decisions} Jev decisions, ${sidekick.cost.jev_usd(config):.5f}")
    return 0


def cmd_effects(args) -> int:
    from .effects import DESCRIPTIONS, EFFECTS, RATE

    if args.export:
        out = Path(args.export)
        out.mkdir(parents=True, exist_ok=True)
        for name, samples in EFFECTS.items():
            with wave.open(str(out / f"{name}.wav"), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(RATE)
                handle.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
        print(f"wrote {len(EFFECTS)} WAVs to {out}")
        return 0
    if args.play:
        import sounddevice as sd

        names = list(EFFECTS) if args.play == "all" else [args.play]
        for name in names:
            if name not in EFFECTS:
                print(f"no effect called {name!r}")
                return 1
            print(f"▶ {name}")
            sd.play(EFFECTS[name], RATE)
            sd.wait()
            time.sleep(0.3)
        return 0
    for name, desc in DESCRIPTIONS.items():
        print(f"{name:16} {len(EFFECTS[name]) / RATE:4.1f}s  {desc}")
    return 0


def cmd_clips(args) -> int:
    from . import clips

    config = _config(args)
    if args.clips_cmd == "add":
        return clips.add(config, args.source, args.name, args.desc, args.start, args.end, args.max, not args.no_screen)
    if args.clips_cmd == "screen":
        return clips.screen_all(config, again=args.again)
    return clips.list_clips(config)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jevboard", description="A live AI soundboard, powered by Jev.")
    parser.add_argument("--config", help="TOML config file (default: ./jevboard.toml if present)")
    parser.add_argument("--trigger", choices=["chill", "normal", "trigger-happy"], help="how eager to react")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("run", help="start with the local transport (default)")
    sub.add_parser("discord", help="start the Discord bot")
    doctor = sub.add_parser("doctor", help="check keys, tools and audio routing")
    doctor.add_argument("--live", action="store_true", help="also test the keys against the APIs")
    doctor.add_argument("--discord", action="store_true", help="check the Discord setup")
    sub.add_parser("devices", help="list audio devices")
    tryit = sub.add_parser("try", help="feed text lines to Jev and see what it would play")
    tryit.add_argument("lines", nargs="*", help="lines of conversation (or pipe them in)")
    tryit.add_argument("--play", action="store_true", help="also play the clips on your speakers")
    effects = sub.add_parser("effects", help="list, play or export the built-in sounds")
    effects.add_argument("--play", metavar="NAME", help="play one (or 'all') on your default output")
    effects.add_argument("--export", metavar="DIR", help="write them all as WAV files")
    clips = sub.add_parser("clips", help="add, screen and list your own clips")
    clips_sub = clips.add_subparsers(dest="clips_cmd")
    add = clips_sub.add_parser("add", help="cut a clip from a file or URL and add it")
    add.add_argument("source", help="an audio/video file, or a URL (needs yt-dlp)")
    add.add_argument("--name", required=True, help="lower_snake_case name")
    add.add_argument("--desc", required=True, help="when to use it: this is what Jev matches against")
    add.add_argument("--start", type=float, help="start, in seconds")
    add.add_argument("--end", type=float, help="end, in seconds")
    add.add_argument("--max", type=float, default=4.0, help="longest allowed clip (default 4 s)")
    add.add_argument("--no-screen", action="store_true", help="skip the swearing screen (listen yourself!)")
    screen = clips_sub.add_parser("screen", help="transcribe and screen clips not screened yet")
    screen.add_argument("--again", action="store_true", help="re-screen everything")
    clips_sub.add_parser("list", help="list built-in and your own sounds")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("websockets", "aiohttp.access", "discord"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    handlers = {"run": cmd_run, None: cmd_run, "discord": lambda a: cmd_run(a, "discord"), "doctor": cmd_doctor,
                "devices": cmd_devices, "try": cmd_try, "effects": cmd_effects, "clips": cmd_clips}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
