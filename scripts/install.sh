#!/usr/bin/env bash
# PortX installer — macOS & Linux
# Usage: curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install.sh | bash

{
set -euo pipefail

# ── Detect OS ────────────────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
  Darwin) OS_NAME="macOS" ;;
  Linux)  OS_NAME="Linux" ;;
  *)
    echo "  ✗ Unsupported operating system: $OS" >&2
    echo "    PortX supports macOS and Linux only." >&2
    exit 1
    ;;
esac

echo ""
echo "  PortX — Installer ($OS_NAME)"
echo "  ─────────────────────────────────────────"
echo ""

# ── Python version check & install ───────────────────────────────────────
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

  if [ "$OS_NAME" = "macOS" ]; then
    # ── macOS: install via Homebrew ──────────────────────────────────────
    if ! command -v brew &>/dev/null; then
      echo "  → Homebrew not found. Installing Homebrew first..."
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      # Source brew for Apple Silicon
      if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        export PATH="/opt/homebrew/bin:$PATH"
      elif [ -f /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
        export PATH="/usr/local/bin:$PATH"
      fi
    fi

    echo "  → Installing/upgrading Python via Homebrew..."
    brew install python3 || brew upgrade python3

    # Re-evaluate shellenv just in case
    if command -v brew &>/dev/null; then
      eval "$(brew shellenv)"
    fi

  else
    # ── Linux: install via system package manager ────────────────────────
    if command -v apt-get &>/dev/null; then
      echo "  → Installing Python via apt-get..."
      sudo apt-get update -qq
      sudo apt-get install -y python3 python3-pip
    elif command -v dnf &>/dev/null; then
      echo "  → Installing Python via dnf..."
      sudo dnf install -y python3 python3-pip
    elif command -v yum &>/dev/null; then
      echo "  → Installing Python via yum..."
      sudo yum install -y python3 python3-pip
    elif command -v pacman &>/dev/null; then
      echo "  → Installing Python via pacman..."
      sudo pacman -Sy --noconfirm python python-pip
    elif command -v zypper &>/dev/null; then
      echo "  → Installing Python via zypper..."
      sudo zypper install -y python3 python3-pip
    else
      echo "  ✗ No supported package manager found." >&2
      echo "    Please install Python ${MIN_MAJOR}.${MIN_MINOR}+ manually: https://www.python.org/downloads/" >&2
      exit 1
    fi
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
TMP_SCRIPT="$(mktemp "${TMPDIR:-/tmp}/portx_install_XXXXXX.py")"

cleanup() { rm -f "$TMP_SCRIPT"; }
trap cleanup EXIT

curl -fsSL "$INSTALLER_URL" -o "$TMP_SCRIPT"
"$PYTHON" "$TMP_SCRIPT"

# ── Add ~/.local/bin to PATH if not already there ────────────────────────
LOCAL_BIN="$HOME/.local/bin"

# Detect shell rc file
if [ -n "${ZSH_VERSION:-}" ] || [ "$(basename "${SHELL:-}")" = "zsh" ]; then
  SHELL_RC="$HOME/.zshrc"
elif [ "$OS_NAME" = "macOS" ]; then
  SHELL_RC="$HOME/.zshrc"         # zsh is the macOS default since Catalina
else
  SHELL_RC="$HOME/.bashrc"        # bash is the Linux default
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
echo "  ─────────────────────────────────────────"
echo "  ✓ Installation complete!"
echo "  → To finish setup, configure your API token:"
echo "      portx api <your-token>"
echo ""

}
