#!/bin/bash

set -euo pipefail

INSTALL_DIR="/opt"
APP_DIR="${INSTALL_DIR}/jarvis-satellite"
STATE_DIR="/var/lib/jarvis-satellite"
WAKEWORD_REF="0dce320db2b6ac938f93f02e1b1136d0625173b1"
WAKEWORD_BASE_URL="https://raw.githubusercontent.com/OHF-Voice/linux-voice-assistant/${WAKEWORD_REF}/wakewords"
SERVICE_NAME="jarvis-satellite.service"
SERVICE_USER="${JARVIS_SERVICE_USER:-${SUDO_USER:-$(logname 2>/dev/null || true)}}"

if [[ -z "${SERVICE_USER}" || "${SERVICE_USER}" == "root" ]]; then
    SERVICE_USER="$(
        getent passwd | awk -F: '
            $3 >= 1000 && $1 != "nobody" {
                print $1
                exit
            }
        '
    )"
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    echo "Unable to find install user '${SERVICE_USER}'"
    echo "Set JARVIS_SERVICE_USER to the non-root account that should run the satellite."
    exit 1
fi

SERVICE_GROUP="$(id -gn "${SERVICE_USER}")"
SERVICE_UID="$(id -u "${SERVICE_USER}")"
SERVICE_HOME="$(getent passwd "${SERVICE_USER}" | cut -d: -f6)"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

run_as_service_user() {
    sudo -H -u "${SERVICE_USER}" "$@"
}

install_respeaker_udev_rule() {
    cat > /etc/udev/rules.d/99-respeaker-xvf3800.rules <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="2886", ATTR{idProduct}=="001a", MODE="0660", GROUP="audio"
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2886", ATTRS{idProduct}=="001a", MODE="0660", GROUP="audio"
EOF

    udevadm control --reload-rules
    udevadm trigger --subsystem-match=usb || true
    udevadm trigger --subsystem-match=hidraw || true
}

configure_digiamp_overlay() {
    local cfg
    for cfg in /boot/firmware/config.txt /boot/config.txt; do
        [[ -f "${cfg}" ]] || continue

        if ! grep -q '^dtoverlay=iqaudio-dacplus' "${cfg}"; then
            echo "dtoverlay=iqaudio-dacplus,unmute_amp" >> "${cfg}"
            log "Added DigiAMP+ overlay to ${cfg}"
        elif ! grep -q '^dtoverlay=iqaudio-dacplus,unmute_amp' "${cfg}"; then
            sed -i 's/^dtoverlay=iqaudio-dacplus.*/dtoverlay=iqaudio-dacplus,unmute_amp/' "${cfg}"
            log "Ensured DigiAMP+ overlay includes unmute_amp in ${cfg}"
        fi

        if grep -q '^dtparam=audio=on' "${cfg}"; then
            sed -i 's/^dtparam=audio=on/# dtparam=audio=on (disabled by jarvis install)/' "${cfg}"
            log "Disabled onboard analog audio in ${cfg}"
        fi
    done
}

write_environment_file() {
    if [[ -f /etc/default/jarvis-satellite ]]; then
        if ! grep -q '^PIPECAT_SERVER_URL=' /etc/default/jarvis-satellite; then
            echo 'PIPECAT_SERVER_URL="http://pipecat:7860/api/offer"' >> /etc/default/jarvis-satellite
        elif grep -q '^PIPECAT_SERVER_URL=""' /etc/default/jarvis-satellite; then
            sed -i 's|^PIPECAT_SERVER_URL=""|PIPECAT_SERVER_URL="http://pipecat:7860/api/offer"|' \
                /etc/default/jarvis-satellite
        fi
        if ! grep -q '^PIPECAT_OUTPUT_SAMPLE_RATE=' /etc/default/jarvis-satellite; then
            echo 'PIPECAT_OUTPUT_SAMPLE_RATE="24000"' >> /etc/default/jarvis-satellite
        fi
        if ! grep -q '^PIPECAT_CONVERSATION_TIMEOUT=' /etc/default/jarvis-satellite; then
            echo 'PIPECAT_CONVERSATION_TIMEOUT="300"' >> /etc/default/jarvis-satellite
        fi
        if ! grep -q '^JARVIS_ENABLE_HARDWARE_AEC=' /etc/default/jarvis-satellite; then
            echo 'JARVIS_ENABLE_HARDWARE_AEC="1"' >> /etc/default/jarvis-satellite
        fi
        if ! grep -q '^JARVIS_AEC_REFERENCE_VOLUME=' /etc/default/jarvis-satellite; then
            echo 'JARVIS_AEC_REFERENCE_VOLUME="100%"' >> /etc/default/jarvis-satellite
        fi
        sed -i "s|^WAKE_MODEL=.*|WAKE_MODEL=\"${APP_DIR}/wakewords/hey_jarvis.json\"|" \
            /etc/default/jarvis-satellite
        return
    fi

    cat > /etc/default/jarvis-satellite <<EOF
PIPECAT_SERVER_URL="${PIPECAT_SERVER_URL:-http://pipecat:7860/api/offer}"
# PIPECAT_AUTH_TOKEN=""
WAKE_MODEL="${APP_DIR}/wakewords/hey_jarvis.json"
PIPECAT_OUTPUT_SAMPLE_RATE="24000"
PIPECAT_CONVERSATION_TIMEOUT="300"
JARVIS_XVF_PATH="${APP_DIR}/respeaker_xvf3800/host_control/rpi_64bit/xvf_host"
JARVIS_XVF_TRANSPORT="usb"
JARVIS_INPUT_VOLUME="125%"
JARVIS_OUTPUT_VOLUME="100%"
JARVIS_XVF_MIC_GAIN="100"
JARVIS_ENABLE_HARDWARE_AEC="1"
JARVIS_AEC_REFERENCE_VOLUME="100%"
# ENABLE_DEBUG="1"
# AUDIO_INPUT_DEVICE="default"
# AUDIO_OUTPUT_DEVICE="default"
# JARVIS_AUDIO_INPUT_NAME="alsa_input.usb-SEEED_ReSpeaker_Array_..."
# JARVIS_AUDIO_OUTPUT_NAME="alsa_output.platform-soc_sound.stereo-fallback"
EOF
}

write_service_file() {
    cat > /etc/systemd/system/${SERVICE_NAME} <<EOF
[Unit]
Description=Jarvis Pipecat Voice Satellite
Wants=network-online.target
Wants=user@${SERVICE_UID}.service
After=network-online.target sound.target user@${SERVICE_UID}.service

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
SupplementaryGroups=audio
WorkingDirectory=${APP_DIR}
EnvironmentFile=-/etc/default/jarvis-satellite
Environment=HOME=${SERVICE_HOME}
Environment=XDG_RUNTIME_DIR=/run/user/${SERVICE_UID}
Environment=PULSE_SERVER=unix:/run/user/${SERVICE_UID}/pulse/native
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/${SERVICE_UID}/bus
Environment=PULSE_COOKIE=${STATE_DIR}/tmp_pulse_cookie
ExecStartPre=${APP_DIR}/scripts/configure_audio_defaults.sh
ExecStart=${APP_DIR}/scripts/run_satellite.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
}

disable_legacy_services() {
    local legacy_services=(
        "wyoming-satellite.service"
        "wyoming-openwakeword.service"
        "jarvis-controller.service"
        "linux-voice-assistant.service"
    )
    local service

    for service in "${legacy_services[@]}"; do
        if systemctl list-unit-files "${service}" --no-legend >/dev/null 2>&1; then
            systemctl disable --now "${service}" >/dev/null 2>&1 || true
        fi
        rm -f "/etc/systemd/system/${service}"
    done
}

install_packages() {
    apt-get update
    apt-get install --no-install-recommends -y \
        alsa-utils \
        avahi-utils \
        build-essential \
        ca-certificates \
        curl \
        dfu-util \
        git \
        iproute2 \
        libasound2-plugins \
        libpulse0 \
        pipewire \
        pipewire-alsa \
        pipewire-bin \
        pipewire-pulse \
        pulseaudio-utils \
        python3-dev \
        python3-venv \
        procps \
        usbutils \
        wireplumber
}

install_wake_word() {
    install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" "${APP_DIR}/wakewords"
    curl --fail --location --silent --show-error \
        "${WAKEWORD_BASE_URL}/hey_jarvis.json" \
        --output "${APP_DIR}/wakewords/hey_jarvis.json"
    curl --fail --location --silent --show-error \
        "${WAKEWORD_BASE_URL}/hey_jarvis.tflite" \
        --output "${APP_DIR}/wakewords/hey_jarvis.tflite"
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_DIR}/wakewords"
}

setup_python_environment() {
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_DIR}" "${STATE_DIR}"

    run_as_service_user python3 -m venv --clear "${APP_DIR}/.venv"
    run_as_service_user "${APP_DIR}/.venv/bin/pip" install --upgrade pip setuptools wheel
    run_as_service_user env CXXFLAGS="-O1 -g0" MAKEFLAGS="-j1" \
        "${APP_DIR}/.venv/bin/pip" install -e "${APP_DIR}"
}

ensure_service_user_groups() {
    usermod -a -G audio "${SERVICE_USER}" || true
}

enable_pipewire_for_user() {
    loginctl enable-linger "${SERVICE_USER}" || true
    systemctl start "user@${SERVICE_UID}.service" >/dev/null 2>&1 || true
    systemctl --global enable pipewire.service pipewire-pulse.service wireplumber.service >/dev/null 2>&1 || true
    run_as_service_user env \
        XDG_RUNTIME_DIR="/run/user/${SERVICE_UID}" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${SERVICE_UID}/bus" \
        systemctl --user daemon-reload >/dev/null 2>&1 || true
    run_as_service_user env \
        XDG_RUNTIME_DIR="/run/user/${SERVICE_UID}" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${SERVICE_UID}/bus" \
        systemctl --user enable pipewire.service pipewire-pulse.service wireplumber.service >/dev/null 2>&1 || true
    run_as_service_user env \
        XDG_RUNTIME_DIR="/run/user/${SERVICE_UID}" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${SERVICE_UID}/bus" \
        systemctl --user restart pipewire.service pipewire-pulse.service wireplumber.service >/dev/null 2>&1 || true
}

if [[ "${EUID}" -ne 0 ]]; then
    echo "Please run as root (sudo ./install.sh)"
    exit 1
fi

log "Installing system packages"
install_packages

log "Configuring DigiAMP+ overlay"
configure_digiamp_overlay

log "Configuring ReSpeaker device permissions"
ensure_service_user_groups
install_respeaker_udev_rule

log "Preparing runtime directories"
mkdir -p "${STATE_DIR}"
touch "${STATE_DIR}/tmp_pulse_cookie"
chmod 600 "${STATE_DIR}/tmp_pulse_cookie"

log "Installing the local wake-word model"
install_wake_word

log "Updating Python environment"
setup_python_environment

log "Enabling PipeWire user services for ${SERVICE_USER}"
enable_pipewire_for_user

log "Installing service configuration"
chmod +x "${APP_DIR}/scripts/configure_audio_defaults.sh"
chmod +x "${APP_DIR}/scripts/run_satellite.sh"
chmod +x "${APP_DIR}/respeaker_xvf3800/host_control/rpi_64bit/xvf_host"
write_environment_file
write_service_file
disable_legacy_services

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

log "Installation complete"
log "Configure PIPECAT_SERVER_URL in /etc/default/jarvis-satellite"
log "Check the service with: sudo systemctl status ${SERVICE_NAME}"
log "A reboot is recommended if the DigiAMP+ overlay was newly enabled"
