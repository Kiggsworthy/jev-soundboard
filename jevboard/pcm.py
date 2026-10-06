"""Pure audio helpers (no audio-device imports), shared by every transport."""

from __future__ import annotations

import threading

import numpy as np


def rms(pcm: bytes) -> float:
    """Loudness of int16 PCM bytes."""
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0


def resample(mono: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or len(mono) == 0:
        return mono
    if src == 2 * dst:  # the usual 48k -> 24k: average pairs
        return mono[: len(mono) // 2 * 2].reshape(-1, 2).mean(axis=1)
    count = int(round(len(mono) * dst / src))
    return np.interp(np.linspace(0, len(mono) - 1, count), np.arange(len(mono)), mono)


def to_api(block: np.ndarray, src: int, dst: int) -> bytes:
    """Device float (frames, channels) -> mono int16 bytes at the API rate."""
    mono = block.mean(axis=1) if block.ndim == 2 else block
    return (np.clip(resample(mono, src, dst), -1, 1) * 32767).astype(np.int16).tobytes()


class SampleBuffer:
    """A small thread-safe FIFO of float samples that drops the oldest audio past `limit`."""

    def __init__(self, limit: int):
        self.limit = limit
        self.lock = threading.Lock()
        self.data = np.zeros(0, dtype=np.float32)

    def push(self, samples: np.ndarray) -> None:
        with self.lock:
            self.data = np.concatenate([self.data, samples.astype(np.float32)])[-self.limit:]

    def take(self, count: int) -> np.ndarray:
        """Exactly `count` samples (zero-padded if short)."""
        with self.lock:
            out, self.data = self.data[:count], self.data[count:]
        if len(out) < count:
            out = np.concatenate([out, np.zeros(count - len(out), dtype=np.float32)])
        return out


def float_to_stereo_s16(mono: np.ndarray) -> bytes:
    """Mono float -> interleaved stereo int16 bytes (what Discord voice wants)."""
    clipped = (np.clip(mono, -1, 1) * 32767).astype(np.int16)
    return np.repeat(clipped, 2).tobytes()


def stereo_s16_to_float(pcm: bytes) -> np.ndarray:
    """Interleaved stereo int16 bytes -> mono float."""
    samples = np.frombuffer(pcm[: len(pcm) // 4 * 4], dtype=np.int16).astype(np.float32) / 32768
    return samples.reshape(-1, 2).mean(axis=1) if samples.size else samples


class ClipLanes:
    """Overlapping clips mixed into fixed-size blocks. Thread-safe: `add` from anywhere,
    `mix` from the audio thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.clips: list[list] = []  # [samples, position]

    def add(self, samples: np.ndarray, gain: float = 1.0) -> None:
        with self.lock:
            self.clips.append([samples.astype(np.float32) * gain, 0])

    def active(self) -> bool:
        with self.lock:
            return bool(self.clips)

    def mix(self, frames: int) -> np.ndarray:
        block = np.zeros(frames, dtype=np.float32)
        with self.lock:
            still = []
            for clip in self.clips:
                samples, pos = clip
                chunk = samples[pos: pos + frames]
                block[: len(chunk)] += chunk
                clip[1] = pos + frames
                if clip[1] < len(samples):
                    still.append(clip)
            self.clips = still
        return block

    def clear(self) -> None:
        with self.lock:
            self.clips = []


class RoomMixer:
    """Many speakers' audio (e.g. one stream per Discord user) mixed into one "room" stream,
    so a single transcription slice hears everyone. Thread-safe."""

    def __init__(self, rate: int = 48000, max_seconds: float = 0.5):
        self.lock = threading.Lock()
        self.limit = int(rate * max_seconds)
        self.buffers: dict[object, np.ndarray] = {}

    def add(self, speaker: object, samples: np.ndarray) -> None:
        with self.lock:
            buffer = self.buffers.get(speaker)
            joined = samples.astype(np.float32) if buffer is None else np.concatenate([buffer, samples.astype(np.float32)])
            self.buffers[speaker] = joined[-self.limit:]  # a stalled reader never builds up lag

    def speakers(self) -> int:
        with self.lock:
            return len(self.buffers)

    def drain(self, frames: int) -> np.ndarray:
        """The next `frames` samples of everyone at once (silence where nobody spoke)."""
        block = np.zeros(frames, dtype=np.float32)
        with self.lock:
            for speaker in list(self.buffers):
                buffer = self.buffers[speaker]
                take = buffer[:frames]
                block[: len(take)] += take
                rest = buffer[frames:]
                if len(rest):
                    self.buffers[speaker] = rest
                else:
                    del self.buffers[speaker]
        return block
