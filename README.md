# PortX

> Simple tunnels — no configuration required.

PortX is a user-friendly wrapper around [FRP](https://github.com/fatedier/frp).
FRP binaries are downloaded directly from the official GitHub Releases — PortX never hosts them.

---

## Installation

### Quick Install (macOS & Linux)

**macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

**Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-linux.sh | bash
```

Both scripts are identical and work on macOS and Linux. They install:
- PortX CLI to `~/.local/bin/portx`
- FRP client binary to `~/.portx/bin/frpc`
- Runtime directories in `~/.portx/` (tunnels/, logs/, tunnels.toml)

**Requirements:** Python 3.8+

### Homebrew (macOS only)

```bash
brew tap aushaif/portx
brew install portx
```

**Note:** You must use the tap `aushaif/portx` because there's an unrelated PortX.app in Homebrew's default casks. Once you've added the tap, `brew install portx` will install this CLI tool.

---

## Uninstallation

To completely remove PortX and all associated background tunnels:

```bash
portx uninstall
```

This removes:
- `~/.local/bin/portx` (CLI executable)
- `~/.portx/` (runtime data, tunnels, logs)

**If installed via Homebrew:**

```bash
brew uninstall portx
rm -rf ~/.portx  # Optional: remove runtime data
```

The Homebrew uninstall preserves `~/.portx` runtime data by default in case you want to reinstall later.

---

## Usage (v2 — Tunnels)

Run from the project root after installing:

### HTTP tunnel

```bash
./portx http 8080
./portx http localhost:3000
./portx http 127.0.0.1:8080
```

Output:

```
→ Requesting HTTP tunnel from PortX server...
✓ Subdomain assigned: x7k29m

→ Connecting to PortX server...
✓ Connected

✓ Tunnel active

  Local:  127.0.0.1:8080
  Public: https://x7k29m.portx.infinitynoob.lol

  Forwarding traffic...
  Press Ctrl+C to stop.
```

### TCP tunnel

```bash
./portx tcp 25565
./portx tcp 127.0.0.1:25565
```

Output:

```
Local:  127.0.0.1:25565
Public: tcp.portx.infinitynoob.lol:30125
```

### UDP tunnel

```bash
./portx udp 7777
```

Output:

```
Local:  127.0.0.1:7777
Public: udp.portx.infinitynoob.lol:32001
```

### Help

```bash
portx --help
portx http --help
portx tcp  --help
portx udp  --help
```

### Cleanup

If you have orphaned tunnel files or old tunnel records:

```bash
portx cleanup              # Clean up orphaned config and log files
portx cleanup --force      # Also remove all stopped tunnel records
```

This is useful if:
- You deleted `~/.portx/` manually but tunnels are still showing
- Old tunnels from before a reinstall are still listed
- You see tunnel files but no corresponding records

---

## How it works

```
User runs: portx http 8080
          ↓
PortX CLI → POST /api/v1/tunnel → PortX API server
                                        ↓
                               Allocate subdomain "x7k29m"
                               Return tunnel info + frps details
          ↓
PortX CLI generates temporary frpc TOML config in ~/.portx/tunnels
          ↓
PortX CLI starts frpc (~/.portx/bin/frpc)
          ↓
frpc connects to frps on portx.infinitynoob.lol:7000
          ↓
Tunnel is live: https://x7k29m.portx.infinitynoob.lol → 127.0.0.1:8080
          ↓
portx stop → frpc stops → temp TOML deleted → server notified
```

---

## Supported platforms (installer)

| OS    | Architecture          | FRP asset suffix |
|-------|-----------------------|-----------------|
| macOS | ARM64 (Apple Silicon) | `darwin_arm64`  |
| macOS | AMD64 (Intel)         | `darwin_amd64`  |
| Linux | ARM64                 | `linux_arm64`   |
| Linux | AMD64                 | `linux_amd64`   |

---

## Project structure

```
portx/
├── portx                        ← Development entry point: ./portx http 8080
├── installer/
│   └── portx_install.py         # Installer: downloads CLI + FRP, installs to ~/.local/bin
├── cli/
│   ├── portx.py                 # CLI entry point
│   ├── commands.py              # CLI commands (start, stop, list, etc.)
│   ├── config.py                # Centralized server config
│   ├── api_client.py            # PortX API client
│   ├── state.py                 # State management (tunnels.toml)
│   ├── frp_config.py            # FRP TOML generator
│   ├── frp_runner.py            # FRP process manager
│   ├── worker.py                # Background daemon process
│   └── address.py               # Address parsing utilities
├── server/
│   ├── portx_server.py          # PortX API server (runs on VPS)
│   ├── frps.toml                # frps config for VPS
│   └── setup.sh                 # One-command VPS setup
├── Formula/
│   └── portx-cli.rb             # Homebrew formula
└── scripts/
    └── install-macos.sh         # curl-pipe installer script
```

**Installation Layout:**
- `~/.local/bin/portx` — CLI executable (works globally)
- `~/.portx/bin/frpc` — FRP client binary
- `~/.portx/tunnels.toml` — Persistent tunnel state
- `~/.portx/tunnels/` — Per-tunnel FRP configs
- `~/.portx/logs/` — Tunnel logs

---

## VPS deployment

```bash
# On your VPS (as root):
git clone https://github.com/aushaif/portX /opt/portx-src
sudo bash /opt/portx-src/server/setup.sh
```

The setup script:
1. Installs `frps` from official GitHub Releases
2. Deploys `portx_server.py` and `frps.toml`
3. Creates systemd services for both
4. Opens required firewall ports

Verify:

```bash
systemctl status frps portx-api
curl http://localhost:8765/health
```

---

## Server configuration

All server addresses are configurable via environment variables — never hardcoded:

| Variable            | Default                        | Description              |
|---------------------|--------------------------------|--------------------------|
| `PORTX_API_URL`     | `http://portx.infinitynoob.lol:8765` | PortX API server URL |
| `PORTX_FRPS_HOST`   | `portx.infinitynoob.lol`       | frps hostname            |
| `PORTX_FRPS_PORT`   | `7000`                         | frps port                |
| `PORTX_HTTP_DOMAIN` | `portx.infinitynoob.lol`       | HTTP wildcard domain     |
| `PORTX_TCP_DOMAIN`  | `tcp.portx.infinitynoob.lol`   | TCP tunnel hostname      |
| `PORTX_UDP_DOMAIN`  | `udp.portx.infinitynoob.lol`   | UDP tunnel hostname      |
| `PORTX_FRP_BINARY`  | `~/.portx/bin/frpc`        | Path to frpc binary      |

---

## DNS records required

| Record              | Type  | Target         | Notes                     |
|---------------------|-------|----------------|---------------------------|
| `*.portx.infinitynoob.lol` | A | VPS IP | Wildcard for HTTP tunnels |
| `tcp.portx.infinitynoob.lol` | A | VPS IP | DNS-only, no proxy     |
| `udp.portx.infinitynoob.lol` | A | VPS IP | DNS-only, no proxy     |
| `portx.infinitynoob.lol`   | A | VPS IP | API + frps               |

---

## Scope

### v2 — implemented

- `portx list` — View all background tunnels
- `portx stop <name>` — Stop a specific tunnel
- `portx remove <name>` — Delete a stopped tunnel
- `portx remove --all` — Wipe all tunnels completely
- `portx restart <name>` — Restart a tunnel
- `portx cleanup` — Clean up orphaned files
- `portx uninstall` — Complete system uninstall
- Automatic daemonization (no terminal window required)
- macOS Homebrew support
- PATH integration (run `portx` from anywhere)

### Not yet implemented

- User accounts / authentication
- Dashboard
- Custom domains

---

## Troubleshooting

### Old/orphaned tunnels showing up

If you see an old tunnel (like `https://boka.infinitynoob.lol/`) running that's not in your `portx list`, this means:

1. The tunnel was created before but the local state was lost (e.g., you deleted `~/.portx/` manually)
2. The server still has it allocated

**Solution:**

The tunnel will remain active on the server until the FRP client disconnects or the server is restarted. Since you lost the local state, you have two options:

1. **Wait it out**: The server will eventually clean up inactive tunnels (when FRP connection drops)
2. **Contact server admin**: Ask them to restart the FRP server (`frps`) which will clear all allocations
3. **Use cleanup command**: Run `portx cleanup --force` to clean up any local state mismatches

**Prevention:**

Always use `portx stop <name>` or `portx remove <name>` to properly shut down tunnels. This notifies the server to release the allocation.

### Missing FRP binary

If you see "FRP binary not found" errors:

```bash
# Check if frpc exists
ls -la ~/.portx/bin/frpc

# Reinstall if missing
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

### PATH issues

If `portx` command is not found:

```bash
# Check if installed
ls -la ~/.local/bin/portx

# Add to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```
