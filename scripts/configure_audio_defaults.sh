#!/bin/bash

set -euo pipefail

log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1" >&2
}

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

        if [[ "$attempt" -eq 5 ]]; then
            systemctl --user start pipewire.service pipewire-pulse.service wireplumber.service >/dev/null 2>&1 || true
        fi

        if [[ "$attempt" -eq "$retries" ]]; then
            return 1
        fi

        sleep "$delay"
    done
}

list_pactl_devices() {
    local device_type="$1"
    pactl list short "$device_type" | awk '{print $2}'
}

list_real_pactl_devices() {
    local device_type="$1"
    list_pactl_devices "$device_type" | grep -v '\.monitor$' || true
}

match_pactl_device() {
    local device_type="$1"
    shift
    local patterns=("$@")
    local line
    local name_lower
    local lowered
    local pattern

    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        lowered="$(tr '[:upper:]' '[:lower:]' <<<"$line")"
        for pattern in "${patterns[@]}"; do
            [[ -n "$pattern" ]] || continue
            name_lower="$(tr '[:upper:]' '[:lower:]' <<<"$pattern")"
            if [[ "$lowered" == *"$name_lower"* ]]; then
                echo "$line"
                return 0
            fi
        done
    done < <(list_real_pactl_devices "$device_type")

    return 1
}

pick_single_device() {
    local device_type="$1"
    mapfile -t devices < <(list_real_pactl_devices "$device_type")
    if [[ "${#devices[@]}" -eq 1 ]]; then
        echo "${devices[0]}"
        return 0
    fi

    return 1
}

has_capture_hardware() {
    arecord -l 2>/dev/null | grep -q '^card '
}

has_playback_hardware() {
    aplay -l 2>/dev/null | grep -q '^card '
}

describe_capture_hardware() {
    arecord -l 2>/dev/null | sed 's/^/  /' || true
}

describe_playback_hardware() {
    aplay -l 2>/dev/null | sed 's/^/  /' || true
}

set_source_volume() {
    local source_name="$1"
    local volume="$2"
    pactl set-source-volume "$source_name" "$volume"
    log "Configured source volume for ${source_name}: ${volume}"
}

set_sink_volume() {
    local sink_name="$1"
    local volume="$2"
    pactl set-sink-volume "$sink_name" "$volume"
    log "Configured sink volume for ${sink_name}: ${volume}"
}

set_xvf_mic_gain() {
    local gain="$1"
    local xvf_path="${JARVIS_XVF_PATH:-}"
    local xvf_transport="${JARVIS_XVF_TRANSPORT:-usb}"

    [[ -n "$xvf_path" ]] || return 0

    if "$xvf_path" --use "$xvf_transport" AUDIO_MGR_MIC_GAIN "$gain" >/dev/null 2>&1; then
        log "Configured XVF microphone gain: ${gain}"
    else
        log_error "Failed to configure XVF microphone gain to ${gain}"
    fi
}

configure_aec_reference_sink() {
    local playback_sink="$1"
    local reference_sink="$2"
    local combined_sink="${JARVIS_AEC_SINK_NAME:-jarvis_aec_output}"
    local module_id

    while IFS= read -r module_id; do
        [[ -n "$module_id" ]] || continue
        pactl unload-module "$module_id" || true
    done < <(
        pactl list short modules \
            | awk -v sink_name="sink_name=${combined_sink}" \
                '$2 == "module-combine-sink" && index($0, sink_name) { print $1 }'
    )

    pactl set-sink-volume \
        "$reference_sink" "${JARVIS_AEC_REFERENCE_VOLUME:-100%}"

    if module_id="$(pactl load-module module-combine-sink \
        sink_name="$combined_sink" \
        slaves="${playback_sink},${reference_sink}" \
        sink_properties="device.description=Jarvis_AEC_Output")"; then
        pactl set-default-sink "$combined_sink"
        log "Configured AEC output ${combined_sink}: speaker=${playback_sink}, reference=${reference_sink}, module=${module_id}"
        return 0
    fi

    log_error "Failed to create the XVF3800 AEC reference output; keeping ${playback_sink}"
    pactl set-default-sink "$playback_sink"
    return 1
}

if ! wait_for_pulse; then
    log_error "PipeWire/PulseAudio is not ready"
    exit 1
fi

default_source="${JARVIS_AUDIO_INPUT_NAME:-}"
default_sink="${JARVIS_AUDIO_OUTPUT_NAME:-}"

if [[ -z "$default_source" ]]; then
    default_source="$(match_pactl_device sources Array respeaker reSpeaker seeed xvf xmos usb || true)"
fi

if [[ -z "$default_source" ]]; then
    default_source="$(pick_single_device sources || true)"
fi

if [[ -z "$default_sink" ]]; then
    default_sink="$(match_pactl_device sinks DigiAMP iqaudio dacplus snd_rpi_iqaudio soc_sound || true)"
fi

if [[ -z "$default_sink" ]]; then
    default_sink="$(pick_single_device sinks || true)"
fi

if [[ -n "$default_source" ]]; then
    pactl set-default-source "$default_source"
    log "Configured default input source: $default_source"
else
    current_source="$(pactl get-default-source 2>/dev/null || true)"
    if [[ -n "$current_source" && "$current_source" != *.monitor ]]; then
        log "Could not identify the ReSpeaker source; keeping current default input source: $current_source"
    else
        log_error "Could not find any real PipeWire capture source"
        if has_capture_hardware; then
            log_error "ALSA capture hardware exists, but PipeWire did not expose an input source"
            describe_capture_hardware >&2
        else
            log_error "ALSA reports no capture hardware. The ReSpeaker/XVF3800 is not enumerated."
        fi
        exit 1
    fi
fi

effective_source="${default_source:-${current_source:-}}"

if [[ -n "$default_sink" ]]; then
    pactl set-default-sink "$default_sink"
    log "Configured default output sink: $default_sink"
else
    current_sink="$(pactl get-default-sink 2>/dev/null || true)"
    if [[ -n "$current_sink" ]]; then
        log "Could not identify the DigiAMP sink; keeping current default output sink: $current_sink"
    elif has_playback_hardware; then
        log "Could not identify the DigiAMP sink, but ALSA playback hardware exists"
        describe_playback_hardware
    else
        log "Could not identify any playback sink"
    fi
fi

effective_sink="${default_sink:-${current_sink:-}}"

if [[ -n "${JARVIS_INPUT_VOLUME:-}" && -n "${effective_source:-}" ]]; then
    set_source_volume "$effective_source" "${JARVIS_INPUT_VOLUME}"
fi

if [[ -n "${JARVIS_OUTPUT_VOLUME:-}" && -n "${effective_sink:-}" ]]; then
    set_sink_volume "$effective_sink" "${JARVIS_OUTPUT_VOLUME}"
fi

if [[ -n "${JARVIS_XVF_MIC_GAIN:-}" ]]; then
    set_xvf_mic_gain "${JARVIS_XVF_MIC_GAIN}"
fi

if [[ "${JARVIS_ENABLE_HARDWARE_AEC:-1}" == "1" && -n "${effective_sink:-}" ]]; then
    aec_reference_sink="${JARVIS_AEC_REFERENCE_SINK:-}"
    if [[ -z "$aec_reference_sink" ]]; then
        aec_reference_sink="$(
            match_pactl_device sinks Array respeaker reSpeaker seeed xvf xmos usb || true
        )"
    fi

    if [[ -n "$aec_reference_sink" && "$aec_reference_sink" != "$effective_sink" ]]; then
        configure_aec_reference_sink "$effective_sink" "$aec_reference_sink" || true
    else
        log_error "XVF3800 playback sink not found; hardware AEC has no far-end reference"
    fi
fi
