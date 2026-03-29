#!/bin/bash

# This script will clone the repo and execute the install.sh script.

INSTALL_DIR="/opt"

if [ -d "$INSTALL_DIR/jarvis-satellite" ]; then
    echo "Repository already exists, updating checkout..."
    cd $INSTALL_DIR/jarvis-satellite
    git fetch origin
    git checkout main
    git pull --ff-only origin main
    git submodule sync --recursive
    git submodule update --init --recursive
else
    git clone --recursive https://github.com/KGoodale13/Jarvis-Satellite.git $INSTALL_DIR/jarvis-satellite
    cd $INSTALL_DIR/jarvis-satellite
fi

chmod +x install.sh
sudo ./install.sh
