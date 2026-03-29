#!/bin/bash

set -euo pipefail

APP_DIR="/opt/jarvis-satellite"
LVA_DIR="/opt/linux-voice-assistant"
PYTHON_BIN="${APP_DIR}/.venv/bin/python"
PREFERENCES_FILE="${PREFERENCES_FILE:-/var/lib/jarvis-satellite/preferences.json}"
PULSE_COOKIE="${PULSE_COOKIE:-/var/lib/jarvis-satellite/tmp_pulse_cookie}"
JARVIS_XVF_PATH="${JARVIS_XVF_PATH:-${APP_DIR}/respeaker_xvf3800/host_control/rpi_64bit/xvf_host}"

mkdir -p "$(dirname "${PREFERENCES_FILE}")"
mkdir -p "$(dirname "${PULSE_COOKIE}")"

if [[ ! -f "${PULSE_COOKIE}" ]]; then
    touch "${PULSE_COOKIE}"
    chmod 600 "${PULSE_COOKIE}"
fi

args=(
    "--xvf-path" "${JARVIS_XVF_PATH}"
    "--preferences-file" "${PREFERENCES_FILE}"
    "--port" "${PORT:-6053}"
    "--wake-model" "${WAKE_MODEL:-hey_jarvis}"
    "--wake-word-dir" "${LVA_DIR}/wakewords"
    "--wake-word-dir" "${LVA_DIR}/wakewords/openWakeWord"
)

if [[ "${JARVIS_DISABLE_LEDS:-0}" == "1" ]]; then
    args+=("--disable-leds")
fi

if [[ -n "${CLIENT_NAME:-}" ]]; then
    args+=("--name" "${CLIENT_NAME}")
fi

if [[ -n "${NETWORK_INTERFACE:-}" ]]; then
    args+=("--network-interface" "${NETWORK_INTERFACE}")
fi

if [[ -n "${HOST:-}" ]]; then
    args+=("--host" "${HOST}")
fi

if [[ -n "${AUDIO_INPUT_DEVICE:-}" ]]; then
    args+=("--audio-input-device" "${AUDIO_INPUT_DEVICE}")
fi

if [[ -n "${AUDIO_OUTPUT_DEVICE:-}" ]]; then
    args+=("--audio-output-device" "${AUDIO_OUTPUT_DEVICE}")
fi

if [[ -n "${REFACTORY_SECONDS:-}" ]]; then
    args+=("--refractory-seconds" "${REFACTORY_SECONDS}")
fi

if [[ "${ENABLE_THINKING_SOUND:-0}" == "1" ]]; then
    args+=("--enable-thinking-sound")
fi

if [[ "${ENABLE_DEBUG:-0}" == "1" ]]; then
    args+=("--debug")
fi

exec "${PYTHON_BIN}" -m jarvis_satellite "${args[@]}"
