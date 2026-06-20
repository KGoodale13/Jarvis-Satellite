#!/bin/bash

set -euo pipefail

APP_DIR="/opt/jarvis-satellite"
PYTHON_BIN="${APP_DIR}/.venv/bin/python"
JARVIS_XVF_PATH="${JARVIS_XVF_PATH:-${APP_DIR}/respeaker_xvf3800/host_control/rpi_64bit/xvf_host}"
WAKE_MODEL="${WAKE_MODEL:-${APP_DIR}/wakewords/hey_jarvis.json}"

args=(
    "--server-url" "${PIPECAT_SERVER_URL:-http://pipecat:7860/api/offer}"
    "--wake-model" "${WAKE_MODEL}"
    "--xvf-path" "${JARVIS_XVF_PATH}"
    "--xvf-transport" "${JARVIS_XVF_TRANSPORT:-usb}"
)

if [[ -n "${PIPECAT_AUTH_TOKEN:-}" ]]; then
    args+=("--auth-token" "${PIPECAT_AUTH_TOKEN}")
fi

if [[ "${JARVIS_DISABLE_LEDS:-0}" == "1" ]]; then
    args+=("--disable-leds")
fi

if [[ -n "${AUDIO_INPUT_DEVICE:-}" ]]; then
    args+=("--audio-input-device" "${AUDIO_INPUT_DEVICE}")
fi

if [[ -n "${AUDIO_OUTPUT_DEVICE:-}" ]]; then
    args+=("--audio-output-device" "${AUDIO_OUTPUT_DEVICE}")
fi

if [[ "${ENABLE_DEBUG:-0}" == "1" ]]; then
    args+=("--debug")
fi

exec "${PYTHON_BIN}" -m jarvis_satellite "${args[@]}"
