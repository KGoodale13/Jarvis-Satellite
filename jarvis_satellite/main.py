#!/usr/bin/env python3
"""Command-line entry point for the Jarvis Pipecat satellite."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from .audio import SoundCardAudio
from .led_controller import JarvisLedController
from .pipecat_client import PipecatSession
from .satellite import JarvisSatellite
from .wake_word import MicroWakeWordDetector


def _env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wake-word Pipecat audio satellite")
    parser.add_argument(
        "--server-url",
        default=os.environ.get("PIPECAT_SERVER_URL"),
        required="PIPECAT_SERVER_URL" not in os.environ,
        help="Pipecat WebSocket URL (for example ws://server:7860/ws)",
    )
    parser.add_argument("--auth-token", default=os.environ.get("PIPECAT_AUTH_TOKEN"))
    parser.add_argument(
        "--wake-model",
        default=os.environ.get(
            "WAKE_MODEL", "/opt/jarvis-satellite/wakewords/hey_jarvis.json"
        ),
        help="Path to a microWakeWord JSON model configuration",
    )
    parser.add_argument("--audio-input-device", default=os.environ.get("AUDIO_INPUT_DEVICE"))
    parser.add_argument("--audio-output-device", default=os.environ.get("AUDIO_OUTPUT_DEVICE"))
    parser.add_argument("--input-sample-rate", type=int, default=16000)
    parser.add_argument(
        "--output-sample-rate",
        type=int,
        default=int(os.environ.get("PIPECAT_OUTPUT_SAMPLE_RATE", "24000")),
    )
    parser.add_argument(
        "--audio-block-size",
        type=int,
        default=int(os.environ.get("JARVIS_AUDIO_BLOCK_SIZE", "1280")),
    )
    parser.add_argument(
        "--refractory-seconds",
        type=float,
        default=_env_float("REFRACTORY_SECONDS", 2.0),
    )
    parser.add_argument(
        "--conversation-timeout",
        type=float,
        default=_env_float("PIPECAT_CONVERSATION_TIMEOUT", 300.0),
        help="Maximum WebSocket session length in seconds; 0 disables the limit",
    )
    parser.add_argument("--xvf-path", default=os.environ.get("JARVIS_XVF_PATH"))
    parser.add_argument(
        "--xvf-transport", default=os.environ.get("JARVIS_XVF_TRANSPORT", "usb")
    )
    parser.add_argument(
        "--disable-leds",
        action="store_true",
        default=os.environ.get("JARVIS_DISABLE_LEDS", "0") == "1",
    )
    parser.add_argument(
        "--debug", action="store_true", default=os.environ.get("ENABLE_DEBUG", "0") == "1"
    )
    return parser


def _create_leds(args: argparse.Namespace) -> JarvisLedController | None:
    if args.disable_leds or not args.xvf_path:
        return None
    try:
        return JarvisLedController(args.xvf_path, transport=args.xvf_transport)
    except Exception:
        logging.getLogger(__name__).exception("LED controller is unavailable")
        return None


async def main() -> None:
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    wake_model = Path(args.wake_model)
    if not wake_model.is_file():
        raise SystemExit(f"Wake model configuration not found: {wake_model}")

    leds = _create_leds(args)
    audio = SoundCardAudio(
        input_device=args.audio_input_device,
        output_device=args.audio_output_device,
        input_sample_rate=args.input_sample_rate,
        output_sample_rate=args.output_sample_rate,
        block_size=args.audio_block_size,
    )
    session = PipecatSession(
        server_url=args.server_url,
        auth_token=args.auth_token,
        input_sample_rate=args.input_sample_rate,
        conversation_timeout=args.conversation_timeout,
    )
    satellite = JarvisSatellite(
        audio=audio,
        wake_detector=MicroWakeWordDetector(wake_model),
        session=session,
        leds=leds,
        refractory_seconds=args.refractory_seconds,
    )
    await satellite.run()
