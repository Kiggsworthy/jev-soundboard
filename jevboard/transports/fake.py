"""An in-memory transport for tests and `jevboard try`: records what it was asked to play."""

from __future__ import annotations

import numpy as np

from . import Transport


class FakeTransport(Transport):
    name = "fake"

    def __init__(self, config, receives: bool = True):
        super().__init__(config)
        self.receives = receives
        self.played: list[np.ndarray] = []
        self.busy = False

    @property
    def receives_audio(self) -> bool:
        return self.receives

    def play(self, samples: np.ndarray) -> None:
        if not self.muted:
            self.played.append(samples)

    def playing(self) -> bool:
        return self.busy

    def feed(self, pcm: bytes) -> None:
        """Pretend audio arrived."""
        self.on_audio(pcm)
