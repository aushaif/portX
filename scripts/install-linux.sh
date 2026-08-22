#!/usr/bin/env bash
# PortX Linux installer
# Usage: curl -fsSL https://your-portx-domain.com/install-linux.sh | bash
set -euo pipefail

echo ""
echo "  PortX — Linux Installer"
echo "  ─────────────────────────────────────────"
echo ""

# ── Require Python 3.8+ ───────────────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null; then
    version=$("$cmd" -c "import sys; print(sys.version_info >= (3, 8))" 2>/dev/null || echo "False")
    if [ "$version" = "True" ]; then
      PYTHON="$cmd"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "  ✗ Error: Python 3.8 or higher is required." >&2
  echo ""
  echo "  Install it using your package manager, e.g.:" >&2
  echo "    Ubuntu/Debian:  sudo apt install python3" >&2
  echo "    Fedora/RHEL:    sudo dnf install python3" >&2
  echo "    Arch:           sudo pacman -S python" >&2
  exit 1
fi

# ── Download and run the Python installer ────────────────────────────────
INSTALLER_URL="https://raw.githubusercontent.com/your-org/portx/main/installer/portx_install.py"
TMP_SCRIPT="$(mktemp /tmp/portx_install_XXXXXX.py)"

cleanup() { rm -f "$TMP_SCRIPT"; }
trap cleanup EXIT

# Use curl if available, fall back to wget
if command -v curl &>/dev/null; then
  curl -fsSL "$INSTALLER_URL" -o "$TMP_SCRIPT"
elif command -v wget &>/dev/null; then
  wget -qO "$TMP_SCRIPT" "$INSTALLER_URL"
else
  echo "  ✗ Error: curl or wget is required to download the installer." >&2
  exit 1
fi

"$PYTHON" "$TMP_SCRIPT"
