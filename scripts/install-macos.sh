#!/usr/bin/env bash
# PortX installer — Linux
# Usage: curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-linux.sh | bash
set -euo pipefail

echo ""
echo "  PortX — Installer (Linux)"
echo "  ─────────────────────────────────────────"
echo ""

# ── Python version check & install ───────────────────────────────────────
# We require Python 3.12+ (modern, available in all major distros)
MIN_MAJOR=3
MIN_MINOR=12

_get_python_version() {
  local cmd="$1"
  command -v "$cmd" &>/dev/null || return 1
  "$cmd" -c "import sys; print(sys.version_info.major, sys.version_info.minor)" 2>/dev/null
}

_python_is_new_enough() {
  local cmd="$1"
  local ver
  ver=$(_get_python_version "$cmd" 2>/dev/null) || return 1
  local major minor
  major=$(echo "$ver" | awk '{print $1}')
  minor=$(echo "$ver" | awk '{print $2}')
  [ "$major" -gt "$MIN_MAJOR" ] || { [ "$major" -eq "$MIN_MAJOR" ] && [ "$minor" -ge "$MIN_MINOR" ]; }
}

PYTHON=""
for cmd in python3.13 python3.12 python3 python; do
  if _python_is_new_enough "$cmd" 2>/dev/null; then
    PYTHON="$cmd"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "  ⚠  Python ${MIN_MAJOR}.${MIN_MINOR}+ not found. Attempting to install..."
  echo ""

  INSTALLED=false

  # Try apt-get (Debian/Ubuntu)
  if command -v apt-get &>/dev/null; then
    echo "  → Installing Python via apt-get..."
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-pip
    INSTALLED=true

  # Try dnf (Fedora/RHEL 8+)
  elif command -v dnf &>/dev/null; then
    echo "  → Installing Python via dnf..."
    sudo dnf install -y python3 python3-pip
    INSTALLED=true

  # Try yum (CentOS/RHEL 7)
  elif command -v yum &>/dev/null; then
    echo "  → Installing Python via yum..."
    sudo yum install -y python3 python3-pip
    INSTALLED=true

  # Try pacman (Arch Linux)
  elif command -v pacman &>/dev/null; then
    echo "  → Installing Python via pacman..."
    sudo pacman -Sy --noconfirm python python-pip
    INSTALLED=true

  # Try zypper (openSUSE)
  elif command -v zypper &>/dev/null; then
    echo "  → Installing Python via zypper..."
    sudo zypper install -y python3 python3-pip
    INSTALLED=true
  fi

  if [ "$INSTALLED" = false ]; then
    echo "  ✗ No supported package manager found." >&2
    echo "    Please install Python ${MIN_MAJOR}.${MIN_MINOR}+ manually:" >&2
    echo "    https://www.python.org/downloads/" >&2
    exit 1
  fi

  # Re-locate Python after install
  for cmd in python3.13 python3.12 python3; do
    if _python_is_new_enough "$cmd" 2>/dev/null; then
      PYTHON="$cmd"
      break
    fi
  done

  if [ -z "$PYTHON" ]; then
    echo "" >&2
    echo "  ✗ Could not install Python ${MIN_MAJOR}.${MIN_MINOR}+." >&2
    echo "    Please install it manually from https://www.python.org/downloads/" >&2
    exit 1
  fi

  echo "  ✓ Python installed successfully."
  echo ""
else
  VER=$(_get_python_version "$PYTHON")
  echo "  ✓ Python $VER found: $PYTHON"
  echo ""
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
