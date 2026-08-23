#!/usr/bin/env bash
# PortX macOS installer
# Usage: curl -fsSL https://your-portx-domain.com/install-macos.sh | bash
set -euo pipefail

echo ""
echo "  PortX — macOS Installer"
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
  echo "    Install it from https://www.python.org/downloads/" >&2
  exit 1
fi

# ── Download and run the Python installer ────────────────────────────────
INSTALLER_URL="https://raw.githubusercontent.com/aushaif/portX/main/installer/portx_install.py"
TMP_SCRIPT="$(mktemp /tmp/portx_install_XXXXXX.py)"

cleanup() { rm -f "$TMP_SCRIPT"; }
trap cleanup EXIT

curl -fsSL "$INSTALLER_URL" -o "$TMP_SCRIPT"
"$PYTHON" "$TMP_SCRIPT"
