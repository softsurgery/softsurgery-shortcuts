# Shortcuts Directory

This repository contains various utility scripts and shortcuts. Below is an index detailing the tracked scripts and tools available in this repository.

## Root Utility Scripts

* **`update-ag.py`**: The Antigravity Manager script. It downloads and manages installations of the Antigravity CLI, Antigravity 2.0, and the Standalone Antigravity IDE. It can detect current installed versions and update them from Google's servers.
* **`remove-old-snaps.sh`**: A cleanup bash script that removes old, disabled revisions of snap packages to free up disk space on the system.
* **`run-emu.sh`**: A simple bash script to launch the Android emulator (device `Pixel_4_XL`) with GPU acceleration (`angle`) and skipping snapshots for a fresh boot.

## File Serving

Fast, secure, and self-contained HTTP(S) file serving tools with web UI, Basic Authentication, download, streaming upload, and automatic firewall port configuration (supporting Debian/Ubuntu distros via `ufw`, CentOS/RHEL distros via `firewall-cmd`, and `iptables`).

* **`file-serving/serve-file-py-3.py`**:
  * Standalone **Python 3** secure file server.
  * **Zero external dependencies**: Built entirely with the Python 3 standard library (`http.server`, `ssl.SSLContext`, `urllib.parse`, and custom chunked multipart stream parser).
  * Features HTTPS encryption (generates on-the-fly self-signed certificate and cleans it up on exit), HTTP Basic Authentication (with auto-generated or custom password), browser-based UI with an upload progress bar, memory-efficient streaming file downloads, and safe multipart uploads.
  * **Usage**:
    ```bash
    ./file-serving/serve-file-py-3.py <file_to_serve> <port> [password]
    ```
* **`file-serving/serve-file-py-3-builder.sh`**:
  * Bash builder script that generates the standalone Python 3 `serve-file.py`.
* **`file-serving/serve-file-py-2.7.py`**:
  * Standalone **Python 2.7** secure file server with HTTPS, Basic Authentication, and file upload/download functionality.
  * **Usage**:
    ```bash
    python2 ./file-serving/serve-file-py-2.7.py <file_to_serve> <port> [password]
    ```
* **`file-serving/serve-file-py-2.7-builder.sh`**:
  * Bash builder script that generates the standalone Python 2.7 `serve-file.py`.

## macOS Utilities

* **`macos/gpu_usage.sh`**: Continuous GPU power and usage monitoring on macOS using `powermetrics`.
* **`macos/xcode-cleanup.sh`**: Interactive cleanup script for Apple developers to safely reclaim disk space by removing Xcode DerivedData, unavailable simulator runtimes, device support symbols, and old build archives (supports `--dry-run`).

## Monaco IDE Shortcut Builder

* **`monaco-ide-shortcut-builder/open-projects.c`**: C utility to quickly open configured local and remote projects into Monaco/VS Code-compatible IDEs.
* **`monaco-ide-shortcut-builder/projects.example.conf`**: Example configuration file template defining `[local]` and `[server]` workspace paths.
