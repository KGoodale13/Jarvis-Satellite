#!/bin/bash

# This script will clone the repo and execute the install.sh script.

INSTALL_DIR="/opt"

git clone https://github.com/KGoodale13/Jarvis-Satellite.git $INSTALL_DIR/jarvis-satellite
cd $INSTALL_DIR/jarvis-satellite
chmod +x install.sh
sudo ./install.sh