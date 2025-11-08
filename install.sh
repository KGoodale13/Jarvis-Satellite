#!/bin/bash

# Exit on error
set -e

# Function to log messages
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Function to check if command succeeded
check_status() {
    if [ $? -eq 0 ]; then
        log "✓ Success: $1"
    else
        log "✗ Error: $1"
        exit 1
    fi
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log "Please run as root (sudo ./install.sh)"
    exit 1
fi

INSTALL_DIR="/opt"

log "Starting installation"

# Update system
log "Updating system packages..."
apt-get update
apt-get upgrade -y
check_status "System update"

# Install prerequisites
log "Installing required packages..."
apt-get install --no-install-recommends -y git python3-venv libopenblas-dev python3-spidev python3-gpiozero
check_status "Package installation"


# Wyoming Satellite setup
log "Setting up Wyoming Satellite..."
cd $INSTALL_DIR

if [ -d "$INSTALL_DIR/wyoming-satellite" ]; then
    log "Wyoming Satellite repository already exists, pulling latest changes..."
    cd $INSTALL_DIR/wyoming-satellite
    git pull
else
    git clone https://github.com/rhasspy/wyoming-satellite.git
    cd $INSTALL_DIR/wyoming-satellite/
fi
script/setup

check_status "Wyoming Satellite installation"

# OpenWakeword setup
log "Setting up OpenWakeword..."
cd $INSTALL_DIR

if [ -d "$INSTALL_DIR/wyoming-openwakeword" ]; then
    log "OpenWakeword repository already exists, pulling latest changes..."
    cd $INSTALL_DIR/wyoming-openwakeword
    git pull
else
    git clone https://github.com/rhasspy/wyoming-openwakeword.git
    cd $INSTALL_DIR/wyoming-openwakeword/
fi
script/setup

check_status "OpenWakeword installation"

# Jarvis Controller Setup
log "Setting up Jarvis Controller"
cd $INSTALL_DIR/jarvis-satellite/
python3 -m venv .venv
source .venv/bin/activate
pip3 install --upgrade pip wheel setuptools
pip3 install -r requirements.txt
pip3 install -e .
deactivate
chmod +x $INSTALL_DIR/jarvis-satellite/respeaker_xvf3800/host_control/rpi_64bit/xvf_host
check_status "Jarvis Controller setup"


configure_digiamp_overlay() {
  local cfg
  for cfg in /boot/firmware/config.txt /boot/config.txt; do
    [[ -f "$cfg" ]] || continue

    if ! grep -q '^dtoverlay=iqaudio-dacplus' "$cfg"; then
      echo "dtoverlay=iqaudio-dacplus,unmute_amp" >> "$cfg"
      echo "Added DigiAMP+ overlay to $cfg"
    elif ! grep -q '^dtoverlay=iqaudio-dacplus,unmute_amp' "$cfg"; then
      # upgrade plain overlay to unmute_amp variant
      sed -i 's/^dtoverlay=iqaudio-dacplus.*/dtoverlay=iqaudio-dacplus,unmute_amp/' "$cfg"
      echo "Ensured unmute_amp option in $cfg"
    fi

    # Disable built-in analogue audio if present
    if grep -q '^dtparam=audio=on' "$cfg"; then
      sed -i 's/^dtparam=audio=on/# dtparam=audio=on (disabled by wyoming setup)/' "$cfg"
      echo "Disabled onboard audio in $cfg"
    fi
  done
}

echo "Configuring IQaudIO DigiAMP+ overlay"
configure_digiamp_overlay

log "Creating Respeaker controller"


# Create service files
log "Creating service files..."

# Jarvis Controller Service
cat > /etc/systemd/system/jarvis-controller.service << EOL
[Unit]
Description=Jarvis Controller

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/jarvis-satellite/.venv/bin/python3 -m jarvis_satellite \
 --uri 'tcp://127.0.0.1:10500' \
 --xvf-path '${INSTALL_DIR}/jarvis-satellite/respeaker_xvf3800/host_control/rpi_64bit/xvf_host'
WorkingDirectory=${INSTALL_DIR}/jarvis-satellite
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
EOL


# OpenWakeword Service
cat > /etc/systemd/system/wyoming-openwakeword.service << EOL
[Unit]
Description=Wyoming openWakeWord

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/wyoming-openwakeword/script/run \
    --uri 'tcp://0.0.0.0:10400' \
    --preload-model 'hey_jarvis' \
    --debug
WorkingDirectory=${INSTALL_DIR}/wyoming-openwakeword
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
EOL

# Wyoming Satellite Service
cat > /etc/systemd/system/wyoming-satellite.service << EOL
[Unit]
Description=Wyoming Satellite
Wants=network-online.target
After=network-online.target wyoming-openwakeword.service jarvis-controller.service
Requires=wyoming-openwakeword.service jarvis-controller.service

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/wyoming-satellite/script/run \
  --debug \
  --name 'Jarvis v1.0' \
  --uri 'tcp://0.0.0.0:10700' \
  --mic-command 'arecord -D plughw:CARD=Array,DEV=0 -r 16000 -c 1 -f S16_LE -t raw --buffer-time=100000 --period-time=50000' \
  --snd-command 'aplay -D plughw:CARD=DigiAMP,DEV=0 -r 22050 -c 1 -f S16_LE -t raw' \
  --wake-uri 'tcp://127.0.0.1:10400' \
  --event-uri 'tcp://127.0.0.1:10500' \
  --wake-word-name 'hey_jarvis'
WorkingDirectory=${INSTALL_DIR}/wyoming-satellite
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
EOL


# Set proper permissions
chown root:root /etc/systemd/system/*.service
chmod 644 /etc/systemd/system/*.service
check_status "Service file creation"

# Enable and start services
log "Enabling and starting services..."
systemctl daemon-reload
systemctl enable wyoming-satellite.service wyoming-openwakeword.service jarvis-controller.service
systemctl start wyoming-satellite.service wyoming-openwakeword.service jarvis-controller.service
check_status "Service activation"

log "Installation complete! Please reboot your system."
log "After reboot, you can check service status with:"
log "systemctl status wyoming-satellite"
log "systemctl status wyoming-openwakeword"
log "systemctl status jarvis-controller"