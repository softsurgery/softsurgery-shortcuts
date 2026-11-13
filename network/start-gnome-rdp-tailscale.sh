
#!/usr/bin/env bash

set -euo pipefail

# ==========================================
# GNOME RDP + TAILSCALE BOOTSTRAP
# Ubuntu
# ==========================================

echo "=================================="
echo " GNOME Remote Desktop Bootstrap"
echo "=================================="

# 1. Check that script isn't running as root
if [[ "$EUID" -eq 0 ]]; then
    echo "Run this script as your normal desktop user, NOT with sudo."
    exit 1
fi

# 2. Install dependencies
echo "[1/8] Installing dependencies..."

sudo apt-get update
sudo apt-get install -y \
    gnome-remote-desktop \
    openssl

# 3. Configure certificate directory
echo "[2/8] Preparing TLS certificates..."

CERT_DIR="$HOME/.local/share/gnome-remote-desktop"

mkdir -p "$CERT_DIR"

CERT="$CERT_DIR/rdp.crt"
KEY="$CERT_DIR/rdp.key"

# Generate certificate only if missing
if [[ ! -f "$CERT" || ! -f "$KEY" ]]; then

    openssl req -x509 -newkey rsa:4096 \
        -keyout "$KEY" \
        -out "$CERT" \
        -sha256 \
        -days 365 \
        -nodes \
        -subj "/CN=$(hostname)"

fi

chmod 600 "$KEY"
chmod 644 "$CERT"

# 4. Configure RDP TLS
echo "[3/8] Configuring RDP certificates..."

grdctl rdp set-tls-cert "$CERT"
grdctl rdp set-tls-key "$KEY"

# 5. Configure RDP credentials
echo "[4/8] Configuring RDP credentials..."

read -r -p "RDP username [$USER]: " RDP_USER
RDP_USER="${RDP_USER:-$USER}"

read -r -s -p "Enter RDP password: " RDP_PASS
echo

if [[ -z "$RDP_PASS" ]]; then
    echo "Password cannot be empty."
    exit 1
fi

grdctl rdp set-credentials "$RDP_USER" "$RDP_PASS"

unset RDP_PASS

# 6. Enable remote desktop
echo "[5/8] Enabling RDP..."

grdctl rdp disable-view-only
grdctl rdp enable

# 7. Restart service
echo "[6/8] Restarting GNOME Remote Desktop..."

systemctl --user restart gnome-remote-desktop.service

# 8. Display status
echo "[7/8] Checking RDP status..."

grdctl status

echo
echo "[8/8] Checking Tailscale..."

if command -v tailscale >/dev/null 2>&1; then

    tailscale status

    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || true)

    echo
    echo "Tailscale IPv4: ${TAILSCALE_IP:-Unavailable}"

else

    echo "Tailscale is not installed."
fi

echo
echo "=================================="
echo " RDP BOOTSTRAP FINISHED"
echo "=================================="

echo "RDP username: $RDP_USER"
echo "RDP port:     3389"

if [[ -n "${TAILSCALE_IP:-}" ]]; then
    echo "Connect to:   ${TAILSCALE_IP}:3389"
fi

echo
echo "Verify listening port with:"
echo "sudo ss -lntp | grep 3389"

echo
echo "Use an RDP client to connect."
