# Shortcuts Directory

This repository contains various utility scripts and shortcuts. Below is an index detailing the tracked scripts available in this repository.

## Root Utility Scripts

* **`update-ag.py`**: The Antigravity Manager script. It downloads and manages installations of the Antigravity CLI, Antigravity 2.0, and the Standalone Antigravity IDE. It can detect current installed versions and update them from Google's servers.
* **`remove-old-snaps.sh`**: A cleanup bash script that removes old, disabled revisions of snap packages to free up disk space on the system.
* **`run-emu.sh`**: A simple bash script to launch the Android emulator (device `Pixel_4_XL`) with GPU acceleration (`angle`) and skipping snapshots for a fresh boot.

## Tools and Helpers

* **`file-serving/serve-file-py-2.7-builder.sh`**: A builder script that writes a Python 2.7 HTTP file server script (`serve-file.py`). Designed to quickly serve a single file for download over a specific port and automatically configure the firewall (via `firewall-cmd`) to allow inbound connections.
