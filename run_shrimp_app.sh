#!/bin/bash

# 1. Kill any existing camera/app processes to free the hardware
sudo pkill -9 rpicam-vid
sudo pkill -9 ffmpeg
pkill -f app.py

# 2. Set Environment for Wayland (RPi5 Default)
export QT_QPA_PLATFORM=wayland
export QT_AUTO_SCREEN_SCALE_FACTOR=0

# 3. Navigate to the NEW directory
cd ~/Documents/ShrimpAppIMX/shrimpMachineAppIMX

# 4. Run using the virtual environment
# (Assuming your venv is still inside this folder)
./venv/bin/python3 app.py