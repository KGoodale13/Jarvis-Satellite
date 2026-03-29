#!/usr/bin/env python3
"""Jarvis launcher for OHF Linux Voice Assistant."""

from __future__ import annotations

import argparse
import importlib
import os
import sys

from .lva_protocol import JarvisVoiceSatelliteProtocol


def _build_wrapper_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--xvf-path",
        default=os.environ.get("JARVIS_XVF_PATH"),
        help="Path to the XVF host-control executable",
    )
    parser.add_argument(
        "--xvf-transport",
        default=os.environ.get("JARVIS_XVF_TRANSPORT", "usb"),
        help="Transport to use with xvf_host (usb or i2c)",
    )
    parser.add_argument(
        "--disable-leds",
        action="store_true",
        default=os.environ.get("JARVIS_DISABLE_LEDS", "0") == "1",
        help="Disable the ReSpeaker LED integration",
    )
    return parser


async def main() -> None:
    """Patch Linux Voice Assistant with Jarvis-specific hardware hooks."""
    wrapper_args, remaining = _build_wrapper_parser().parse_known_args()

    try:
        lva_main = importlib.import_module("linux_voice_assistant.__main__")
    except ModuleNotFoundError as err:
        raise SystemExit(
            "linux-voice-assistant is not installed in this environment"
        ) from err

    JarvisVoiceSatelliteProtocol.configure(
        xvf_path=wrapper_args.xvf_path,
        disable_leds=wrapper_args.disable_leds,
        xvf_transport=wrapper_args.xvf_transport,
    )
    lva_main.VoiceSatelliteProtocol = JarvisVoiceSatelliteProtocol

    sys.argv = [sys.argv[0], *remaining]
    await lva_main.main()
