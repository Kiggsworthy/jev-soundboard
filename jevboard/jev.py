"""The decision, made by Jev: given the last few seconds of the call, should a clip fire
right now, and which one?

Jev is TypeSafe's System One model. It doesn't write text; it answers typed questions about
a `state` with calibrated probabilities, in a fraction of a second. Each slice of speech
becomes one call with two questions asked in parallel:

    react_now  (noul)    probability that a reaction to the newest line, right now, lands
    clip       (choice)  the best-matched sound from the board, or "none"

API reference: https://docs.typesafe.ai/api
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import aiohttp

from .config import Config

log = logging.getLogger("jevboard.jev")

JEV_URL = "https://api.typesafe.ai/v1/systemone"
MAX_CHOICES = 255  # API limit on options per choice question


@dataclass
class Decision:
    react: float
    clip: str | None
    input_tokens: int = 0


def build_state(context: str, vibe: str, lines: list[str], seconds_since_last_clip: float | None,
                recently_played: list[str]) -> dict:
    return {
        "call": context,
        "vibe": vibe,
        "transcript": lines,
        "newest_line": lines[-1] if lines else "",
        "seconds_since_last_clip": None if seconds_since_last_clip is None else round(seconds_since_last_clip),
        "recently_played": recently_played,
    }


def build_questions(menu: dict[str, str], blocked: list[str] | tuple = ()) -> dict:
    """The two questions. Recently played clips are left out of the choice entirely."""
    clips = {name: desc for name, desc in menu.items() if name not in blocked}
    clips = dict(list(clips.items())[: MAX_CHOICES - 1])
    clips["none"] = "Nothing fits well enough right now."
    return {
        "react_now": {
            "type": "noul",
            "instructions": "`transcript` is a live, machine-transcribed `call`, newest line last. People talk over "
            "each other and lines can be cut off mid-sentence. Would a soundboard reaction RIGHT NOW, to "
            "`newest_line`, make the moment funnier? Follow `vibe`.",
            "criteria": {
                "true": "The newest line has something to react to: a fail, a brag, a roast, an argument, a dumb or "
                "amazing idea, a surprise, a joke that needs punctuating.",
                "false": "Nothing new to react to, filler or logistics, or the moment was already reacted to.",
            },
        },
        "clip": {
            "type": "choice",
            "instructions": "Which sound is the funniest, best-matched reaction to `newest_line`, given the rest of "
            "`transcript`? Match the meaning, not just a keyword. Follow `vibe`.",
            "criteria": clips,
        },
    }


def parse_answers(result: dict | None, allowed) -> Decision | None:
    """Jev's response -> Decision. Strict about the clip name, forgiving about everything else."""
    if not isinstance(result, dict):
        return None
    answers = result.get("answers")
    if not isinstance(answers, dict):
        return None
    react_answer = answers.get("react_now") or {}
    try:
        react = float(react_answer.get("noul", 0) if isinstance(react_answer, dict) else 0)
    except (TypeError, ValueError):
        react = 0.0
    if react != react:  # NaN
        react = 0.0
    react = min(1.0, max(0.0, react))
    clip_answer = answers.get("clip") or {}
    clip = clip_answer.get("choice") if isinstance(clip_answer, dict) else None
    if not isinstance(clip, str) or clip == "none" or clip not in set(allowed):
        clip = None
    usage = result.get("usage") or {}
    tokens = usage.get("input_tokens", 0) if isinstance(usage, dict) else 0
    return Decision(react, clip, int(tokens or 0))


class Jev:
    """A thin async client for the System One endpoint."""

    def __init__(self, config: Config):
        if not config.typesafe_api_key:
            raise RuntimeError("Jev needs TYPESAFE_API_KEY (set it in the environment or .env).")
        self.config = config
        self.session: aiohttp.ClientSession | None = None

    async def ask(self, state: dict, questions: dict) -> dict | None:
        if self.session is None:
            self.session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {self.config.typesafe_api_key}"})
        try:
            async with self.session.post(
                self.config.jev_url,
                json={"state": state, "model": self.config.jev_model, "questions": questions},
                timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            ) as response:
                if response.status != 200:
                    log.warning("jev %s: %s", response.status, (await response.text())[:200])
                    return None
                return await response.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("jev call failed: %s", exc or type(exc).__name__)
            return None

    async def decide(self, state: dict, menu: dict[str, str], blocked: list[str]) -> Decision | None:
        result = await self.ask(state, build_questions(menu, blocked))
        return parse_answers(result, [name for name in menu if name not in blocked])

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()


async def check_key(config: Config) -> tuple[bool, str]:
    """Doctor helper: list the models this key can use (no decision tokens spent)."""
    url = config.jev_url.rsplit("/", 1)[0] + "/models"
    try:
        async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {config.typesafe_api_key}"}) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return False, f"HTTP {response.status}"
                data = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return False, str(exc) or type(exc).__name__
    models = [m.get("id") or m.get("name") for m in (data.get("data") or data.get("models") or []) if isinstance(m, dict)]
    return True, ", ".join(filter(None, models)) or "ok"
