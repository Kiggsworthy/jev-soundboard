"""The sidekick (Jev on the soundboard): judges each new slice of the conversation and fires a clip when it lands.

Only the newest slice is ever judged. While one decision is in flight, new slices pile into
the transcript window; when the decision returns, the sidekick judges the latest moment once
and skips everything in between. That keeps reactions ~1-2 s behind the conversation no
matter how fast people talk.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import numpy as np

from .board import Soundboard
from .config import Config
from .jev import Decision, Jev, build_state

log = logging.getLogger("jevboard")

# How confident the model must be that a reaction lands, per trigger level.
TRIGGER = {"chill": 0.88, "normal": 0.75, "trigger_happy": 0.6}


class AntiRepeat:
    """Remembers what played so the same clip doesn't fire twice in a row.

    It blocks the last `size` clips, but never more than half the board, so a small board
    (say, only the 15 built-ins) always has something left to choose from.
    """

    def __init__(self, size: int):
        self.size = size
        self.played: list[str] = []

    def add(self, name: str) -> None:
        self.played = (self.played + [name])[-max(self.size, 1) * 4:]

    def blocked(self, board_size: int) -> list[str]:
        limit = min(self.size, board_size // 2)
        if limit <= 0:
            return []
        recent: list[str] = []
        for name in reversed(self.played):
            if name not in recent:
                recent.append(name)
            if len(recent) == limit:
                break
        return recent

    def allows(self, name: str, board_size: int) -> bool:
        return name not in self.blocked(board_size)


@dataclass
class CostMeter:
    """Jev bills input tokens only; transcription bills per minute of committed audio."""

    input_tokens: int = 0
    audio_seconds: float = 0.0
    decisions: int = 0

    def add_decision(self, decision: Decision) -> None:
        self.decisions += 1
        self.input_tokens += decision.input_tokens

    def add_audio(self, seconds: float) -> None:
        self.audio_seconds += seconds

    def jev_usd(self, config: Config) -> float:
        return self.input_tokens * config.jev_price_per_mtok / 1e6

    def transcribe_usd(self, config: Config) -> float:
        return self.audio_seconds / 60 * config.transcribe_price_per_minute

    def usd(self, config: Config) -> float:
        return self.jev_usd(config) + self.transcribe_usd(config)


class Sidekick:
    def __init__(self, board: Soundboard, jev: Jev, config: Config,
                 play: Callable[[np.ndarray], None], busy: Callable[[], bool] = lambda: False,
                 clock: Callable[[], float] = time.monotonic):
        self.board = board
        self.jev = jev
        self.config = config
        self.play = play
        self.audio_busy = busy  # don't talk over a clip that's still playing
        self.clock = clock
        self.window: deque[tuple[float, str]] = deque()
        self.recent = AntiRepeat(config.recent)
        self.cost = CostMeter()
        self.vibe = config.vibe
        self.trigger = config.trigger
        self.enabled = True
        self.last_clip: float | None = None
        self.busy = False
        self.pending = False
        self.events: deque[str] = deque(maxlen=200)  # for the control panel
        self.on_event: Callable[[str], None] = lambda line: None
        self.on_decision: Callable[[str, Decision, float], None] = lambda line, decision, took: None

    def log(self, line: str) -> None:
        self.events.append(time.strftime("%H:%M:%S ") + line)
        self.on_event(line)

    def add(self, text: str) -> None:
        now = self.clock()
        self.window.append((now, text))
        while self.window and now - self.window[0][0] > self.config.window_seconds:
            self.window.popleft()

    async def heard(self, text: str) -> None:
        """A new slice of the conversation."""
        self.add(text)
        if not self.enabled:
            return
        if self.busy:
            self.pending = True  # judge only the newest moment once the current decision lands
            return
        self.busy = True
        try:
            while True:
                self.pending = False
                await self.decide()
                if not self.pending or not self.enabled:
                    break
        finally:
            self.busy = False

    def since_last_clip(self) -> float | None:
        return None if self.last_clip is None else self.clock() - self.last_clip

    async def decide(self) -> str | None:
        """Judge the newest line; returns the clip that fired, if any."""
        if not self.window:
            return None
        lines = [text for _, text in self.window]
        blocked = self.recent.blocked(len(self.board.entries))
        state = build_state(self.config.context, self.vibe, lines, self.since_last_clip(), blocked[:8])
        started = self.clock()
        decision = await self.jev.decide(state, self.board.menu(), blocked)
        if decision is None:
            return None
        took = self.clock() - started
        self.cost.add_decision(decision)
        self.on_decision(lines[-1], decision, took)
        return self.consider(decision, lines[-1], took)

    def consider(self, decision: Decision, line: str, took: float = 0.0) -> str | None:
        """Apply the trigger level, the minimum gap and anti-repeat; play if it all passes."""
        if not self.enabled or decision.clip is None:
            return None
        if decision.react < TRIGGER[self.trigger]:
            return None
        gap = self.since_last_clip()
        if gap is not None and gap < self.config.min_gap:
            return None
        if self.audio_busy() or not self.recent.allows(decision.clip, len(self.board.entries)):
            return None
        if not self.fire(decision.clip):
            return None
        self.log(f"⚡ {decision.clip} ({took:.2f}s, react {decision.react:.2f}) ← “{line}”")
        return decision.clip

    def fire(self, name: str, manual: bool = False) -> bool:
        samples = self.board.samples(name)
        if samples is None:
            return False
        self.play(samples)
        self.recent.add(name)
        if not manual:
            self.last_clip = self.clock()
        else:
            self.log(f"🎛️ {name} (manual)")
        return True

    async def run_preload(self) -> None:
        await asyncio.to_thread(self.board.preload)
