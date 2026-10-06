"""Local audio devices (used by the `local` transport, and by the Discord transport when it
listens through the host machine).

    call audio  -> listen device -> Listener --+--> 24 kHz PCM -> transcription
    your mic    -> MicPassthrough -------------+
                                  \\
    clips -> Mixer ----------------+--> output device (the call's microphone, via a loopback device)
                  \\--> optional monitor device (your headphones)

See docs/AUDIO-SETUP.md for wiring this into FaceTime (or anything else) on macOS.
Importing this module needs PortAudio (installed with the `sounddevice` wheel on macOS/Windows).
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import sounddevice as sd

from .config import Config
from .pcm import ClipLanes, SampleBuffer, to_api


def devices() -> list[dict]:
    return [dict(info, index=index) for index, info in enumerate(sd.query_devices())]


def list_devices() -> str:
    lines = []
    for info in devices():
        kinds = []
        if info["max_input_channels"] > 0:
            kinds.append(f"in:{info['max_input_channels']}")
        if info["max_output_channels"] > 0:
            kinds.append(f"out:{info['max_output_channels']}")
        lines.append(f"{info['index']:3d}  {info['name']}  ({', '.join(kinds)})")
    return "\n".join(lines)


def find_device(name: str, kind: str) -> int | None:
    """A device index from a name fragment or a number; None means the system default."""
    if not name:
        return None
    if name.isdigit():
        return int(name)
    for info in devices():
        channels = info["max_input_channels"] if kind == "input" else info["max_output_channels"]
        if name.lower() in info["name"].lower() and channels > 0:
            return info["index"]
    raise RuntimeError(f"No {kind} audio device named like {name!r}. Run `jevboard devices` to see what's there.")


def device_name(name: str, kind: str) -> str:
    index = find_device(name, kind)
    if index is None:
        index = sd.default.device[0 if kind == "input" else 1]
    return sd.query_devices(index)["name"]


class MicPassthrough:
    """Your real mic, so you can be on the call yourself: it's mixed into the output device
    (the call hears you plus the clips) and into what Jev hears."""

    def __init__(self, config: Config):
        rate = config.device_rate
        self.to_call = SampleBuffer(limit=rate // 8)  # cap added latency at ~125 ms
        self.to_jev = SampleBuffer(limit=rate // 2)
        self.stream = sd.InputStream(
            device=find_device(config.mic_device, "input"),
            samplerate=rate,
            channels=1,
            dtype="float32",
            blocksize=rate // 100,  # 10 ms, keep it snappy
            callback=self._callback,
        )

    def _callback(self, indata, frames, time, status):  # noqa: ARG002
        mono = indata[:, 0].copy()
        self.to_call.push(mono)
        self.to_jev.push(mono)

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop()


class Listener:
    """Captures the listen device (plus your mic, if passed through) and hands API-rate PCM
    chunks to `on_audio` (on the audio thread)."""

    def __init__(self, config: Config, on_audio: Callable[[bytes], None], mic: MicPassthrough | None = None):
        self.config = config
        self.on_audio = on_audio
        self.mic = mic
        self.level = 0.0  # recent loudness
        self.stream = sd.InputStream(
            device=find_device(config.listen_device, "input"),
            samplerate=config.device_rate,
            channels=1,
            dtype="float32",
            blocksize=config.device_rate // 20,  # 50 ms
            callback=self._callback,
        )

    def _callback(self, indata, frames, time, status):  # noqa: ARG002 (sounddevice signature)
        block = indata[:, 0].copy()
        if self.mic is not None:
            block = block + self.mic.to_jev.take(len(block))
        self.level = float(np.sqrt(np.mean(block**2)))
        self.on_audio(to_api(block, self.config.device_rate, self.config.api_rate))

    def start(self):
        self.stream.start()

    def stop(self):
        self.stream.stop()


class Mixer:
    """Plays clips to the output device (and the optional monitor). Clips can overlap.
    Your mic (if passed through) goes to the main output only, never the monitor."""

    def __init__(self, config: Config, mic: MicPassthrough | None = None):
        self.config = config
        self.mic = mic
        self.muted = False
        outputs = [find_device(config.output_device, "output")]
        if config.monitor_device:
            outputs.append(find_device(config.monitor_device, "output"))
        self.lanes = [ClipLanes() for _ in outputs]
        self.streams = [
            sd.OutputStream(
                device=device,
                samplerate=config.device_rate,
                channels=1,
                dtype="float32",
                blocksize=config.device_rate // 50,  # 20 ms
                callback=self._callback_for(index),
            )
            for index, device in enumerate(outputs)
        ]

    def play(self, samples: np.ndarray) -> None:
        for lane in self.lanes:
            lane.add(samples, self.config.gain)

    def playing(self) -> bool:
        return self.lanes[0].active()

    def _callback_for(self, index: int):
        def callback(outdata, frames, time, status):  # noqa: ARG001
            block = self.lanes[index].mix(frames)
            if self.muted:
                block[:] = 0
            if index == 0 and self.mic is not None:
                block += self.mic.to_call.take(frames)  # mute silences clips, never you
            np.clip(block, -1, 1, out=block)
            outdata[:, 0] = block

        return callback

    def start(self):
        for stream in self.streams:
            stream.start()

    def stop(self):
        for stream in self.streams:
            stream.stop()
