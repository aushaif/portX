#!/usr/bin/env bash
# PortX installer — Linux
# Usage: curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-linux.sh | bash
set -euo pipefail

echo ""
echo "  PortX — Installer (Linux)"
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

# ── Add ~/.local/bin to PATH if not already there ────────────────────────
LOCAL_BIN="$HOME/.local/bin"

# Linux: prefer ~/.bashrc, fall back to ~/.zshrc if zsh is the active shell
if [ -n "${ZSH_VERSION:-}" ] || [ "$(basename "${SHELL:-}")" = "zsh" ]; then
  SHELL_RC="$HOME/.zshrc"
else
  SHELL_RC="$HOME/.bashrc"
fi

if ! grep -q "$LOCAL_BIN" "$SHELL_RC" 2>/dev/null; then
  echo "" >> "$SHELL_RC"
  echo "# Added by PortX installer" >> "$SHELL_RC"
  echo "export PATH=\"$LOCAL_BIN:\$PATH\"" >> "$SHELL_RC"
  echo ""
  echo "  ✓ Added ~/.local/bin to PATH in $SHELL_RC"
  echo "  → Run 'source $SHELL_RC' or restart your terminal to apply."
fi

echo ""
echo "  Run 'portx --help' to get started."
echo ""
