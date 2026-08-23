#!/usr/bin/env bash
# PortX VPS Setup Script
# Run this ONCE on your VPS (portx.infinitynoob.lol) to deploy frps + PortX server.
#
# Tested on Ubuntu 22.04 / Debian 12.
# Must be run as root (or with sudo).
set -euo pipefail

PORTX_DIR="/opt/portx"
FRP_VERSION=""   # leave empty to auto-detect latest

echo ""
echo "  PortX VPS Setup"
echo "  ─────────────────────────────────────────"
echo ""

# ── Helpers ───────────────────────────────────────────────────────────────
info()  { echo "  → $*"; }
ok()    { echo "  ✓ $*"; }
fail()  { echo "  ✗ $*" >&2; exit 1; }

# ── Require root ──────────────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || fail "Please run as root: sudo bash setup.sh"

# ── Detect architecture ───────────────────────────────────────────────────
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)          FRP_ARCH="linux_amd64"  ;;
  aarch64|arm64)   FRP_ARCH="linux_arm64"  ;;
  *) fail "Unsupported architecture: $ARCH" ;;
esac
ok "Detected architecture: $FRP_ARCH"

# ── Install Python 3 (for portx_server.py) ────────────────────────────────
info "Installing Python 3..."
apt-get update -qq
apt-get install -y -qq python3 curl tar
ok "Python 3 installed"

# ── Fetch latest FRP version ──────────────────────────────────────────────
if [ -z "$FRP_VERSION" ]; then
  info "Detecting latest FRP version..."
  FRP_VERSION="$(curl -fsSL \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/fatedier/frp/releases/latest" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'].lstrip('v'))")"
  ok "Latest FRP version: v${FRP_VERSION}"
fi

FRP_ARCHIVE="frp_${FRP_VERSION}_${FRP_ARCH}.tar.gz"
FRP_URL="https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/${FRP_ARCHIVE}"

# ── Download & install frps ───────────────────────────────────────────────
info "Downloading FRP..."
TMP="$(mktemp -d)"
curl -L --progress-bar -o "$TMP/$FRP_ARCHIVE" "$FRP_URL"
ok "Download complete"

info "Installing frps..."
tar -xzf "$TMP/$FRP_ARCHIVE" -C "$TMP"
mkdir -p /usr/local/bin
cp "$TMP/frp_${FRP_VERSION}_${FRP_ARCH}/frps" /usr/local/bin/frps
chmod +x /usr/local/bin/frps
rm -rf "$TMP"
ok "frps installed at /usr/local/bin/frps"

# ── Install PortX server files ────────────────────────────────────────────
info "Installing PortX server..."
mkdir -p "$PORTX_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/portx_server.py" "$PORTX_DIR/"
cp "$SCRIPT_DIR/frps.toml"       "$PORTX_DIR/"

mkdir -p /var/log/frps
ok "PortX server files installed at $PORTX_DIR"

# ── Create systemd service: frps ──────────────────────────────────────────
info "Creating frps systemd service..."
cat > /etc/systemd/system/frps.service <<EOF
[Unit]
Description=FRP Server (PortX)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frps -c ${PORTX_DIR}/frps.toml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
ok "frps service created"

# ── Create systemd service: portx-api ─────────────────────────────────────
info "Creating portx-api systemd service..."
cat > /etc/systemd/system/portx-api.service <<EOF
[Unit]
Description=PortX API Server
After=network.target

[Service]
Type=simple
WorkingDirectory=${PORTX_DIR}
ExecStart=/usr/bin/python3 ${PORTX_DIR}/portx_server.py
Restart=on-failure
RestartSec=5

# Override any of these to customise:
# Environment="PORTX_API_PORT=8765"
# Environment="PORTX_FRPS_HOST=portx.infinitynoob.lol"
# Environment="PORTX_FRPS_PORT=7000"

[Install]
WantedBy=multi-user.target
EOF
ok "portx-api service created"

# ── Enable & start services ───────────────────────────────────────────────
info "Starting services..."
systemctl daemon-reload
systemctl enable frps portx-api
systemctl restart frps portx-api

sleep 2

frps_status=$(systemctl is-active frps    2>/dev/null || true)
api_status=$(systemctl  is-active portx-api 2>/dev/null || true)

[ "$frps_status" = "active" ]    && ok "frps is running"    || fail "frps failed to start — check: journalctl -u frps"
[ "$api_status"  = "active" ]    && ok "portx-api is running" || fail "portx-api failed to start — check: journalctl -u portx-api"

# ── Open firewall ports ───────────────────────────────────────────────────
if command -v ufw &>/dev/null; then
  info "Opening firewall ports (ufw)..."
  ufw allow 7000/tcp   comment "frps bind port"    2>/dev/null || true
  ufw allow 80/tcp     comment "frps HTTP vhost"   2>/dev/null || true
  ufw allow 443/tcp    comment "frps HTTPS vhost"  2>/dev/null || true
  ufw allow 8765/tcp   comment "PortX API"         2>/dev/null || true
  ufw allow 30000:31999/tcp comment "PortX TCP tunnels" 2>/dev/null || true
  ufw allow 32000:33999/udp comment "PortX UDP tunnels" 2>/dev/null || true
  ok "Firewall rules applied"
fi

echo ""
echo "  ─────────────────────────────────────────"
ok "PortX VPS setup complete!"
echo ""
echo "  Services running:"
echo "    frps       → listens on :7000 (frpc connections)"
echo "    portx-api  → listens on :8765 (PortX CLI requests)"
echo ""
echo "  Verify with:"
echo "    systemctl status frps portx-api"
echo "    curl http://localhost:8765/health"
echo ""
