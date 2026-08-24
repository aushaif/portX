# Setting Up Homebrew Tap for PortX

## Overview

To make installation simple with `brew install portx`, we use a custom tap. Users must add your tap first since there's an unrelated `portx` cask in Homebrew's default repository.

## Repository Structure

You need two GitHub repositories:

1. **Main repo**: `aushaif/portX` (this project)
2. **Tap repo**: `aushaif/homebrew-portx` (Homebrew tap)

## Step 1: Create Tap Repository

```bash
# Create a new repository on GitHub: aushaif/homebrew-portx
# Clone it locally
git clone https://github.com/aushaif/homebrew-portx.git
cd homebrew-portx

# Create Formula directory
mkdir Formula
```

## Step 2: Add Formula

Copy the formula from this repo:

```bash
cp /path/to/portX/Formula/portx.rb homebrew-portx/Formula/
```

Or create `Formula/portx.rb` with the content from `Formula/portx.rb` in this repo.

## Step 3: Commit and Push

```bash
git add Formula/portx.rb
git commit -m "Add portx formula"
git push origin main
```

## Step 4: Test Installation

```bash
# Add the tap
brew tap aushaif/portx

# Install the formula
brew install portx

# Test
portx --help
portx http 8080
```

## Step 5: Update README

Make sure the main PortX README contains:

```markdown
## Installation

### macOS (Homebrew)

```bash
brew tap aushaif/portx
brew install portx
```

**Note:** You must use the tap `aushaif/portx` because there's an unrelated PortX.app 
in Homebrew's default casks. Once you've added the tap, `brew install portx` will 
install this CLI tool.
```

## Updating the Formula

When you release a new version:

1. Update `version` in `Formula/portx-cli.rb`
2. Update `url` if needed (or keep using `main` branch)
3. Remove or update `sha256` (Homebrew can auto-calculate it)
4. Commit and push to `homebrew-portx`

```bash
cd homebrew-portx
vim Formula/portx-cli.rb
# Update version number
git commit -am "Bump portx-cli to v2.1.0"
git push
```

Users can then upgrade:

```bash
brew update
brew upgrade portx-cli
```

## Formula Naming Convention

Homebrew tap formula naming:

- Tap URL: `https://github.com/aushaif/homebrew-portx`
- Formula file: `Formula/portx.rb`
- Class name: `Portx`
- Tap name: `aushaif/portx`
- Install command: `brew install aushaif/portx/portx` or just `brew install portx` after tapping

**Why the tap is needed:**
There's an unrelated PortX.app cask in Homebrew's main repository. By using your own tap, `brew install portx` will prioritize your formula once users have added your tap.

## Testing Locally

Before pushing to GitHub:

```bash
# Install from local formula file
brew install --build-from-source Formula/portx.rb

# Or test the tap locally
brew install --build-from-source aushaif/portx/portx
```

## Troubleshooting

### Formula not found

```bash
brew tap --repair
brew update
brew tap aushaif/portx --force
```

### Conflicts with existing portx

If users accidentally install the wrong `portx`:

```bash
brew uninstall portx
brew install portx-cli
```

### SHA256 checksum errors

Remove the `sha256` line from the formula:

```ruby
class PortxCli < Formula
  desc "..."
  homepage "..."
  url "..."
  version "2.0.0"
  # sha256 "" # Remove or comment out
```

Homebrew will auto-calculate it on first install.

## GitHub Releases (Optional)

For more stable releases, you can use GitHub releases instead of the main branch:

1. Create a release on GitHub: `https://github.com/aushaif/portX/releases`
2. Tag it: `v2.0.0`
3. Update formula URL:

```ruby
url "https://github.com/aushaif/portX/archive/refs/tags/v2.0.0.tar.gz"
version "2.0.0"
```

This is more reliable than using the `main` branch URL.

## Current Setup

**Main Repository:**
- `https://github.com/aushaif/portX`
- Contains: CLI source, installer, server, formulas

**Tap Repository (to create):**
- `https://github.com/aushaif/homebrew-portx`
- Contains: `Formula/portx.rb`

**Installation:**
```bash
brew tap aushaif/portx
brew install portx
```

**Executable:**
- Command: `portx`
- Location: `/opt/homebrew/bin/portx` (Apple Silicon) or `/usr/local/bin/portx` (Intel)
