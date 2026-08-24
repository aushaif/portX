# PortX Installation & Homebrew Fix - Implementation Summary

## What Was Done

### 1. ✅ Changed Installer Architecture

**Goal**: Install PortX CLI to `~/.local/bin/portx` as a standalone executable, with `~/.portx/` containing only runtime data.

**Changes**:
- Modified `installer/portx_install.py`:
  - No longer clones entire repo to `~/.portx/src/`
  - Installs CLI modules to `~/.local/lib/portx/`
  - Creates executable wrapper at `~/.local/bin/portx`
  - Only stores FRP binary in `~/.portx/bin/frpc`
  - Creates runtime directories: `~/.portx/tunnels/`, `~/.portx/logs/`

**Result**:
```
~/.local/bin/portx          # CLI executable (works globally)
~/.local/lib/portx/         # CLI modules
~/.portx/bin/frpc           # FRP binary only
~/.portx/tunnels/           # Tunnel configs
~/.portx/logs/              # Logs
~/.portx/tunnels.toml       # State database
```

### 2. ✅ Fixed Homebrew Installation

**Problem**: `brew install portx` was installing an unrelated PortX.app cask.

**Solution**:
- Created new formula: `Formula/portx-cli.rb` (unique name)
- Deleted old formula: `Formula/portx.rb`
- Updated README with correct tap instructions

**New Homebrew Install**:
```bash
brew tap aushaif/portx
brew install portx-cli  # Note: portx-CLI, not just portx
```

**Homebrew Setup Needed**:
- Create tap repository: `github.com/aushaif/homebrew-portx`
- Copy `Formula/portx-cli.rb` to that repo
- See `HOMEBREW_TAP_SETUP.md` for full instructions

### 3. ✅ Updated Uninstall

**Changes to `cli/commands.py`**:
- `cmd_uninstall()` now removes:
  - `~/.local/bin/portx` (CLI executable)
  - `~/.portx/` (runtime data)
- Detects Homebrew installations and provides correct instructions
- Homebrew preserves `~/.portx/` by default (user can manually remove)

### 4. ✅ Added Cleanup Command

**New command**: `portx cleanup [--force]`

**Purpose**: Handle orphaned files and state mismatches

**Functionality**:
```bash
portx cleanup         # Remove orphaned configs/logs
portx cleanup --force # Also remove stopped tunnel records
```

**Implementation**:
- Added `cmd_cleanup()` to `cli/commands.py`
- Added command parser to `cli/portx.py`
- Updated help text and README

### 5. ✅ Unified Install Scripts

**Changes**:
- Updated `scripts/install-macos.sh` to work on both macOS and Linux
- Made `scripts/install-linux.sh` a symlink to `install-macos.sh`
- Fixed shell detection for both bash and zsh
- Improved PATH setup for different platforms

### 6. ✅ Fixed State Initialization

**Changes to `cli/state.py`**:
- Auto-creates `tunnels.toml` if it doesn't exist
- Prevents "file not found" errors on first run
- Ensures clean state for new installations

### 7. ✅ Documented Old Tunnel Issue

**Problem**: Old tunnel (https://boka.infinitynoob.lol/) still running when local state was lost

**Solution**:
- Added troubleshooting section to README
- Explained why tunnels persist on server
- Provided cleanup commands
- Added prevention tips

**Why it happens**:
1. Tunnel created with old installation
2. User deleted `~/.portx/` manually
3. Local state lost, but FRP client might still be connected
4. Server keeps allocation until FRP disconnects

**How to fix**:
1. Run `portx cleanup --force` to reset local state
2. Wait for server to clean up inactive connections
3. Contact server admin to restart FRP server if needed

### 8. ✅ Updated Documentation

**Changes to `README.md`**:
- Updated installation instructions
- Added Homebrew warning about name conflict
- Added troubleshooting section
- Updated project structure
- Added cleanup command documentation
- Updated uninstall instructions

## Files Modified

| File | Changes |
|------|---------|
| `installer/portx_install.py` | Complete rewrite of installation logic |
| `cli/commands.py` | Updated uninstall, added cleanup command |
| `cli/portx.py` | Added cleanup command, updated help |
| `cli/state.py` | Added auto-initialization of tunnels.toml |
| `Formula/portx-cli.rb` | New Homebrew formula (created) |
| `Formula/portx.rb` | Deleted (conflicted with existing cask) |
| `scripts/install-macos.sh` | Updated for cross-platform support |
| `scripts/install-linux.sh` | Made symlink to install-macos.sh |
| `README.md` | Major updates to installation & troubleshooting |

## Files Created

| File | Purpose |
|------|---------|
| `INSTALL_CHANGES.md` | Detailed changelog of installation architecture changes |
| `HOMEBREW_TAP_SETUP.md` | Guide for setting up Homebrew tap repository |
| `IMPLEMENTATION_SUMMARY.md` | This file - overview of all changes |

## Installation Methods

### Method 1: Quick Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

Works on: macOS (Intel & ARM), Linux (x86_64 & ARM64)

### Method 2: Homebrew (macOS only)

**⚠️ Requires tap setup first** (see `HOMEBREW_TAP_SETUP.md`)

```bash
brew tap aushaif/portx
brew install portx-cli
```

### Method 3: Manual Installation

```bash
# Clone repo
git clone https://github.com/aushaif/portX.git
cd portX

# Run installer
python3 installer/portx_install.py
```

## What Needs to Be Done Next

### 1. Create Homebrew Tap (Required for Homebrew installs)

```bash
# On GitHub, create: aushaif/homebrew-portx
# Clone and setup
git clone https://github.com/aushaif/homebrew-portx.git
cd homebrew-portx
mkdir Formula
cp /path/to/portX/Formula/portx-cli.rb Formula/
git add Formula/portx-cli.rb
git commit -m "Add portx-cli formula"
git push
```

See `HOMEBREW_TAP_SETUP.md` for details.

### 2. Test Installation

```bash
# Test quick install
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash

# Verify
which portx
portx --help
ls -la ~/.local/bin/portx
ls -la ~/.portx/

# Test functionality
portx http 8080
portx list
portx cleanup
```

### 3. Handle Old Tunnel (boka.infinitynoob.lol)

**Option A**: Wait for auto-cleanup
- FRP connection will eventually timeout
- Server will release the allocation

**Option B**: Server restart
```bash
# On VPS
sudo systemctl restart frps
```

**Option C**: Client cleanup
```bash
portx cleanup --force
```

### 4. Update Repository

```bash
cd /Users/infinitynoob/Desktop/portx
git add -A
git commit -m "Refactor: New installation architecture and Homebrew fix

- Install CLI to ~/.local/bin/portx instead of symlinking from ~/.portx/src
- Store only runtime data in ~/.portx/ (bin/frpc, tunnels/, logs/, tunnels.toml)
- Create portx-cli Homebrew formula to avoid conflict with existing portx cask
- Add cleanup command for orphaned files
- Unify install scripts for macOS and Linux
- Add troubleshooting docs for old tunnel issues
- Update uninstall to match new architecture"

git push origin main
```

## Testing Checklist

- [ ] Quick install works on macOS
- [ ] Quick install works on Linux
- [ ] Executable is at `~/.local/bin/portx`
- [ ] FRP binary is at `~/.portx/bin/frpc`
- [ ] No `~/.portx/src/` directory created
- [ ] `portx http 8080` works
- [ ] `portx list` shows tunnels
- [ ] `portx stop` works
- [ ] `portx cleanup` works
- [ ] `portx uninstall` removes everything
- [ ] Homebrew tap setup complete
- [ ] `brew install portx-cli` works
- [ ] Homebrew uninstall works

## Common Issues & Solutions

### Issue: "portx: command not found"

**Solution**:
```bash
# Check if installed
ls -la ~/.local/bin/portx

# Add to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Issue: "FRP binary not found"

**Solution**:
```bash
# Check if exists
ls -la ~/.portx/bin/frpc

# Reinstall
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

### Issue: Old tunnel still showing

**Solution**:
```bash
portx cleanup --force
```

Or wait for server to clean up, or restart FRP server.

### Issue: Homebrew installs wrong PortX

**Solution**:
```bash
brew uninstall portx
brew tap aushaif/portx
brew install portx-cli
```

## Architecture Comparison

### Before
```
User runs: portx
  ↓
Symlink: ~/.local/bin/portx -> ~/.portx/src/portx
  ↓
Runs: ~/.portx/src/cli/portx.py
  ↓
Imports: ~/.portx/src/cli/*.py
```

**Problem**: Deleting source breaks everything

### After
```
User runs: portx
  ↓
Executable: ~/.local/bin/portx
  ↓
Imports: ~/.local/lib/portx/*.py
  ↓
Runs standalone (no source dependency)
```

**Benefit**: Source-independent, survives repository deletion

## Summary

All required changes have been implemented:

✅ Installer no longer stores full repository in `~/.portx/`
✅ CLI installs to `~/.local/bin/portx` as standalone executable
✅ `~/.portx/` contains only runtime data (frpc, tunnels, logs)
✅ Homebrew formula renamed to `portx-cli` to avoid conflicts
✅ Uninstall updated to remove correct files
✅ Cleanup command added for orphaned files
✅ Install scripts unified for macOS/Linux
✅ Old tunnel issue documented with solutions
✅ State initialization fixed
✅ Documentation updated

**Next Step**: Create Homebrew tap repository and test installations.
