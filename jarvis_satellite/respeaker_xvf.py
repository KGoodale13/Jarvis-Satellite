"""Respeaker XVF3800 control via the XVF interface from https://github.com/respeaker/reSpeaker_XVF3800_USB_4MIC_ARRAY"""

from __future__ import annotations

import logging
import subprocess
from enum import Enum
from typing import Iterable

_LOGGER = logging.getLogger(__name__)


class XVFCommand(Enum):
    LED_EFFECT = "LED_EFFECT"
    LED_BRIGHTNESS = "LED_BRIGHTNESS"
    LED_GAMMIFY = "LED_GAMMIFY"
    LED_SPEED = "LED_SPEED"
    LED_COLOR = "LED_COLOR"

class LEDEffect(Enum):
    OFF = 0
    BREATH = 1
    RAINBOW = 2
    SINGLE_COLOR = 3
    DOA = 4

class RespeakerXVF:
    def __init__(self, xvf_path: str, transport: str = "usb"):
        self.xvf_path = xvf_path
        self.transport = transport

    def _execute_xvf(self, command: XVFCommand, value: int) -> None:
        try:
            subprocess.run(
                self._build_command(command, value),
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
        except FileNotFoundError:
            _LOGGER.warning("XVF host binary not found: %s", self.xvf_path)
        except subprocess.TimeoutExpired:
            _LOGGER.warning("Timed out sending %s to XVF host", command.value)
        except subprocess.CalledProcessError:
            _LOGGER.warning(
                "XVF host rejected %s=%s over transport %s",
                command.value,
                value,
                self.transport,
            )

    def _build_command(self, command: XVFCommand, value: int) -> list[str]:
        cmd = [self.xvf_path]
        transport_args = list(self._transport_args())
        if transport_args:
            cmd.extend(transport_args)
        cmd.extend([command.value, str(value)])
        return cmd

    def _transport_args(self) -> Iterable[str]:
        normalized_transport = self.transport.strip().lower()
        if normalized_transport:
            return ("--use", normalized_transport)
        return ()

    def set_led_effect(self, effect: LEDEffect) -> None:
        self._execute_xvf(XVFCommand.LED_EFFECT, effect.value)

    def set_led_brightness(self, brightness: int) -> None:
        if brightness < 0 or brightness > 255:
            raise ValueError("Brightness must be between 0 and 255")
        self._execute_xvf(XVFCommand.LED_BRIGHTNESS, brightness)

    def set_led_gammify(self, gammify: bool) -> None:
        self._execute_xvf(XVFCommand.LED_GAMMIFY, 1 if gammify else 0)

    def set_led_speed(self, speed: int) -> None:
        if speed < 0 or speed > 10:
            raise ValueError("Speed must be between 0 and 10")
        self._execute_xvf(XVFCommand.LED_SPEED, speed)

    def set_led_color(self, color: int) -> None:
        if color < 0 or color > 0xFFFFFFFF:
            raise ValueError("Color must be between 0 and 0xFFFFFFFF")
        self._execute_xvf(XVFCommand.LED_COLOR, color)
