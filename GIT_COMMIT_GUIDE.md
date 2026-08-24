# Git Commit Guide

## Quick Commit Commands

```bash
cd /Users/infinitynoob/Desktop/portx

# Check status
git status

# Add all changes
git add -A

# Commit with detailed message
git commit -m "Refactor: Standalone CLI installation and Homebrew fix

Major Changes:
- Install CLI to ~/.local/bin/portx as standalone executable
- Store only runtime data in ~/.portx/ (frpc, tunnels, logs, state)
- No longer clone entire repo to ~/.portx/src
- Create portx-cli Homebrew formula to avoid conflict with existing portx cask
- Add cleanup command for orphaned tunnel files
- Unify install scripts for macOS/Linux (install-linux.sh now symlink)
- Update uninstall to match new architecture
- Add troubleshooting documentation for old tunnel issues
- Auto-initialize tunnels.toml on first run

Files Modified:
- installer/portx_install.py - Complete rewrite
- cli/commands.py - Added cleanup, updated uninstall
- cli/portx.py - Added cleanup command
- cli/state.py - Auto-create tunnels.toml
- scripts/install-macos.sh - Cross-platform support
- README.md - Updated installation & troubleshooting

Files Created:
- Formula/portx-cli.rb - New Homebrew formula
- INSTALL_CHANGES.md - Detailed changelog
- HOMEBREW_TAP_SETUP.md - Tap setup guide
- IMPLEMENTATION_SUMMARY.md - Complete overview

Files Deleted:
- Formula/portx.rb - Conflicted with existing cask

Breaking Changes:
- None (but users should reinstall for new architecture)
- Old ~/.portx/src/ directory no longer used

Fixes:
- #issue Old tunnel persisting after state loss
- #issue brew install portx installs wrong app
- #issue Deleting source repo breaks installed CLI"

# Push to GitHub
git push origin main
```

## Alternative: Shorter Commit

```bash
git add -A
git commit -m "Refactor: New CLI installation architecture

- Install to ~/.local/bin/portx instead of ~/.portx/src symlink
- Store only runtime data in ~/.portx/ (frpc, tunnels, logs)
- Create portx-cli formula to avoid Homebrew naming conflict
- Add cleanup command and improve uninstall
- Unify macOS/Linux installers"

git push origin main
```

## After Pushing

1. **Create Homebrew Tap Repository**:
   ```bash
   # On GitHub: Create aushaif/homebrew-portx
   git clone https://github.com/aushaif/homebrew-portx.git
   cd homebrew-portx
   mkdir Formula
   cp /path/to/portX/Formula/portx.rb Formula/
   git add Formula/portx.rb
   git commit -m "Add portx formula v2.0.0"
   git push origin main
   ```

2. **Test Installation**:
   ```bash
   # Test curl install
   curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
   
   # Test Homebrew (after tap setup)
   brew tap aushaif/portx
   brew install portx
   ```

3. **Verify**:
   ```bash
   which portx
   portx --help
   portx http 8080
   portx list
   portx cleanup
   portx uninstall
   ```

## Commit Checklist

- [ ] All files added with `git add -A`
- [ ] Commit message describes major changes
- [ ] Pushed to origin/main
- [ ] Homebrew tap repository created
- [ ] Installation tested from GitHub (curl method)
- [ ] Homebrew installation tested
- [ ] Documentation reviewed
