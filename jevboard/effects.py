"""Built-in sound effects, synthesized with numpy, so the board works with zero clip files
and ships no audio anyone else owns.

Each effect has a description; the decision model reads those to pick the right one.
"""

from __future__ import annotations

import numpy as np

RATE = 48000


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(RATE * seconds)) / RATE


def _tone(freq: float, seconds: float, shape: str = "sine", volume: float = 0.5) -> np.ndarray:
    t = _t(seconds)
    if shape == "square":
        wave = np.sign(np.sin(2 * np.pi * freq * t))
    elif shape == "saw":
        wave = 2 * (t * freq % 1) - 1
    else:
        wave = np.sin(2 * np.pi * freq * t)
    fade = np.minimum(1, np.minimum(t, seconds - t) * 80)  # no clicks
    return wave * fade * volume


def _glide(freq: np.ndarray) -> np.ndarray:
    """A sine whose pitch follows `freq` sample by sample."""
    return np.sin(2 * np.pi * np.cumsum(freq) / RATE)


def _sweep(start: float, end: float, seconds: float, volume: float = 0.4) -> np.ndarray:
    t = _t(seconds)
    return _glide(np.linspace(start, end, len(t))) * volume * np.minimum(1, (seconds - t) * 8)


def _noise_hit(seconds: float, volume: float = 0.6, decay: float = 30) -> np.ndarray:
    t = _t(seconds)
    return np.random.default_rng(len(t)).uniform(-1, 1, len(t)) * np.exp(-t * decay) * volume


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(RATE * seconds))


def _finish(wave: np.ndarray, peak: float = 0.9) -> np.ndarray:
    top = float(np.max(np.abs(wave))) if wave.size else 0.0
    if top > peak:
        wave = wave * (peak / top)
    return wave.astype(np.float32)


def buzzer():
    return _tone(110, 1.1, "square", 0.35) + _tone(116, 1.1, "square", 0.25)


def bleep():
    return _tone(1000, 0.7, "sine", 0.45)


def airhorn():
    blast = sum(_tone(f, 0.35, "saw", 0.18) for f in (440, 554, 659))
    hold = sum(_tone(f, 1.0, "saw", 0.18) for f in (440, 554, 659))
    return np.concatenate([blast, _silence(0.06), blast, _silence(0.06), hold])


def sad_trombone():
    return np.concatenate([_sweep(f, f * 0.94, 0.45 if i < 3 else 1.2) for i, f in enumerate((392, 370, 349, 330))])


def rimshot():
    return np.concatenate([_noise_hit(0.12), _silence(0.08), _noise_hit(0.12), _noise_hit(0.5, 0.8)])


def drumroll():
    return np.concatenate([_noise_hit(0.05, 0.4) for _ in range(40)] + [_noise_hit(0.6, 0.9)])


def ding():
    return _tone(1318, 0.5, "sine", 0.4) * np.exp(-_t(0.5) * 6)


def boing():
    t = _t(0.7)
    freq = 220 + 160 * (1 - np.exp(-t * 6)) + 60 * np.sin(2 * np.pi * 14 * t) * np.exp(-t * 3)
    return _glide(freq) * np.exp(-t * 3.5) * 0.6


def slide_whistle():
    t = _t(0.9)
    freq = np.linspace(1800, 450, len(t)) * (1 + 0.02 * np.sin(2 * np.pi * 6 * t))
    return _glide(freq) * np.minimum(1, np.minimum(t * 30, (0.9 - t) * 10)) * 0.4


def tada():
    pickup = sum(_tone(f, 0.12, "saw", 0.12) for f in (523, 659))
    chord = sum(_tone(f, 1.1, "saw", 0.12) for f in (523, 659, 784, 1047)) * np.exp(-_t(1.1) * 1.5)
    return np.concatenate([pickup, _silence(0.05), chord])


def crickets():
    chirp = _tone(4600, 0.018, "sine", 0.3)
    group = np.concatenate([np.concatenate([chirp, _silence(0.025)]) for _ in range(4)])
    return np.concatenate([np.concatenate([group, _silence(0.45)]) for _ in range(3)])


def boom():
    t = _t(1.2)
    thump = _glide(np.geomspace(140, 38, len(t))) * np.exp(-t * 2.2) * 0.9
    return thump + np.concatenate([_noise_hit(0.04, 0.3, 80), np.zeros(len(t) - int(RATE * 0.04))])


def level_up():
    notes = [_tone(f, 0.08, "square", 0.18) for f in (523, 659, 784, 1047, 1319)]
    return np.concatenate(notes + [_tone(1568, 0.35, "square", 0.18) * np.exp(-_t(0.35) * 5)])


def bonk():
    t = _t(0.22)
    knock = _glide(np.linspace(700, 260, len(t))) * np.exp(-t * 22) * 0.8
    return knock + np.concatenate([_noise_hit(0.03, 0.4, 120), np.zeros(len(t) - int(RATE * 0.03))])


def record_scratch():
    t = _t(0.55)
    freq = 250 + 900 * np.abs(np.sin(np.pi * t / 0.55 * 1.5))
    scratch = np.sign(_glide(freq)) * 0.15 + _noise_hit(0.55, 0.35, 2)
    return scratch * np.minimum(1, (0.55 - t) * 20)


# name -> (generator, when the model should use it)
CATALOG: dict[str, tuple] = {
    "buzzer": (buzzer, "Wrong-answer buzzer: a bad take, a wrong guess, a rejected idea."),
    "airhorn": (airhorn, "Hype airhorn: an epic play, a big win, a brag that's actually earned."),
    "sad_trombone": (sad_trombone, "Wah-wah-wah-waaah: a fail, a loss, a plan that fell apart."),
    "rimshot": (rimshot, "Ba-dum-tss: right after a joke, a pun, or a cheesy line."),
    "drumroll": (drumroll, "Drumroll: build suspense before a reveal, a result, or a big decision."),
    "ding": (ding, "Correct-answer ding: someone's right, a good point, a smart idea."),
    "bleep": (bleep, "Censor bleep: someone almost says something they shouldn't."),
    "boing": (boing, "Cartoon boing: something goofy, bouncy, or ridiculous."),
    "slide_whistle": (slide_whistle, "Falling slide whistle: someone falls, drops, or their plan goes downhill."),
    "tada": (tada, "Ta-da fanfare: a reveal, a finished thing, a proud moment."),
    "crickets": (crickets, "Crickets: a joke that bombed, or awkward silence."),
    "boom": (boom, "Dramatic boom: a shocking statement, a savage roast, a mic-drop moment."),
    "level_up": (level_up, "Level-up jingle: someone improves, wins a point, gets an upgrade."),
    "bonk": (bonk, "Bonk: someone said something dumb, or got hit."),
    "record_scratch": (record_scratch, "Record scratch: wait, what did you just say? A sudden plot twist."),
}

EFFECTS: dict[str, np.ndarray] = {name: _finish(make()) for name, (make, _) in CATALOG.items()}
DESCRIPTIONS: dict[str, str] = {name: desc for name, (_, desc) in CATALOG.items()}
