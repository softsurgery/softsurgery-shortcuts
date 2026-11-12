
#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <host> <port>"
    echo "Example: $0 localhost 5000"
    exit 1
fi

HOST="$1"
PORT="$2"

sudo tailscale funnel reset
sudo tailscale funnel --bg "https+insecure://${HOST}:${PORT}"
sudo tailscale funnel status

