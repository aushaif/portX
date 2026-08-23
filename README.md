# PortX

> Step 1 — FRP Downloader / Installer

PortX installs the latest [FRP](https://github.com/fatedier/frp) client binary (`frpc`) directly from the official GitHub Releases. **No FRP binaries are hosted or mirrored by PortX.**

---

## Installation

### macOS

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

### Linux

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-linux.sh | bash
```

Both commands require **Python 3.8+** to be installed.

---

## What it does

```
PortX installer
      ↓
Detect OS + architecture
      ↓
Fetch latest FRP release (GitHub API)
      ↓
Download FRP archive from GitHub
      ↓
Validate archive
      ↓
Extract frpc binary
      ↓
~/Downloads/portx/frp
```

---

## Supported platforms

| OS    | Architecture   | FRP asset suffix    |
|-------|---------------|---------------------|
| macOS | ARM64 (Apple Silicon) | `darwin_arm64` |
| macOS | AMD64 (Intel)         | `darwin_amd64` |
| Linux | ARM64                 | `linux_arm64`  |
| Linux | AMD64                 | `linux_amd64`  |

---

## Project structure

```
portx/
├── installer/
│   └── portx_install.py   # Core Python installer (zero external deps)
├── scripts/
│   ├── install-macos.sh   # curl-pipe shell wrapper for macOS
│   └── install-linux.sh   # curl-pipe shell wrapper for Linux
└── README.md
```

---

## Running locally (for development / testing)

```bash
python3 installer/portx_install.py
```

No dependencies beyond the Python standard library.

---

## Output

After installation:

```
~/Downloads/portx/
└── frp        ← frpc binary, renamed to 'frp'
```

---

## Scope (Step 1 only)

This release covers **only** the installer.  The following are **not yet implemented**:

- PATH configuration
- FRP configuration files
- Tunnels
- Authentication
- Domains / subdomains
- Dashboard
- Server management
- Homebrew tap / formula
