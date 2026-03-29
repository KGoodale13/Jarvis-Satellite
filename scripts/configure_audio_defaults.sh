#!/bin/bash

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

wait_for_pulse() {
    local retries="${1:-30}"
    local delay="${2:-1}"
    local attempt

    for attempt in $(seq 1 "$retries"); do
        if pactl info >/dev/null 2>&1; then
            return 0
        fi

        if [[ "$attempt" -eq "$retries" ]]; then
            return 1
        fi

        sleep "$delay"
    done
}

match_pactl_device() {
    local device_type="$1"
    shift
    local patterns=("$@")
    local line
    local name
    local lowered
    local pattern

    while IFS= read -r line; do
        name="$(awk '{print $2}' <<<"$line")"
        lowered="$(tr '[:upper:]' '[:lower:]' <<<"$name")"
        for pattern in "${patterns[@]}"; do
            [[ -n "$pattern" ]] || continue
            if [[ "$lowered" == *"$(tr '[:upper:]' '[:lower:]' <<<"$pattern")"* ]]; then
                echo "$name"
                return 0
            fi
        done
    done < <(pactl "list" short "$device_type")

    return 1
}

if ! wait_for_pulse; then
    log "PipeWire/PulseAudio is not ready"
    exit 1
fi

default_source="${JARVIS_AUDIO_INPUT_NAME:-}"
default_sink="${JARVIS_AUDIO_OUTPUT_NAME:-}"

if [[ -z "$default_source" ]]; then
    default_source="$(match_pactl_device sources Array respeaker reSpeaker xvf || true)"
fi

if [[ -z "$default_sink" ]]; then
    default_sink="$(match_pactl_device sinks DigiAMP iqaudio dacplus snd_rpi_iqaudio || true)"
fi

if [[ -n "$default_source" ]]; then
    pactl set-default-source "$default_source"
    log "Configured default input source: $default_source"
else
    log "Could not detect a ReSpeaker input source; leaving the current default"
fi

if [[ -n "$default_sink" ]]; then
    pactl set-default-sink "$default_sink"
    log "Configured default output sink: $default_sink"
else
    log "Could not detect a DigiAMP output sink; leaving the current default"
fi
