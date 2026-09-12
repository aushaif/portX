# PortX

> Simple tunnels — no configuration required.

PortX is a user-friendly wrapper around [FRP](https://github.com/fatedier/frp).
FRP binaries are downloaded directly from the official GitHub Releases — PortX never hosts them.

**Tunnels stay alive.** PortX uses active TCP keepalives and heartbeat probes to detect dead connections within 90 seconds and reconnects automatically. No zombie tunnels, no manual reloads.

---

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install.sh | bash
```

This single command works for both **macOS** and **Linux**. It automatically:
- Detects your operating system
- Installs Python 3.12+ if missing (Homebrew on macOS, system package manager on Linux)
- Installs PortX CLI → `~/.local/bin/portx`
- Downloads FRP client binary → `~/.portx/bin/frpc`
- Creates runtime directories → `~/.portx/` (tunnels/, logs/, tunnels.toml)

**Requirements:** Python 3.12+ (automatically installed by the script if missing)

### Homebrew (macOS only)

```bash
brew tap aushaif/portx
brew install portx
```

> **Note:** Use the tap `aushaif/portx` — there is an unrelated PortX.app in Homebrew's default casks.

---

## First Run — Auth Token

On first use, PortX will prompt you to enter your auth token:

```
  PortX — First Time Setup
  ─────────────────────────────────────────

  No auth token found. Please enter your PortX auth token.
  You can find your token at: https://portx.infinitynoob.lol/dashboard

  Auth token: ••••••••••••••••••••••

  ✓ Auth token saved to ~/.portx/config.toml
```

Your token is saved to `~/.portx/config.toml` and reused automatically on all future commands.

You can also set or update your token at any time:

```bash
portx api <your-token>
```

---

## Commands

### Create tunnels

```bash
portx http 8080                                       # HTTP tunnel to local port 8080
portx http 192.168.0.9:8080 my-app -s test            # portx http <ip:port> <name> -s <subdomain>
portx https 127.0.0.1:3000 my-app -s test             # portx https <ip:port> <name> -s <subdomain>
portx tcp 25565                                       # TCP tunnel (auto-assigned public port)
portx tcp 192.168.0.9:25565 mc-server -p 25565       # portx tcp <ip:port> <name> -p <remote port>
portx udp 7777                                        # UDP tunnel (auto-assigned public port)
portx udp 192.168.0.9:19132 bedrock -p 19132         # portx udp <ip:port> <name> -p <remote port>
```

### Manage tunnels

```bash
portx list                                            # View all tunnels and their status
portx info <name>                                     # Show detailed tunnel configuration
portx stop <name>                                     # Stop a tunnel (URL/port reserved)
portx stop --all                                      # Stop all active tunnels
portx start <name>                                    # Start a saved stopped tunnel
portx start --all                                     # Start all saved stopped tunnels
portx restart <name>                                  # Restart a running or stopped tunnel
portx reload                                          # Gracefully reload all running tunnels (zero-downtime)
portx reload <name>                                   # Gracefully reload a specific tunnel
portx edit <name>                                     # Interactively edit a tunnel's configuration
portx remove <name>                                   # Permanently delete tunnel and release URL/port
portx remove --all                                    # Permanently delete all tunnels
portx status                                          # Show PortX system status and server connection
```

### Auth token & config

```bash
portx api <token>                    # Set or update your auth token
portx api ls                         # Show current API URL and token
```

### Maintenance

```bash
portx cleanup                        # Remove orphaned config/log files
portx cleanup --force                # Also remove stopped tunnel records
portx uninstall                      # Complete system uninstall
```

---

## Configuration

All settings are stored in `~/.portx/config.toml`:

```toml
[portx]
api_url    = "http://portx.infinitynoob.lol:8765"
auth_token = "your-token-here"
```

You never need to edit this file manually — use `portx api <token>` to update your token.

---

## Connection Reliability

PortX is designed to keep tunnels alive indefinitely without manual intervention:

| Layer | Mechanism | Effect |
|:------|:----------|:-------|
| **TCP Keepalive** | `tcpMuxKeepaliveInterval = 30s` in frpc config | Prevents NAT/firewall tables from silently dropping idle connections (the root cause of zombie tunnels after several days) |
| **Heartbeat Probes** | `heartbeatInterval = 30s`, `heartbeatTimeout = 90s` | frpc actively pings frps every 30 s. If no reply in 90 s, frpc self-terminates and the worker reconnects |
| **Live Log Monitoring** | `worker.py` scans frpc output continuously | Detects failure markers (`heartbeat timeout`, `connection is closed`, `i/o timeout`, etc.) and triggers an immediate reconnect |
| **Auto-Reconnect** | Exponential backoff: 2 s → 120 s max | Reconnects automatically after any dropout — no manual `portx reload` needed |
| **Boot Recovery** | System watchdog daemon | Automatically restores all tunnels after machine reboot or power failure |
| **Server Stale Cleanup** | Reaper runs every 5 min on VPS | Releases allocations from tunnels silent for 10+ min, preventing port conflicts on reconnect |

Tunnels **only restart when a real failure is detected** — there are no arbitrary periodic refreshes that would interrupt connections.

---

## How it works

```
portx http 8080
    │
    ├─ POST /api/v1/tunnel  →  PortX API server
    │                              │
    │                         Allocate subdomain
    │                         Return frps details
    │
    ├─ Generate frpc TOML config with keepalives in ~/.portx/tunnels/
    │       heartbeatInterval=30, heartbeatTimeout=90,
    │       tcpMuxKeepaliveInterval=30
    │
    ├─ Spawn background worker.py (detached daemon)
    │       └─ Starts frpc
    │       └─ Monitors frpc output for failure markers
    │       └─ Sends heartbeats to server every 60 s
    │       └─ Auto-reconnects on any failure
    │
    └─ Tunnel live: https://<subdomain>.infinitynoob.lol → 127.0.0.1:8080

portx stop my-app
    └─ Kill frpc → Notify server → Update state
```

---

## Project structure

```
portx/
├── portx                         ← Dev entry point (./portx http 8080)
├── cli/
│   ├── portx.py                  # CLI entry point & argument parsing
│   ├── commands.py               # Command implementations
│   ├── config.py                 # Config manager (~/.portx/config.toml)
│   ├── api_client.py             # PortX API client (auth-aware)
│   ├── state.py                  # Tunnel state (tunnels.toml)
│   ├── frp_config.py             # frpc TOML generator
│   ├── frp_runner.py             # frpc process manager
│   ├── worker.py                 # Background daemon
│   └── address.py                # Address parsing utilities
├── installer/
│   └── portx_install.py          # Installer (downloads CLI + FRP)
├── server/
│   ├── portx_server.py           # PortX API server (VPS)
│   ├── frps.toml                 # frps configuration
│   └── setup.sh                  # One-command VPS setup
├── Formula/
│   └── portx-cli.rb              # Homebrew formula
└── scripts/
    └── install.sh                 # macOS & Linux unified installer
```

**Runtime layout:**

| Path | Purpose |
|------|---------|
| `~/.local/bin/portx` | CLI executable |
| `~/.portx/config.toml` | Auth token + API URL |
| `~/.portx/tunnels.toml` | Tunnel state |
| `~/.portx/bin/frpc` | FRP client binary |
| `~/.portx/tunnels/` | Per-tunnel frpc configs |
| `~/.portx/logs/` | Tunnel logs |

---

## Supported platforms

| OS | Architecture | FRP asset |
|----|-------------|-----------|
| macOS | ARM64 (Apple Silicon) | `darwin_arm64` |
| macOS | AMD64 (Intel) | `darwin_amd64` |
| Linux | ARM64 | `linux_arm64` |
| Linux | AMD64 | `linux_amd64` |

---

## Uninstallation

```bash
portx uninstall
```

This removes **everything** PortX installed:
- `~/.portx/` — runtime data, tunnels, config, FRP binary
- `~/.local/bin/portx` — CLI executable
- `~/.local/lib/portx/` — CLI library files
- All background frpc tunnel processes are killed

**If installed via Homebrew:**

```bash
brew uninstall portx
rm -rf ~/.portx     # Optional: remove runtime data and config
```

---

## Troubleshooting

### `portx` command not found

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### FRP binary missing

```bash
ls -la ~/.portx/bin/frpc

# Reinstall to restore
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install.sh | bash
```

### Old tunnels still showing

Use `portx cleanup --force` to remove stopped tunnel records and orphaned files.
