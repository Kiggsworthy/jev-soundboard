import asyncio

import pytest

from jevboard.board import Soundboard
from jevboard.config import Config
from jevboard.jev import Decision
from jevboard.sidekick import Sidekick
from jevboard.transports.fake import FakeTransport


class FakeJev:
    """Stands in for the Jev client: returns scripted decisions, records what it was asked."""

    def __init__(self, decisions=None, delay=0.0):
        self.decisions = list(decisions or [])
        self.delay = delay
        self.calls = []

    async def decide(self, state, menu, blocked):
        self.calls.append({"state": state, "menu": menu, "blocked": list(blocked)})
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.decisions.pop(0) if self.decisions else Decision(0.0, None, 100)

    async def close(self):
        pass


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def make_sidekick():
    def make(decisions=None, delay=0.0, **overrides):
        config = Config(**overrides)
        transport = FakeTransport(config)
        clock = Clock()
        jev = FakeJev(decisions, delay)
        sidekick = Sidekick(Soundboard(None), jev, config, play=transport.play, busy=transport.playing, clock=clock)
        transport.attach(sidekick)
        return sidekick, transport, jev, clock

    return make
