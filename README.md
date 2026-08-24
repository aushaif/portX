# PortX

> Simple tunnels — no configuration required.

PortX is a user-friendly wrapper around [FRP](https://github.com/fatedier/frp).
FRP binaries are downloaded directly from the official GitHub Releases — PortX never hosts them.

---

## Installation

### macOS (Homebrew - Recommended)

```bash
brew tap aushaif/portX
brew install portx
```

### macOS

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

### Linux

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-linux.sh | bash
```

*(Use `install-linux.sh` for Linux).*

Both commands require **Python 3.8+** to be installed.

---

## Uninstallation

To completely remove PortX and all associated background tunnels:

```bash
portx uninstall
```
*(If installed via Homebrew, the command will safely exit and ask you to run `brew uninstall portx`).*

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
./portx --help
./portx http --help
./portx tcp  --help
./portx udp  --help
```

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
├── portx                        ← Run tunnels: ./portx http 8080
├── installer/
│   └── portx_install.py         # v1: FRP downloader/installer
├── cli/
│   ├── portx.py                 # v2: CLI entry point
│   ├── commands.py              # CLI commands (start, stop, etc.)
│   ├── config.py                # Centralised server config
│   ├── api_client.py            # PortX API client
│   ├── state.py                 # SQLite/JSON state management
│   ├── frp_config.py            # FRP TOML generator
│   └── worker.py                # Background daemon process
├── server/
│   ├── portx_server.py          # PortX API server (runs on VPS)
│   ├── frps.toml                # frps config for VPS
│   └── setup.sh                 # One-command VPS setup
├── scripts/
│   ├── install-macos.sh         # curl-pipe installer for macOS
│   └── install-linux.sh         # curl-pipe installer for Linux
└── README.md
```

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
- `portx uninstall` — Complete system uninstall
- Automatic daemonization (no terminal window required)
- macOS Homebrew support
- PATH integration (run `portx` from anywhere)

### Not yet implemented

- User accounts / authentication
- Dashboard
- Custom domains
