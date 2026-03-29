"""XVF3800 LED state management for the Jarvis satellite."""

from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock, Timer
from typing import Callable, Optional

from .respeaker_xvf import LEDEffect, RespeakerXVF

_LOGGER = logging.getLogger(__name__)


class JarvisLedController:
    """Translate satellite state transitions into XVF3800 LED commands."""

    def __init__(self, xvf_path: str) -> None:
        resolved_path = Path(xvf_path)
        if not resolved_path.exists():
            raise FileNotFoundError(f"XVF host binary not found: {resolved_path}")

        self._xvf = RespeakerXVF(str(resolved_path))
        self._lock = Lock()
        self._timer: Optional[Timer] = None
        self._generation = 0
        self._xvf.set_led_gammify(True)

    def startup(self) -> None:
        self._transition(self._startup_action)

    def connected(self) -> None:
        self._transition(self._connected_action, delay=1.0, follow_up=self._idle_action)

    def disconnected(self) -> None:
        self._transition(
            self._disconnected_action,
            delay=2.0,
            follow_up=self._disconnected_dim_action,
        )

    def wake_detected(self) -> None:
        self._transition(self._wake_detected_action, delay=1.0, follow_up=self._idle_action)

    def listening(self) -> None:
        self._transition(self._listening_action)

    def processing(self) -> None:
        self._transition(self._processing_action)

    def muted(self) -> None:
        self._transition(self._muted_action)

    def voice_captured(self) -> None:
        self._transition(self._voice_captured_action, delay=0.5, follow_up=self._idle_action)

    def speaking(self) -> None:
        self._transition(self._idle_action)

    def idle(self) -> None:
        self._transition(self._idle_action)

    def _transition(
        self,
        action: Callable[[], None],
        *,
        delay: Optional[float] = None,
        follow_up: Optional[Callable[[], None]] = None,
    ) -> None:
        with self._lock:
            self._generation += 1
            generation = self._generation
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

            action()

            if delay is not None and follow_up is not None:
                timer = Timer(delay, self._run_follow_up, args=(generation, follow_up))
                timer.daemon = True
                timer.start()
                self._timer = timer

    def _run_follow_up(self, generation: int, action: Callable[[], None]) -> None:
        with self._lock:
            if generation != self._generation:
                return

            self._timer = None
            action()

    def _startup_action(self) -> None:
        self._xvf.set_led_effect(LEDEffect.SINGLE_COLOR)
        self._xvf.set_led_brightness(255)
        self._xvf.set_led_color(0x0080FF)

    def _connected_action(self) -> None:
        self._xvf.set_led_effect(LEDEffect.BREATH)
        self._xvf.set_led_brightness(255)
        self._xvf.set_led_color(0x00FF00)
        self._xvf.set_led_speed(5)

    def _disconnected_action(self) -> None:
        self._xvf.set_led_effect(LEDEffect.BREATH)
        self._xvf.set_led_brightness(255)
        self._xvf.set_led_color(0xFF0000)
        self._xvf.set_led_speed(8)

    def _disconnected_dim_action(self) -> None:
        self._xvf.set_led_brightness(150)

    def _wake_detected_action(self) -> None:
        self._xvf.set_led_effect(LEDEffect.DOA)
        self._xvf.set_led_brightness(255)

    def _listening_action(self) -> None:
        self._xvf.set_led_effect(LEDEffect.BREATH)
        self._xvf.set_led_brightness(255)
        self._xvf.set_led_color(0x0080FF)
        self._xvf.set_led_speed(1)

    def _processing_action(self) -> None:
        self._xvf.set_led_effect(LEDEffect.SINGLE_COLOR)
        self._xvf.set_led_brightness(255)
        self._xvf.set_led_color(0x00FFFF)

    def _muted_action(self) -> None:
        self._xvf.set_led_effect(LEDEffect.SINGLE_COLOR)
        self._xvf.set_led_brightness(180)
        self._xvf.set_led_color(0xFF8000)

    def _voice_captured_action(self) -> None:
        self._xvf.set_led_effect(LEDEffect.SINGLE_COLOR)
        self._xvf.set_led_brightness(255)
        self._xvf.set_led_color(0x00FFFF)

    def _idle_action(self) -> None:
        self._xvf.set_led_effect(LEDEffect.OFF)
