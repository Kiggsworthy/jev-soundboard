"""The `local` transport: system audio devices. Works with anything that can use a loopback
device: FaceTime, the Discord desktop app, Zoom, Meet in a browser, OBS. See docs/AUDIO-SETUP.md.
"""

from __future__ import annotations

import asyncio

import numpy as np

from . import Transport


class LocalTransport(Transport):
    name = "local"

    def __init__(self, config, play_audio: bool = True, hear_audio: bool = True):
        super().__init__(config)
        from ..audio import Listener, MicPassthrough, Mixer  # needs PortAudio, so imported lazily

        self.mic = MicPassthrough(config) if (config.mic_device and play_audio) else None
        self.mixer = Mixer(config, self.mic) if play_audio else None
        self.listener = Listener(config, lambda pcm: self.on_audio(pcm), self.mic) if hear_audio else None

    @property
    def receives_audio(self) -> bool:
        return self.listener is not None

    @property
    def muted(self) -> bool:
        return bool(self.mixer and self.mixer.muted)

    @muted.setter
    def muted(self, value: bool) -> None:
        if getattr(self, "mixer", None) is not None:
            self.mixer.muted = value

    def play(self, samples: np.ndarray) -> None:
        if self.mixer is not None:
            self.mixer.play(samples)

    def playing(self) -> bool:
        return bool(self.mixer and self.mixer.playing())

    def start(self) -> None:
        for part in (self.mic, self.mixer, self.listener):
            if part is not None:
                part.start()

    async def run(self) -> None:
        self.start()
        await asyncio.Event().wait()

    async def close(self) -> None:
        for part in (self.listener, self.mixer, self.mic):
            if part is not None:
                part.stop()
