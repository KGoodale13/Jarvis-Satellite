#!/usr/bin/env python3
"""Event controller for the LEDs on the ReSpeaker XVF3800 USB 4-Mic Array and
the digiamp+ audio output.
"""
import argparse
import asyncio
import logging
import time
from functools import partial

from wyoming.event import Event
from wyoming.satellite import (
    SatelliteConnected,
    SatelliteDisconnected,
    StreamingStarted,
    StreamingStopped,
)
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.snd import Played
from wyoming.vad import VoiceStarted, VoiceStopped
from wyoming.wake import Detection
from jarvis_satellite.respeaker_xvf import RespeakerXVF, LEDEffect
_LOGGER = logging.getLogger()


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True, help="unix:// or tcp://")
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    parser.add_argument("--xvf-path", required=True, help="Path to the XVF executable")
    args = parser.parse_args()

    respeaker_xvf = RespeakerXVF(args.xvf_path)

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    _LOGGER.info("Ready")

    # Turn on power to LEDs 
    respeaker_xvf.set_led_effect(LEDEffect.ON)
    respeaker_xvf.set_led_brightness(255)
    respeaker_xvf.set_led_gammify(True)
    respeaker_xvf.set_led_color(0x0080FF)
    await asyncio.sleep(1)

    # Start server
    server = AsyncServer.from_uri(args.uri)

    try:
        await server.run(partial(LEDsEventHandler, args))
    except KeyboardInterrupt:
        pass
    finally:
        respeaker_xvf.set_led_effect(LEDEffect.OFF)


class LEDsEventHandler(AsyncEventHandler):
    """Event handler for clients."""

    def __init__(
        self,
        cli_args: argparse.Namespace,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.client_id = str(time.monotonic_ns())
        self.respeaker_xvf = RespeakerXVF(cli_args.xvf_path)
    
        _LOGGER.debug("Client connected: %s", self.client_id)

    async def handle_event(self, event: Event) -> bool:
        _LOGGER.debug(event)

        if Detection.is_type(event.type):
            _LOGGER.debug("Detection")
            self.respeaker_xvf.set_led_effect(LEDEffect.DOA)
            self.respeaker_xvf.set_led_brightness(255)
        elif VoiceStarted.is_type(event.type):
            _LOGGER.debug("VoiceStarted")
            self.respeaker_xvf.set_led_effect(LEDEffect.BREATH)
            self.respeaker_xvf.set_led_brightness(255)
            self.respeaker_xvf.set_led_color(0x0080FF)
            self.respeaker_xvf.set_led_speed(1)
        elif VoiceStopped.is_type(event.type):
            _LOGGER.debug("VoiceStopped")
            self.respeaker_xvf.set_led_effect(LEDEffect.ON)
            self.respeaker_xvf.set_led_brightness(255)
            self.respeaker_xvf.set_led_color(0x00FFFF)
            await asyncio.sleep(0.5)
            self.respeaker_xvf.set_led_effect(LEDEffect.OFF)
        elif StreamingStopped.is_type(event.type):
            _LOGGER.debug("StreamingStopped")
            self.respeaker_xvf.set_led_effect(LEDEffect.OFF)
        elif SatelliteConnected.is_type(event.type):
            _LOGGER.debug("SatelliteConnected")
            self.respeaker_xvf.set_led_effect(LEDEffect.ON)
            self.respeaker_xvf.set_led_brightness(255)
            self.respeaker_xvf.set_led_color(0x00FF00)
            self.respeaker_xvf.set_led_speed(5)
            await asyncio.sleep(2)
            self.respeaker_xvf.set_led_effect(LEDEffect.OFF)
        elif Played.is_type(event.type):
            _LOGGER.debug("Played")
            self.respeaker_xvf.set_led_effect(LEDEffect.OFF)
        elif SatelliteDisconnected.is_type(event.type):
            _LOGGER.debug("SatelliteDisconnected")
            self.respeaker_xvf.set_led_effect(LEDEffect.ON)
            self.respeaker_xvf.set_led_color(0xFF0000)
            self.respeaker_xvf.set_led_speed(8)
            await asyncio.sleep(10)
            self.respeaker_xvf.set_led_brightness(175)

        return True


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass