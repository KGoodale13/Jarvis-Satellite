#!/bin/bash

# This script will clone the repo and execute the install.sh script.

INSTALL_DIR="/opt"

if [ -d "$INSTALL_DIR/jarvis-satellite" ]; then
    echo "Repository already exists, pulling latest changes..."
    cd $INSTALL_DIR/jarvis-satellite
    git fetch origin
    git reset --hard origin/main
    git submodule update --init --recursive
else
    git clone --recursive https://github.com/KGoodale13/Jarvis-Satellite.git $INSTALL_DIR/jarvis-satellite
    cd $INSTALL_DIR/jarvis-satellite
fi

chmod +x install.sh
sudo ./install.sh