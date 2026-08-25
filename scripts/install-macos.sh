#!/usr/bin/env bash
# PortX installer — macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
set -euo pipefail

echo ""
echo "  PortX — Installer (macOS)"
echo "  ─────────────────────────────────────────"
echo ""

# ── Python version check & install ───────────────────────────────────────
# We require Python 3.12+ (modern, widely available via Homebrew)
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
  echo "  ⚠  Python ${MIN_MAJOR}.${MIN_MINOR}+ not found. Attempting to install via Homebrew..."
  echo ""

  # Ensure Homebrew is available
  if ! command -v brew &>/dev/null; then
    echo "  → Homebrew not found. Installing Homebrew first..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Source brew for Apple Silicon
    if [ -f /opt/homebrew/bin/brew ]; then
      eval "$(/opt/homebrew/bin/brew shellenv)"
    elif [ -f /usr/local/bin/brew ]; then
      eval "$(/usr/local/bin/brew shellenv)"
    fi
  fi

  echo "  → Installing/upgrading Python via Homebrew..."
  brew install python3 || brew upgrade python3

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
TMP_SCRIPT="$(mktemp "${TMPDIR:-/tmp}/portx_install_XXXXXX.py")"

cleanup() { rm -f "$TMP_SCRIPT"; }
trap cleanup EXIT

curl -fsSL "$INSTALLER_URL" -o "$TMP_SCRIPT"
"$PYTHON" "$TMP_SCRIPT"

# ── Add ~/.local/bin to PATH if not already there ────────────────────────
LOCAL_BIN="$HOME/.local/bin"

# macOS: prefer ~/.zshrc (zsh default since Catalina), fall back to ~/.bash_profile
if [ -n "${ZSH_VERSION:-}" ] || [ "$(basename "${SHELL:-}")" = "zsh" ]; then
  SHELL_RC="$HOME/.zshrc"
else
  SHELL_RC="$HOME/.bash_profile"
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
