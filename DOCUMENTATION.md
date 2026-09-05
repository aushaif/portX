# PortX — Full Technical Documentation

> Version 2.1 | Last updated: September 2026

---

## Table of Contents

1. [What is PortX?](#1-what-is-portx)
2. [Architecture Overview](#2-architecture-overview)
3. [Installation](#3-installation)
4. [First Run & Auth Setup](#4-first-run--auth-setup)
5. [CLI Commands Reference](#5-cli-commands-reference)
6. [Configuration Files & State](#6-configuration-files--state)
7. [How Tunnels & Reconnection Work](#7-how-tunnels--reconnection-work)
8. [Project File Structure](#8-project-file-structure)
9. [Module Reference (CLI)](#9-module-reference-cli)
10. [Server Reference](#10-server-reference)
11. [Server API Reference](#11-server-api-reference)
12. [VPS Deployment](#12-vps-deployment)
13. [Supported Platforms](#13-supported-platforms)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. What is PortX?

PortX is a command-line tool that exposes your **local ports to the internet** using secure, high-reliability tunnels. It is a user-friendly wrapper around [FRP (Fast Reverse Proxy)](https://github.com/fatedier/frp), a high-performance open-source reverse proxy.

**Key features:**
- One command to create persistent HTTP, TCP, or UDP tunnels
- Tunnels run as **background daemons** — no active terminal window required
- **Auto-Reconnection & Recovery:** Automatic exponential backoff reconnects if network drops, server restarts, or frpc crashes
- **Persistent Allocations:** Subdomains and TCP/UDP ports remain reserved across restarts and reboots
- **Crash & Power-Failure Recovery:** System-level watchdog automatically restores tunnels on boot without manual login
- **Graceful Zero-Downtime Reload:** Edit configurations and reload tunnels on the fly via `portx edit` and `portx reload`
- **Concurrency & Process Safety:** Kernel-level file locking (`fcntl`) guarantees zero duplicate worker processes
- Auth token-based access control
- Zero external Python dependencies (pure Python 3.12+ stdlib)

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Client Machine (macOS / Linux)                                         │
│                                                                         │
│   portx http 8080                                                       │
│        │                                                                │
│        ├─ cli/portx.py          (CLI entry & argument parsing)          │
│        ├─ cli/commands.py       (CLI commands & process management)     │
│        ├─ cli/api_client.py     (REST client with auth & reregister)    │
│        ├─ cli/state.py          (tunnels.toml + fcntl lock management)  │
│        ├─ cli/frp_config.py     (generates frpc TOML configs)           │
│        ├─ cli/worker.py         (background daemon with auto-reconnect) │
│        ├─ cli/watchdog.py       (boot-time monitor & restorer)          │
│        └─ cli/launchd.py        (LaunchDaemon / systemd installer)      │
│                   │                                                     │
│              ~/.portx/bin/frpc  (FRP client binary)                     │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │  frpc connects on port 7000
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  VPS (portx.infinitynoob.lol)                                           │
│                                                                         │
│   frps (port 7000)        ← frpc tunnel connections                     │
│   portx_server.py (8765)  ← PortX REST API (allocations & heartbeats)  │
│   /opt/portx/state.json   ← Persistent allocation state & .bak backup   │
│                                                                         │
│   HTTP  → *.infinitynoob.lol        → frps → frpc → local port          │
│   TCP   → tcp.portx.infinitynoob.lol:PORT → frps → frpc → local port    │
│   UDP   → udp.portx.infinitynoob.lol:PORT → frps → frpc → local port    │
└─────────────────────────────────────────────────────────────────────────┘
```

Two server-side components run on the VPS:

| Component         | Port | Role                                                 |
|-------------------|------|------------------------------------------------------|
| `frps`            | 7000 | FRP server — handles actual proxying of tunnel data  |
| `portx_server.py` | 8765 | PortX API — persists allocations, auth, & heartbeat  |

---

## 3. Installation

### Quick Install (macOS & Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

- **macOS:** Auto-installs Python 3.12+ via Homebrew if not present.
- **Linux:** Auto-installs Python 3.12+ via the system package manager (`apt-get`, `dnf`, `yum`, `pacman`, or `zypper`).

### Homebrew (macOS only)

```bash
brew tap aushaif/portx
brew install portx
```

> **Note:** Always use the tap `aushaif/portx` — there is an unrelated PortX.app in Homebrew's default casks.

### What the installer does

1. Detects OS and CPU architecture (Apple Silicon ARM64, Intel AMD64, Linux ARM64/AMD64).
2. Checks for Python 3.12+ and installs/upgrades automatically if needed.
3. Downloads the PortX CLI source code from GitHub.
4. Installs CLI modules to `~/.local/lib/portx/`.
5. Creates an executable binary wrapper at `~/.local/bin/portx`.
6. Downloads the official matching `frpc` binary from FRP GitHub Releases.
7. Installs `frpc` to `~/.portx/bin/frpc`.
8. Initializes runtime directories: `~/.portx/tunnels/`, `~/.portx/logs/`, `~/.portx/locks/`.
9. Adds `~/.local/bin` to `PATH` in your shell profile (`~/.zshrc`, `~/.bashrc`, etc.).
10. Guides you through first-time auth token setup.

---

## 4. First Run & Auth Setup

On first use, PortX checks `~/.portx/config.toml` for an auth token. If missing, you will be prompted:

```
  PortX — First Time Setup
  ─────────────────────────────────────────

  No auth token found. Please enter your PortX auth token.
  You can find your token at: https://portx.infinitynoob.lol/dashboard

  Auth token: ••••••••••••••••••••••

  ✓ Auth token saved to ~/.portx/config.toml
```

The token is securely saved and reused automatically. You can update it anytime:

```bash
portx api <your-token>
```

---

## 5. CLI Commands Reference

### `portx http <address> [name] [--s <sub>]` / `portx https <address> [name] [--s <sub>]`

Create an HTTP or HTTPS tunnel exposing your local web server.

| Argument          | Description |
|-------------------|-------------|
| `address`         | Local port (e.g. `8080`) or `host:port` (e.g. `127.0.0.1:3000`) |
| `name`            | Optional custom tunnel name. A human-readable name is auto-generated if omitted. |
| `--s`, `--subdomain` | Request a custom subdomain (e.g. `--s myapp` or `--subdomain myapp`) |

**Examples:**
```bash
portx http 8080
portx http localhost:3000 my-app
portx http 8080 --s demo
portx https 8080 --s demo
```

**Output:**
```
  ✓ Tunnel active

  Name:        swift-falcon
  Local:       127.0.0.1:8080
  Public:      https://x7k29m.infinitynoob.lol

  ✓ Running in background

  Tip: Run 'sudo portx watchdog install' if you haven't already,
       to enable boot-time auto-start for all tunnels.
```

---

### `portx tcp <address> [name] [--p <port>]`

Create a TCP tunnel for non-HTTP services (SSH, game servers, databases, etc.). Supports optional custom public port via `--p` or `--port`.

| Argument       | Description |
|----------------|-------------|
| `address`      | Local port (e.g. `25565`) or `host:port` (e.g. `192.168.0.9:25565`) |
| `name`         | Optional custom tunnel name. |
| `--p`, `--port` | Optional custom public port (1–65000, e.g. `--p 25565`). If omitted, an available port is automatically assigned. |

**Examples:**
```bash
portx tcp 25565                              # Random public port assigned
portx tcp 192.168.0.9:25565 --p 25565        # Custom public port 25565
portx tcp 22 --port 2222 ssh-server          # Custom public port 2222
portx tcp 5432 postgres-dev                  # PostgreSQL database
```

**Output:**
```
  Name:        calm-lion
  Local:       192.168.0.9:25565
  Public:      tcp.portx.infinitynoob.lol:25565
```

---

### `portx udp <address> [name] [--p <port>]`

Create a UDP tunnel for UDP services (game servers, VoIP, DNS, etc.). Supports optional custom public port via `--p` or `--port`.

| Argument       | Description |
|----------------|-------------|
| `address`      | Local port (e.g. `19132`) or `host:port` (e.g. `192.168.0.9:19132`) |
| `name`         | Optional custom tunnel name. |
| `--p`, `--port` | Optional custom public port (1–65000, e.g. `--p 19132`). If omitted, an available port is automatically assigned. |

**Examples:**
```bash
portx udp 7777                               # Terraria server (random port)
portx udp 192.168.0.9:19132 --p 19132 bedrock # Minecraft Bedrock with custom port 19132
```

> **Note on Protocol Independence:** TCP and UDP ports are managed independently. You can have both `portx tcp ... --p 25565` and `portx udp ... --p 25565` running concurrently without conflict.

---

### `portx list`

List all saved tunnels, their endpoints, and current running status.

```bash
portx list
```

**Output:**
```
  PORTX TUNNELS

  NAME            TYPE   LOCAL                PUBLIC                                   STATUS
  ─────────────────────────────────────────────────────────────────────────────────────────────
  swift-falcon    HTTP   127.0.0.1:8080       https://x7k29m.infinitynoob.lol          RUNNING
  calm-lion       TCP    127.0.0.1:25565      tcp.portx.infinitynoob.lol:30125          STOPPED
```

---

### `portx info <name>`

Show detailed diagnostics, process ID, config paths, and error history for a tunnel.

```bash
portx info swift-falcon
```

**Output:**
```
  Name:        swift-falcon
  ID:          3f2a1c8d-98e2-4f1b-87cf-1e827b5f10ad
  Type:        HTTP
  Local:       127.0.0.1:8080
  Public:      https://x7k29m.infinitynoob.lol
  Status:      RUNNING
  PID:         12345
  Config:      /Users/you/.portx/tunnels/swift-falcon.toml
  Log:         /Users/you/.portx/logs/swift-falcon.log
```

---

### `portx start <name>` and `portx start --all`

Start a stopped tunnel or all saved stopped tunnels.

```bash
portx start swift-falcon     # Start a specific tunnel
portx start --all            # Start all stopped tunnels
```

- Skips already-running tunnels safely with kernel-level duplicate worker prevention.
- Clears administrative stop flags so the watchdog can resume monitoring.

---

### `portx stop <name>` and `portx stop --all`

Gracefully stop a running tunnel or all active tunnels.

```bash
portx stop swift-falcon
portx stop --all
```

- Terminates the worker and `frpc` processes cleanly.
- **Preserves URL/port allocation:** Keeps the public address reserved so restarting gives you the exact same URL/port.
- Marks tunnels as `admin_stopped=1` so the background watchdog will not automatically restart them.

---

### `portx restart <name>`

Restart a running or stopped tunnel.

```bash
portx restart swift-falcon
```

- Gracefully restarts the worker and re-attaches to the existing reserved public address.

---

### `portx reload [name]`

Gracefully reload tunnel configuration without stopping healthy client sessions.

```bash
portx reload                 # Reload all active tunnels
portx reload swift-falcon    # Reload specific tunnel
```

- Sends `SIGUSR1` to the worker process.
- Performs an **instant zero-backoff reload** of `frpc` with updated configs, reconnecting within ~1-2 seconds.
- Preserves the existing proxy name, subdomain, and remote port.

---

### `portx edit <name>`

Interactively edit a tunnel's configuration.

```bash
portx edit swift-falcon
```

- Opens the tunnel's configuration in your preferred editor (`$EDITOR`, defaults to `nano`).
- For TCP and UDP tunnels, `remotePort` is visible and directly editable:
  ```toml
  name = "bedrock"
  type = "udp"
  local_ip = "192.168.0.9"
  local_port = 19132
  remotePort = 19132
  ```
- **Validation & Safety:**
  - Validates that `remotePort` is between 1 and 65000.
  - Checks for local port conflicts across your existing tunnels of the same protocol.
  - Re-allocates the port on the server before making changes.
  - If the new port is invalid or already in use, the existing running tunnel is **never destroyed or interrupted**, and your previous configuration is preserved.
  - If valid, the tunnel is automatically stopped, reconfigured, restarted with the new port, and the new public address is displayed.

---

### `portx remove <name>` and `portx remove --all`

Permanently remove a tunnel and release its URL/port allocation on the server.

```bash
portx remove swift-falcon
portx remove --all
```

- Kills the worker and `frpc` processes.
- Calls the server API to free the subdomain/port back to the public pool.
- Deletes the local TOML config and log files.

---

### `portx status`

Display overall system status, API connectivity, and watchdog state.

```bash
portx status
```

**Output:**
```
  PortX v2.1

  Server:    Connected
  API URL:   http://portx.infinitynoob.lol:8765
  Tunnels:   1 running, 0 reconnecting, 1 stopped
  Watchdog:  Running
```

---

### `portx watchdog install | uninstall | status`

Manage the boot-level background watchdog daemon.

```bash
sudo portx watchdog install    # Install system boot daemon
sudo portx watchdog uninstall  # Remove system boot daemon
portx watchdog status          # Check daemon health
```

- **macOS:** Installs a `LaunchDaemon` at `/Library/LaunchDaemons/lol.infinitynoob.portx.watchdog.plist` to run automatically at system boot before user login.
- **Linux:** Installs a systemd unit at `/etc/systemd/system/portx-watchdog.service`.

---

### `portx api <token>` and `portx api ls`

Manage authentication credentials and API URL.

```bash
portx api hhoudcaddhaa798rtb3ryfwgsjsho   # Set new auth token
portx api ls                             # Display active API URL and masked token
```

---

### `portx cleanup [--force]`

Clean up orphaned configuration and log files.

```bash
portx cleanup              # Clean up orphaned files only
portx cleanup --force      # Also remove stopped tunnel records and their files
```

---

### `portx uninstall`

Completely removes PortX, its configuration, binaries, logs, daemons, and background processes.

```bash
portx uninstall
```

---

## 6. Configuration Files & State

### 1. `~/.portx/config.toml` — Auth & API settings

```toml
[portx]
api_url    = "http://portx.infinitynoob.lol:8765"
auth_token = "your-auth-token-here"
```

### 2. `~/.portx/tunnels.toml` — Local tunnel database

```toml
[swift-falcon]
type            = "http"
local_host      = "127.0.0.1"
local_port      = 8080
public_url      = "https://x7k29m.infinitynoob.lol"
status          = "running"
pid             = 12345
tunnel_id       = "3f2a1c8d-98e2-4f1b-87cf-1e827b5f10ad"
proxy_name      = "portx-http-x7k29m"
subdomain       = "x7k29m"
remote_port     = 0
auto_start      = 1
admin_stopped   = 0
frp_config_path = "/Users/you/.portx/tunnels/swift-falcon.toml"
log_path        = "/Users/you/.portx/logs/swift-falcon.log"
creation_time   = 1724686400.0
```

- Protected by `fcntl.flock` at `~/.portx/.tunnels.lock` on all read-modify-write cycles.

### 3. `~/.portx/locks/<name>.lock` — Kernel worker locks

- Each active worker process acquires an exclusive `fcntl.flock` on this file for its entire lifetime.
- Guarantees that only one worker/frpc instance can ever run per tunnel.

### 4. `~/.portx/tunnels/<name>.toml` — FRP client configuration

```toml
serverAddr    = "portx.infinitynoob.lol"
serverPort    = 7000
auth.method   = "token"
auth.token    = "<your-auth-token>"

[log]
level = "warn"

[[proxies]]
name      = "portx-http-x7k29m"
type      = "http"
localIP   = "127.0.0.1"
localPort = 8080
subdomain = "x7k29m"
```

---

## 7. How Tunnels & Reconnection Work

### Creation Flow (`portx http 8080`)

```
1. portx.py parses arguments and checks local address.
2. api_client.py sends POST /api/v1/tunnel with auth token.
3. portx_server.py allocates subdomain and returns connection parameters.
4. frp_config.py writes ~/.portx/tunnels/<name>.toml.
5. state.py writes tunnel record to ~/.portx/tunnels.toml under fcntl lock.
6. commands.py spawns worker.py in a detached session.
7. worker.py acquires ~/.portx/locks/<name>.lock and starts frpc.
8. worker.py starts a background heartbeat thread (PUT /api/v1/tunnel/<id>/heartbeat).
9. Tunnel is live at https://<subdomain>.infinitynoob.lol.
```

### Auto-Reconnection & Conflict Recovery Flow

If network is lost, the server restarts, or `frpc` drops:

```
1. frpc exits unexpectedly.
2. worker.py detects exit and enters exponential backoff loop (2s → 4s → ... → 120s max).
3. worker.py restarts frpc with the existing config.
4. If frpc fails with proxy name/port conflict (e.g. server wiped state):
   worker.py calls POST /api/v1/tunnel/<id>/reregister to reclaim the exact allocation.
5. On reregister success, worker.py regenerates config and connects immediately.
```

### Boot & Power Failure Recovery Flow

```
1. Device boots or recovers from power failure.
2. System LaunchDaemon (macOS) or systemd (Linux) starts watchdog.py before login.
3. watchdog.py waits 8s for system network to settle.
4. watchdog.py checks all tunnels in ~/.portx/tunnels.toml.
5. For every tunnel where admin_stopped != 1 and worker lock is not held:
   watchdog.py spawns worker.py, fully restoring all tunnels.
```

---

## 8. Project File Structure

```
portx/
│
├── portx                         ← Dev entry point (./portx http 8080)
│
├── cli/                          ← Client-side application
│   ├── portx.py                  # CLI entry point, argument parsing & dispatch
│   ├── commands.py               # Command implementations & process manager
│   ├── config.py                 # Configuration manager (~/.portx/config.toml)
│   ├── api_client.py             # REST API client (allocations, reregister, heartbeat)
│   ├── state.py                  # State manager (tunnels.toml + fcntl locking)
│   ├── frp_config.py             # Generates frpc TOML configs
│   ├── frp_runner.py             # Process launcher for frpc binary
│   ├── worker.py                 # Background worker daemon (reconnect loop & signals)
│   ├── watchdog.py               # Boot-time recovery daemon
│   ├── launchd.py                # System LaunchDaemon / systemd installer
│   └── address.py                # Parses local IP/port addresses
│
├── installer/
│   └── portx_install.py          # Python installer (downloads CLI + FRP binaries)
│
├── server/                       ← VPS server-side code
│   ├── portx_server.py           # PortX REST API server with state persistence
│   ├── frps.toml                 # FRP server configuration
│   └── setup.sh                  # One-command VPS setup script
│
├── Formula/
│   └── portx.rb                  # Homebrew formula
│
├── scripts/
│   ├── install-macos.sh          # macOS / Linux unified curl installer
│   └── install-linux.sh          # Symlink to install-macos.sh
│
├── README.md                     ← Quick start guide
└── DOCUMENTATION.md              ← Comprehensive technical documentation
```

---

## 9. Module Reference (CLI)

### `portx.py`
CLI entry point. Configures `argparse` subparsers for `http`, `tcp`, `udp`, `list`, `info`, `start`, `stop`, `restart`, `reload`, `edit`, `remove`, `status`, `watchdog`, `api`, `cleanup`, and `uninstall`.

### `commands.py`
High-level command execution:
- `cmd_start(name)` / `cmd_start_all()`: Starts stopped tunnels, preventing duplicates.
- `cmd_stop(name)` / `cmd_stop_all()`: Stops tunnels, preserving URLs, sets `admin_stopped=1`.
- `cmd_edit(name)`: Interactive editing via `$EDITOR`, parses TOML changes, and calls reload.
- `cmd_reload(name)`: Sends `SIGUSR1` to workers for instant zero-backoff restart.
- `cmd_restart(name)`: Kills worker and restarts it cleanly.
- `cmd_watchdog_install()` / `cmd_watchdog_uninstall()` / `cmd_watchdog_status()`: Manages system service.

### `worker.py`
Detached daemon per active tunnel:
- Acquires exclusive `fcntl` lock on `~/.portx/locks/<name>.lock`.
- Exponential backoff reconnection loop (`2s` to `120s`).
- Handles `SIGTERM`/`SIGINT` for clean termination.
- Handles `SIGUSR1` for graceful reload (kills `frpc` and restarts immediately with zero backoff).
- Conflict resolution via reregister API.
- Heartbeat loop thread (`PUT /api/v1/tunnel/<id>/heartbeat` every 60s).

### `watchdog.py`
System daemon running at boot:
- Checks tunnels every 30s.
- Auto-starts all unstopped tunnels (`admin_stopped=0`).
- Validates liveness via `is_worker_locked(name)`.

### `launchd.py`
Cross-platform system daemon installer:
- **macOS:** `/Library/LaunchDaemons/lol.infinitynoob.portx.watchdog.plist`
- **Linux:** `/etc/systemd/system/portx-watchdog.service`
- Configured to run as the invoking user (`UserName=<user>`, `HOME=<home>`).

### `state.py`
State persistence and file locking:
- `_lock()`: Multi-process mutex using `fcntl.flock` on `~/.portx/.tunnels.lock`.
- `acquire_worker_lock(name)` / `is_worker_locked(name)`: Kernel-level single worker guarantee.
- Atomic file writes (`.tmp` → replace).

---

## 10. Server Reference

Runs on the VPS alongside `frps`.

### `portx_server.py`
Lightweight REST API server built with Python standard library (`http.server`).

**Key features:**
- **State Persistence:** Persists all allocations to `/opt/portx/state.json`.
- **Automatic Backups:** Creates `/opt/portx/state.json.bak` on each save.
- **Corruption Protection:** Automatically recovers from `.bak` if primary state is corrupt; aborts startup safely if both fail to prevent URL hijacking.
- **Atomic Writes:** Saves state via temporary files to avoid partial write corruption.
- **Tunnel Reclamation:** Supports `reregister` API allowing reconnecting clients to reclaim their exact URLs/ports.

---

## 11. Server API Reference

Base URL: `http://portx.infinitynoob.lol:8765`

### `POST /api/v1/tunnel` — Request new allocation
**Headers:** `Authorization: Bearer <token>`  
**Body:** `{"type": "http"|"tcp"|"udp", "local_host": "127.0.0.1", "local_port": 8080, "subdomain": "optional", "remote_port": 25565}`  
*Note:* `remote_port` is optional and only applies to `tcp` and `udp` tunnels. Allowed range is 1–65000 (critical system ports such as 22, 80, 443, 7000, 8765 on TCP are protected).
**Response (200):**
```json
{
  "tunnel_id": "3f2a1c8d-98e2-4f1b-87cf-1e827b5f10ad",
  "type": "http",
  "subdomain": "x7k29m",
  "public_url": "https://x7k29m.infinitynoob.lol",
  "proxy_name": "portx-http-x7k29m",
  "frps_host": "portx.infinitynoob.lol",
  "frps_port": 7000
}
```

### `POST /api/v1/tunnel/<tunnel_id>/reregister` — Reclaim existing allocation
**Headers:** `Authorization: Bearer <token>`  
**Body:** `{"type": "http", "local_host": "127.0.0.1", "local_port": 8080, "subdomain": "x7k29m", "proxy_name": "portx-http-x7k29m"}`  
**Response (200):** Same as `POST /api/v1/tunnel`.  
**Response (409):** Allocation taken by another active tunnel.

### `PUT /api/v1/tunnel/<tunnel_id>/heartbeat` — Keep-alive heartbeat
**Headers:** `Authorization: Bearer <token>`  
**Response (200):** `{"status": "ok"}`

### `GET /api/v1/tunnel/<tunnel_id>` — Get tunnel info
**Headers:** `Authorization: Bearer <token>`  
**Response (200):** Tunnel information object.

### `DELETE /api/v1/tunnel/<tunnel_id>` — Release allocation
**Headers:** `Authorization: Bearer <token>`  
**Response (204):** Empty body. Subdomain / port is released back to pool.

### `GET /health` — Health check
**Response (200):** `{"status": "ok"}`

---

## 12. VPS Deployment

### One-command setup (Ubuntu 22.04 / Debian 12)

```bash
git clone https://github.com/aushaif/portX /opt/portx-src
sudo bash /opt/portx-src/server/setup.sh
```

**What the script configures:**
1. Installs Python 3, `ufw`, and system utilities.
2. Downloads and installs the matching `frps` server binary to `/usr/local/bin/frps`.
3. Copies server files and templates to `/opt/portx/`.
4. Creates and starts systemd services: `frps.service` and `portx-api.service` (`Restart=always`, `After=network-online.target`).
5. Configures firewall rules via `ufw`.

---

## 13. Supported Platforms

| OS     | Architecture          | Client Support | Server Support |
|--------|-----------------------|----------------|----------------|
| macOS  | ARM64 (Apple Silicon) | Yes            | No             |
| macOS  | AMD64 (Intel)         | Yes            | No             |
| Linux  | ARM64                 | Yes            | Yes            |
| Linux  | AMD64                 | Yes            | Yes            |

---

## 14. Troubleshooting

### Command not found after install
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### FRP binary missing or corrupted
```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

### Tunnel shows "reconnecting"
Check the per-tunnel log file:
```bash
cat ~/.portx/logs/<tunnel-name>.log
```

### Authentication Failed
Update your auth token:
```bash
portx api <your-auth-token>
```

### Server Unreachable
Verify VPS service status:
```bash
systemctl status portx-api frps
```
