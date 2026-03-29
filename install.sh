#!/bin/bash

set -euo pipefail

INSTALL_DIR="/opt"
APP_DIR="${INSTALL_DIR}/jarvis-satellite"
LVA_DIR="${INSTALL_DIR}/linux-voice-assistant"
STATE_DIR="/var/lib/jarvis-satellite"
LVA_REPO="https://github.com/OHF-Voice/linux-voice-assistant.git"
LVA_REF="0dce320db2b6ac938f93f02e1b1136d0625173b1"
SERVICE_NAME="jarvis-satellite.service"
SERVICE_USER="${SUDO_USER:-$(logname 2>/dev/null || true)}"

if [[ -z "${SERVICE_USER}" || "${SERVICE_USER}" == "root" ]]; then
    SERVICE_USER="pi"
fi

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    echo "Unable to find install user '${SERVICE_USER}'"
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
    cat > /etc/default/jarvis-satellite <<EOF
CLIENT_NAME="Jarvis Satellite"
PORT="6053"
WAKE_MODEL="hey_jarvis"
PREFERENCES_FILE="${STATE_DIR}/preferences.json"
JARVIS_XVF_PATH="${APP_DIR}/respeaker_xvf3800/host_control/rpi_64bit/xvf_host"
JARVIS_XVF_TRANSPORT="usb"
# ENABLE_DEBUG="1"
# ENABLE_THINKING_SOUND="1"
# NETWORK_INTERFACE="eth0"
# HOST="192.168.1.100"
# AUDIO_INPUT_DEVICE="default"
# AUDIO_OUTPUT_DEVICE="default"
# JARVIS_AUDIO_INPUT_NAME="alsa_input.usb-SEEED_ReSpeaker_Array_..."
# JARVIS_AUDIO_OUTPUT_NAME="alsa_output.platform-soc_sound.stereo-fallback"
EOF
}

write_service_file() {
    cat > /etc/systemd/system/${SERVICE_NAME} <<EOF
[Unit]
Description=Jarvis Satellite (Linux Voice Assistant)
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
        libmpv-dev \
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

sync_linux_voice_assistant() {
    if [[ -d "${LVA_DIR}/.git" ]]; then
        git -C "${LVA_DIR}" fetch origin
    else
        git clone "${LVA_REPO}" "${LVA_DIR}"
    fi

    git -C "${LVA_DIR}" checkout "${LVA_REF}"
}

setup_python_environment() {
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_DIR}" "${LVA_DIR}" "${STATE_DIR}"

    run_as_service_user python3 -m venv "${APP_DIR}/.venv"
    run_as_service_user "${APP_DIR}/.venv/bin/pip" install --upgrade pip setuptools wheel
    run_as_service_user env CXXFLAGS="-O1 -g0" MAKEFLAGS="-j1" \
        "${APP_DIR}/.venv/bin/pip" install -e "${LVA_DIR}" -e "${APP_DIR}"
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

log "Syncing upstream linux-voice-assistant checkout"
sync_linux_voice_assistant

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
log "Home Assistant should add this device using the ESPHome integration on port 6053"
log "Check the service with: sudo systemctl status ${SERVICE_NAME}"
log "A reboot is recommended if the DigiAMP+ overlay was newly enabled"
