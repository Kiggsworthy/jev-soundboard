"""Wires the transport-agnostic core together: the board, Jev, the sidekick, the transcriber
and the control panel, around whichever transport carries the audio."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from .board import Soundboard
from .config import Config
from .jev import Jev
from .panel import make_app, panel_token
from .sidekick import Sidekick
from .transcribe import make_transcriber
from .transports import Transport

log = logging.getLogger("jevboard")


def build(config: Config, transport: Transport) -> tuple[Sidekick, object | None]:
    board = Soundboard(config.clips_dir)
    sidekick = Sidekick(board, Jev(config), config, play=transport.play, busy=transport.playing)
    transport.attach(sidekick)
    transcriber = None
    if transport.receives_audio:
        transcriber = make_transcriber(config, sidekick.heard, sidekick.cost.add_audio)
        transport.on_audio = transcriber.hear
    return sidekick, transcriber


async def run(config: Config, transport: Transport) -> None:
    sidekick, transcriber = build(config, transport)
    sidekick.on_event = lambda line: log.info("%s", line)
    log.info("%d sounds on the board (%d built-in)", len(sidekick.board.entries),
             sum(1 for clip in sidekick.board.entries.values() if clip.file is None))

    token = panel_token(config.state_dir)
    runner = web.AppRunner(make_app(sidekick, token, transport, transcriber))
    await runner.setup()
    await web.TCPSite(runner, config.panel_host, config.panel_port).start()
    host = "localhost" if config.panel_host in ("127.0.0.1", "0.0.0.0") else config.panel_host
    print(f"Control panel: http://{host}:{config.panel_port}/?t={token}", flush=True)

    tasks = [transport.run(), sidekick.run_preload()]
    if transcriber is not None:
        tasks.append(transcriber.run())
    try:
        await asyncio.gather(*tasks)
    finally:
        await transport.close()
        await sidekick.jev.close()
        await runner.cleanup()
