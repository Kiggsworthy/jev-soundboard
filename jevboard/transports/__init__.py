"""Transports: how audio gets in and how clips get out. The rest of jevboard (Jev's decision
loop, the clip index, the panel, the cost meter) doesn't know or care which one is running.

    local    system audio devices + loopback (FaceTime, Discord desktop, Zoom, a stream, ...)
    discord  a bot in a Discord voice channel, driven by slash commands
    fake     in-memory, for tests and `jevboard try`

A transport is small:

    on_audio(pcm)   set by the app; the transport calls it with 24 kHz mono int16 bytes
    receives_audio  whether it will call on_audio at all (if not, no transcriber is started)
    play(samples)   48 kHz mono float32 clip audio out
    playing()       is a clip still sounding?
    muted           silence clip output
    attach(sk)      gets the Sidekick, for transports with their own controls (slash commands)
    run() / close() lifecycle
"""

from __future__ import annotations

import asyncio
from typing import Callable

import numpy as np

from ..config import Config


class Transport:
    name = "base"

    def __init__(self, config: Config):
        self.config = config
        self.on_audio: Callable[[bytes], None] = lambda pcm: None
        self.muted = False
        self.sidekick = None

    @property
    def receives_audio(self) -> bool:
        return False

    def attach(self, sidekick) -> None:
        self.sidekick = sidekick

    def play(self, samples: np.ndarray) -> None:
        raise NotImplementedError

    def playing(self) -> bool:
        return False

    async def run(self) -> None:
        await asyncio.Event().wait()

    async def close(self) -> None:
        pass


def make_transport(config: Config) -> Transport:
    if config.transport == "local":
        from .local import LocalTransport

        return LocalTransport(config)
    if config.transport == "discord":
        from .discord_bot import DiscordTransport

        return DiscordTransport(config)
    if config.transport == "fake":
        from .fake import FakeTransport

        return FakeTransport(config)
    raise RuntimeError(f"Unknown transport {config.transport!r}; options: local, discord")
