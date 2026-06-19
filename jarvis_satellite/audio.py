"""Full-duplex audio access through the system's PipeWire/PulseAudio defaults."""

from __future__ import annotations

import asyncio
import logging
import threading
from queue import Queue
from typing import Optional

import numpy as np
import soundcard as sc

_LOGGER = logging.getLogger(__name__)


class SoundCardAudio:
    """Continuously capture PCM16 and play server PCM16 on dedicated threads."""

    def __init__(
        self,
        *,
        input_device: str | None,
        output_device: str | None,
        input_sample_rate: int,
        output_sample_rate: int,
        block_size: int,
    ) -> None:
        self.input_sample_rate = input_sample_rate
        self.output_sample_rate = output_sample_rate
        self.block_size = block_size
        self._microphone = sc.get_microphone(input_device) if input_device else sc.default_microphone()
        self._speaker = sc.get_speaker(output_device) if output_device else sc.default_speaker()
        if self._microphone is None:
            raise RuntimeError("No capture device is available")
        if self._speaker is None:
            raise RuntimeError("No playback device is available")

        self.capture_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=32)
        self._playback_queue: Queue[Optional[bytes]] = Queue(maxsize=64)
        self._stop = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._playback_thread: threading.Thread | None = None

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        _LOGGER.info("Using microphone %s and speaker %s", self._microphone.name, self._speaker.name)
        self._capture_thread = threading.Thread(
            target=self._capture, args=(loop,), daemon=True, name="jarvis-capture"
        )
        self._playback_thread = threading.Thread(
            target=self._playback, daemon=True, name="jarvis-playback"
        )
        self._capture_thread.start()
        self._playback_thread.start()

    def _capture(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            with self._microphone.recorder(
                samplerate=self.input_sample_rate, channels=1, blocksize=self.block_size
            ) as recorder:
                while not self._stop.is_set():
                    samples = recorder.record(self.block_size).reshape(-1)
                    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
                    loop.call_soon_threadsafe(self._enqueue_capture, pcm)
        except Exception:
            _LOGGER.exception("Audio capture stopped unexpectedly")
            loop.call_soon_threadsafe(self._enqueue_capture, b"")

    def _enqueue_capture(self, pcm: bytes) -> None:
        if self.capture_queue.full():
            try:
                self.capture_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self.capture_queue.put_nowait(pcm)

    def _playback(self) -> None:
        try:
            with self._speaker.player(samplerate=self.output_sample_rate, channels=1) as player:
                while not self._stop.is_set():
                    pcm = self._playback_queue.get()
                    if pcm is None:
                        return
                    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
                    player.play(samples.reshape(-1, 1))
        except Exception:
            _LOGGER.exception("Audio playback stopped unexpectedly")

    async def play(self, pcm: bytes, sample_rate: int, channels: int) -> None:
        if sample_rate != self.output_sample_rate or channels != 1:
            raise ValueError(
                "Pipecat output must be "
                f"{self.output_sample_rate} Hz mono, received {sample_rate} Hz/{channels} channels"
            )
        await asyncio.to_thread(self._playback_queue.put, pcm)

    async def stop(self) -> None:
        self._stop.set()
        try:
            self._playback_queue.put_nowait(None)
        except Exception:
            pass
        for thread in (self._capture_thread, self._playback_thread):
            if thread is not None:
                await asyncio.to_thread(thread.join, 2.0)
