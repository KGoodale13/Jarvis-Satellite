"""Satellite orchestration independent of Pipecat server internals."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Protocol

from .led_controller import JarvisLedController

_LOGGER = logging.getLogger(__name__)


class Audio(Protocol):
    capture_queue: asyncio.Queue[bytes]

    def start(self, loop: asyncio.AbstractEventLoop) -> None: ...
    async def play(self, pcm: bytes, sample_rate: int, channels: int) -> None: ...
    async def stop(self) -> None: ...


class WakeDetector(Protocol):
    phrase: str
    def process(self, pcm: bytes) -> bool: ...
    def reset(self) -> None: ...


class Session(Protocol):
    async def run_with_timeout(self, *args, **kwargs) -> None: ...


class JarvisSatellite:
    def __init__(
        self,
        *,
        audio: Audio,
        wake_detector: WakeDetector,
        session: Session,
        leds: JarvisLedController | None,
        refractory_seconds: float,
    ) -> None:
        self._audio = audio
        self._wake_detector = wake_detector
        self._session = session
        self._leds = leds
        self._refractory_seconds = refractory_seconds

    async def run(self) -> None:
        if self._leds:
            self._leds.startup()
        self._audio.start(asyncio.get_running_loop())
        if self._leds:
            self._leds.idle()
        _LOGGER.info("Satellite ready; waiting for %r", self._wake_detector.phrase)

        last_wake = 0.0
        try:
            while True:
                pcm = await self._audio.capture_queue.get()
                if not pcm:
                    raise RuntimeError("Microphone capture stopped")
                if not self._wake_detector.process(pcm):
                    continue
                now = time.monotonic()
                if now - last_wake < self._refractory_seconds:
                    continue
                last_wake = now
                await self._conversation()
        finally:
            await self._audio.stop()
            if self._leds:
                self._leds.idle()

    async def _conversation(self) -> None:
        _LOGGER.info("Detected wake word %r", self._wake_detector.phrase)
        if self._leds:
            self._leds.wake_detected()
            self._leds.processing()
        try:
            await self._session.run_with_timeout(
                self._audio.capture_queue,
                self._audio.play,
                self._listening,
                self._speaking,
            )
        except TimeoutError:
            _LOGGER.warning("Pipecat conversation reached its configured time limit")
        except Exception:
            _LOGGER.exception("Pipecat conversation failed")
            if self._leds:
                self._leds.disconnected()
            await asyncio.sleep(2.0)
        finally:
            self._wake_detector.reset()
            if self._leds:
                self._leds.idle()
            _LOGGER.info("Waiting for wake word")

    def _listening(self) -> None:
        if self._leds:
            self._leds.listening()

    def _speaking(self) -> None:
        if self._leds:
            self._leds.speaking()
