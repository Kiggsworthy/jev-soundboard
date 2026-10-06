"""Speech-to-text: the only piece of jevboard that isn't Jev (Jev reads text, not audio).

A transcriber takes raw call audio through `hear(pcm)` (24 kHz mono int16, from the audio
thread), calls `on_text(line)` with each new slice of speech, and exposes `connected`.
The default is OpenAI's Realtime transcription; register others in TRANSCRIBERS.

Streaming transcription on a fixed clock.

When several people talk over each other there are no clean pauses, so waiting for the end
of a sentence (voice-activity detection) means waiting forever. Instead, audio streams to an
OpenAI Realtime transcription session continuously and gets committed every `slice_seconds`
(~1.2 s), so text keeps arriving about once a second however chaotic the call gets. Quiet
slices are cleared instead of committed, so silence costs nothing.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Awaitable, Callable

import websockets

from .config import Config
from .pcm import rms

log = logging.getLogger("jevboard.transcribe")

REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"
SESSION_LIMIT = 55 * 60  # sessions cap at 60 minutes; hop to a fresh one before that


class OpenAIRealtime:
    """Call audio (24 kHz mono int16) -> text, in fixed-length slices."""

    def __init__(self, config: Config, on_text: Callable[[str], Awaitable[None]],
                 on_audio_seconds: Callable[[float], None] = lambda seconds: None):
        if not config.openai_api_key:
            raise RuntimeError("Transcription needs OPENAI_API_KEY (set it in the environment or .env).")
        self.config = config
        self.on_text = on_text
        self.on_audio_seconds = on_audio_seconds
        self.queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=400)
        self.loop: asyncio.AbstractEventLoop | None = None
        self.ws = None
        self.connected = False

    def hear(self, pcm: bytes) -> None:
        """Called from the audio thread."""
        if self.loop is None:
            return

        def put():
            if not self.queue.full():
                self.queue.put_nowait(pcm)

        self.loop.call_soon_threadsafe(put)

    async def _send(self, event: dict) -> None:
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps(event))
            except websockets.ConnectionClosed:
                pass

    async def _slicer(self) -> None:
        """Forward audio as it comes; every slice_seconds, commit it (or drop it if it was quiet)."""
        bytes_per_second = self.config.api_rate * 2
        started, loud, sent = time.monotonic(), 0.0, 0
        while True:
            try:
                pcm = await asyncio.wait_for(self.queue.get(), timeout=0.2)
            except asyncio.TimeoutError:
                pcm = None
            if pcm and self.ws is not None:
                loud = max(loud, rms(pcm))
                sent += len(pcm)
                await self._send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode()})
            if time.monotonic() - started >= self.config.slice_seconds:
                if sent >= bytes_per_second * 0.3:  # at least 0.3 s of audio
                    if loud >= self.config.silence_rms:
                        await self._send({"type": "input_audio_buffer.commit"})
                        self.on_audio_seconds(sent / bytes_per_second)
                    else:
                        await self._send({"type": "input_audio_buffer.clear"})
                started, loud, sent = time.monotonic(), 0.0, 0

    def _session(self) -> dict:
        transcription = {"model": self.config.transcribe_model}
        if self.config.language:
            transcription["language"] = self.config.language
        return {
            "type": "session.update",
            "session": {
                "type": "transcription",
                "audio": {"input": {
                    "format": {"type": "audio/pcm", "rate": self.config.api_rate},
                    "transcription": transcription,
                    "turn_detection": None,  # we cut the slices ourselves
                }},
            },
        }

    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        slicer = asyncio.create_task(self._slicer())
        headers = {"Authorization": f"Bearer {self.config.openai_api_key}"}
        try:
            while True:
                try:
                    async with websockets.connect(REALTIME_URL, additional_headers=headers, max_size=None) as ws:
                        self.ws = ws
                        opened = time.monotonic()
                        await ws.send(json.dumps(self._session()))
                        self.connected = True
                        log.info("listening (transcription stream connected)")
                        async for message in ws:
                            event = json.loads(message)
                            kind = event.get("type")
                            if kind == "conversation.item.input_audio_transcription.completed":
                                text = event.get("transcript", "").strip()
                                if text:
                                    asyncio.create_task(self.on_text(text))
                            elif kind == "error":
                                if event.get("error", {}).get("code") != "input_audio_buffer_commit_empty":
                                    log.warning("transcription error: %s", event.get("error"))
                            if time.monotonic() - opened > SESSION_LIMIT:
                                break
                except Exception as exc:  # noqa: BLE001 - keep listening
                    if "invalid_api_key" in str(exc):
                        log.error("OpenAI rejected OPENAI_API_KEY; fix it in .env (retrying in 30 s)")
                        backoff = 30
                    else:
                        log.warning("transcription stream dropped (%s); reconnecting", exc or type(exc).__name__)
                        backoff = 1
                else:
                    backoff = 1
                self.ws = None
                self.connected = False
                await asyncio.sleep(backoff)
        finally:
            slicer.cancel()


TRANSCRIBERS: dict[str, type] = {
    "openai-realtime": OpenAIRealtime,
}


def make_transcriber(config: Config, on_text, on_audio_seconds=lambda seconds: None):
    try:
        cls = TRANSCRIBERS[config.transcriber]
    except KeyError:
        raise RuntimeError(f"Unknown transcriber {config.transcriber!r}; options: {', '.join(TRANSCRIBERS)}") from None
    return cls(config, on_text, on_audio_seconds)
