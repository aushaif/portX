# PortX Installation Architecture Changes

## Summary

Overhauled the PortX installer to use a clean, minimal runtime directory structure and fixed Homebrew installation conflicts.

## Key Changes

### 1. New Installation Layout

**Before:**
```
~/.portx/
├── src/              # Entire repository cloned here
│   ├── cli/
│   ├── server/
│   ├── installer/
│   └── ...
├── bin/frpc
└── ~/.local/bin/portx -> ~/.portx/src/portx (symlink)
```

**After:**
```
~/.local/
└── bin/
    └── portx         # Standalone executable
~/.portx/
├── bin/
│   └── frpc         # FRP client binary only
├── tunnels/         # Per-tunnel FRP configs
├── logs/            # Tunnel logs
└── tunnels.toml     # Tunnel state database
```

### 2. Benefits

- **Clean separation**: CLI is globally installed, runtime data is isolated
- **Survives deletion**: Deleting the source repository doesn't break the installed CLI
- **No source dependency**: `~/.portx/` contains only runtime data
- **Proper uninstall**: Clear distinction between what gets removed

### 3. Installation Files

**CLI Installation:**
- Executable: `~/.local/bin/portx`
- Library: `~/.local/lib/portx/` (CLI modules)

**Runtime Data:**
- FRP binary: `~/.portx/bin/frpc`
- Tunnel configs: `~/.portx/tunnels/*.toml`
- Logs: `~/.portx/logs/*.log`
- State: `~/.portx/tunnels.toml`

### 4. Homebrew Formula Changes

**Problem:**
- `brew install portx` was installing an unrelated PortX.app cask
- Name conflict with existing Homebrew package

**Solution:**
- Created new formula: `portx-cli.rb` (unique name)
- Updated tap instructions: `brew tap aushaif/portx && brew install portx-cli`
- Removed old `portx.rb` formula
- Added clear warnings in README about name conflict

**Homebrew Installation Layout:**
```
/opt/homebrew/
├── bin/portx                    # Wrapper script
├── Cellar/portx-cli/2.0.0/     # Installation
└── var/portx/                   # Runtime data
    ├── bin/frpc
    ├── tunnels/
    ├── logs/
    └── tunnels.toml
```

### 5. Unified Install Script

- Merged `install-macos.sh` and `install-linux.sh`
- Single script works for both platforms
- `install-linux.sh` is now a symlink to `install-macos.sh`

### 6. Uninstall Updates

**Standard Installation:**
```bash
portx uninstall
```
Removes:
- `~/.local/bin/portx`
- `~/.portx/` (all runtime data)

**Homebrew Installation:**
```bash
brew uninstall portx-cli
rm -rf ~/.portx  # Optional: manual cleanup of runtime data
```

### 7. New Cleanup Command

Added `portx cleanup` to handle orphaned files:

```bash
portx cleanup              # Remove orphaned config/log files
portx cleanup --force      # Also remove stopped tunnel records
```

Useful when:
- Reinstalling after deleting `~/.portx/`
- Cleaning up after manual file operations
- Syncing state with actual files

### 8. Old Tunnel Issue Fix

**Problem:**
- Old tunnel (e.g., `https://boka.infinitynoob.lol/`) still active on server
- Local state was lost (deleted `~/.portx/`)
- Can't stop the tunnel because client doesn't know about it

**Solutions:**
1. **Server-side**: Tunnel auto-expires when FRP client disconnects
2. **Client-side**: Use `portx cleanup --force` to reset local state
3. **Prevention**: Always use `portx stop` or `portx remove` properly

**Added to README:**
- Troubleshooting section
- Explanation of orphaned tunnels
- Prevention tips

### 9. State Initialization

- Added automatic `tunnels.toml` creation on first run
- Prevents "file not found" errors
- Ensures clean state for new installations

## Installation Commands

### Quick Install (macOS/Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

### Homebrew (macOS)

```bash
brew tap aushaif/portx
brew install portx-cli
```

**⚠️ Important:** Do NOT use `brew install portx` — that's a different app!

## Migration Guide

If you have an existing installation:

### Option 1: Clean Reinstall (Recommended)

```bash
# Stop all tunnels first
portx stop --all

# Uninstall old version
portx uninstall

# Reinstall
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

### Option 2: Manual Migration

```bash
# Backup runtime data
cp -r ~/.portx/tunnels.toml /tmp/portx-backup.toml

# Remove old installation
rm -rf ~/.portx/src
rm ~/.local/bin/portx

# Install new version
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash

# Restore state (if needed)
cp /tmp/portx-backup.toml ~/.portx/tunnels.toml
```

## Files Modified

- `installer/portx_install.py` — Rewrote installation logic
- `cli/commands.py` — Updated uninstall, added cleanup command
- `cli/portx.py` — Added cleanup command, updated help
- `cli/state.py` — Added auto-initialization of tunnels.toml
- `Formula/portx-cli.rb` — New Homebrew formula (unique name)
- `Formula/portx.rb` — Deleted (conflicted with cask)
- `scripts/install-macos.sh` — Unified installer for macOS/Linux
- `scripts/install-linux.sh` — Now symlink to install-macos.sh
- `README.md` — Updated installation instructions, added troubleshooting

## Testing

After installation, verify:

```bash
# Check installation
which portx
portx --help

# Check FRP binary
ls -la ~/.portx/bin/frpc

# Check runtime directories
ls -la ~/.portx/

# Test tunnel creation
portx http 8080
portx list
portx stop <tunnel-name>

# Test cleanup
portx cleanup
```

## Breaking Changes

None — existing tunnels will continue to work, but:

- Old `~/.portx/src/` directory is no longer used or created
- Executable location changed from symlink to standalone script
- Homebrew formula renamed from `portx` to `portx-cli`

Users should reinstall to get the new architecture.
