# PortX — Full Technical Documentation

> Version 2.0 | Last updated: August 2026

---

## Table of Contents

1. [What is PortX?](#1-what-is-portx)
2. [Architecture Overview](#2-architecture-overview)
3. [Installation](#3-installation)
4. [First Run & Auth Setup](#4-first-run--auth-setup)
5. [CLI Commands Reference](#5-cli-commands-reference)
6. [Configuration Files](#6-configuration-files)
7. [How Tunnels Work](#7-how-tunnels-work)
8. [Project File Structure](#8-project-file-structure)
9. [Module Reference (CLI)](#9-module-reference-cli)
10. [Server Reference](#10-server-reference)
11. [Server API Reference](#11-server-api-reference)
12. [VPS Deployment](#12-vps-deployment)
13. [Supported Platforms](#13-supported-platforms)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. What is PortX?

PortX is a command-line tool that exposes your **local ports to the internet** using secure tunnels. It is a user-friendly wrapper around [FRP (Fast Reverse Proxy)](https://github.com/fatedier/frp), a high-performance open-source tool.

**Key features:**
- One command to create an HTTP, TCP, or UDP tunnel
- Tunnels run in the **background** — no terminal window needed
- Manages multiple tunnels simultaneously
- Persistent state — tunnels survive terminal restarts
- Auth token based access
- Zero external Python dependencies (stdlib only)

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  User's Machine (macOS / Linux)                                     │
│                                                                     │
│   portx http 8080                                                   │
│        │                                                            │
│        ├─ cli/portx.py          (CLI entry + argument parsing)      │
│        ├─ cli/api_client.py     (HTTP POST to PortX API server)     │
│        ├─ cli/frp_config.py     (generates frpc TOML config)        │
│        ├─ cli/worker.py         (background daemon)                 │
│        └─ cli/frp_runner.py     (manages frpc process)              │
│                   │                                                 │
│              ~/.portx/bin/frpc  (FRP client binary)                 │
└─────────────────────────┬───────────────────────────────────────────┘
                          │  frpc connects on port 7000
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  VPS (portx.infinitynoob.lol)                                       │
│                                                                     │
│   frps (port 7000)        ← frpc connects here                      │
│   portx_server.py (8765)  ← PortX CLI sends tunnel requests here   │
│                                                                     │
│   HTTP  → *.infinitynoob.lol → frps → frpc → your local port       │
│   TCP   → tcp.portx.infinitynoob.lol:PORT → frps → frpc            │
│   UDP   → udp.portx.infinitynoob.lol:PORT → frps → frpc            │
└─────────────────────────────────────────────────────────────────────┘
```

Two server-side components run on the VPS:

| Component         | Port | Role                                    |
|-------------------|------|-----------------------------------------|
| `frps`            | 7000 | FRP server — handles actual tunnel traffic |
| `portx_server.py` | 8765 | PortX API — allocates subdomains/ports  |

---

## 3. Installation

### macOS (curl)

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

- Auto-installs Python 3.12+ via Homebrew if not present
- Installs Homebrew itself if not found

### Linux (curl)

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-linux.sh | bash
```

- Auto-installs Python 3.12+ via the available package manager
  (`apt-get`, `dnf`, `yum`, `pacman`, or `zypper`)

### Homebrew (macOS only)

```bash
brew tap aushaif/portx
brew install portx
```

> Always use the tap `aushaif/portx` — there is an unrelated PortX.app in the default cask list.

### What the installer does

1. Detects the OS and CPU architecture
2. Checks for Python 3.12+ — installs/upgrades automatically if needed
3. Downloads the PortX CLI source from GitHub
4. Installs CLI modules to `~/.local/lib/portx/`
5. Creates an executable wrapper at `~/.local/bin/portx`
6. Downloads the latest `frpc` binary from official FRP GitHub releases
7. Installs `frpc` to `~/.portx/bin/frpc`
8. Creates runtime directories: `~/.portx/tunnels/`, `~/.portx/logs/`
9. Adds `~/.local/bin` to `PATH` in your shell RC file
10. Prints instructions to configure your auth token

---

## 4. First Run & Auth Setup

On the **first command** after installation, PortX checks `~/.portx/config.toml`
for an auth token. If none is found, it prompts you:

```
  PortX — First Time Setup
  ─────────────────────────────────────────

  No auth token found. Please enter your PortX auth token.
  You can find your token at: https://portx.infinitynoob.lol/dashboard

  Auth token: ••••••••••••••••••••••

  ✓ Auth token saved to /Users/you/.portx/config.toml
```

The token is saved and **reused automatically** on all subsequent commands.

### Set or update the auth token at any time

```bash
portx api <your-token>
```

---

## 5. CLI Commands Reference

### `portx http <address> [name] [--subdomain <sub>]`

Create an HTTP tunnel.

| Argument      | Description |
|---------------|-------------|
| `address`     | Local port or `host:port` (e.g. `8080`, `localhost:3000`) |
| `name`        | Optional tunnel name. Auto-generated if omitted. |
| `--subdomain` | Request a specific subdomain (e.g. `--subdomain test`) |

**Examples:**
```bash
portx http 8080
portx http localhost:3000 my-app
portx http 8080 --subdomain demo
```

**Output:**
```
  ✓ Tunnel active

  Name:   swift-falcon
  Local:  127.0.0.1:8080
  Public: https://x7k29m.infinitynoob.lol

  ✓ Running in background
```

---

### `portx tcp <address> [name]`

Create a TCP tunnel for any TCP-based service (game servers, SSH, databases, etc.)

```bash
portx tcp 25565              # Minecraft
portx tcp 22                 # SSH
portx tcp 5432 postgres-dev  # PostgreSQL
```

**Output:**
```
  Name:   calm-lion
  Local:  127.0.0.1:25565
  Public: tcp.portx.infinitynoob.lol:30125
```

---

### `portx udp <address> [name]`

Create a UDP tunnel for UDP-based services (game servers, VoIP, etc.)

```bash
portx udp 7777
portx udp 19132 bedrock
```

**Output:**
```
  Name:   wild-hawk
  Local:  127.0.0.1:7777
  Public: udp.portx.infinitynoob.lol:32001
```

---

### `portx list`

Display all tunnels and their current status.

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

Show full details for a specific tunnel.

```bash
portx info swift-falcon
```

**Output:**
```
  Name:    swift-falcon
  ID:      3f2a1c8d-...
  Type:    HTTP
  Local:   127.0.0.1:8080
  Public:  https://x7k29m.infinitynoob.lol
  Status:  RUNNING
  PID:     12345
  Config:  /Users/you/.portx/tunnels/swift-falcon.toml
  Log:     /Users/you/.portx/logs/swift-falcon.log
```

---

### `portx stop <name> [--all]`

Stop a running tunnel. The server is notified and releases the allocation.

```bash
portx stop swift-falcon
portx stop --all           # Stop all running tunnels
```

---

### `portx remove <name> [--all]`

Stop and permanently delete a tunnel record, its config, and its log file.

```bash
portx remove swift-falcon
portx remove --all         # Remove all tunnels
```

---

### `portx restart <name>`

Restart a stopped tunnel. Note: the server issues a new allocation so the
public URL/port may change.

```bash
portx restart swift-falcon
```

---

### `portx status`

Show overall system status.

```bash
portx status
```

**Output:**
```
  PortX v2.0

  Server:    Connected
  API URL:   http://portx.infinitynoob.lol:8765
  Tunnels:   2 running
  Stopped:   1
```

---

### `portx api <token>`

Set or update the auth token stored in `~/.portx/config.toml`.

```bash
portx api hhoudcaddhaa798rtb3ryfwgsjsho
```

**Output:**
```
  ✓ Auth token updated: hhoudc***********************
  Saved to: /Users/you/.portx/config.toml
```

---

### `portx api ls`

Show the currently configured API URL and masked auth token.

```bash
portx api ls
```

**Output:**
```
  API URL:    http://portx.infinitynoob.lol:8765
  Auth token: hhoudc***********************
  Config:     /Users/you/.portx/config.toml
```

---

### `portx cleanup [--force]`

Remove orphaned tunnel config and log files with no matching tunnel record.

```bash
portx cleanup              # Remove orphaned files only
portx cleanup --force      # Also remove STOPPED tunnel records and their files
```

---

### `portx uninstall` (also accepts `portx unistall`)

Completely remove PortX from the system.

```bash
portx uninstall
```

**What it removes:**

| Path                   | Contents                                     |
|------------------------|----------------------------------------------|
| `~/.portx/`            | Auth config, tunnels, frpc binary, logs      |
| `~/.local/bin/portx`   | CLI executable wrapper                       |
| `~/.local/lib/portx/`  | All CLI Python modules                       |

Also kills all running `frpc` and `worker.py` background processes.

> If installed via Homebrew: `brew uninstall portx` then `rm -rf ~/.portx`

---

## 6. Configuration Files

### `~/.portx/config.toml` — Auth & API settings

```toml
[portx]
api_url    = "http://portx.infinitynoob.lol:8765"
auth_token = "your-token-here"
```

Managed by `portx api <token>`. Do not edit manually.

---

### `~/.portx/tunnels.toml` — Tunnel state database

```toml
[swift-falcon]
type            = "http"
local_host      = "127.0.0.1"
local_port      = 8080
public_url      = "https://x7k29m.infinitynoob.lol"
status          = "running"
pid             = 12345
tunnel_id       = "3f2a1c8d-..."
frp_config_path = "/Users/you/.portx/tunnels/swift-falcon.toml"
log_path        = "/Users/you/.portx/logs/swift-falcon.log"
subdomain       = "x7k29m"
creation_time   = 1724686400.0
```

Automatically maintained by the CLI. Do not edit manually.

---

### `~/.portx/tunnels/<name>.toml` — Per-tunnel frpc config

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

Generated automatically. Never edit manually.

---

## 7. How Tunnels Work

### Step-by-step flow for `portx http 8080`

```
1. portx.py parses arguments

2. api_client.py → POST /api/v1/tunnel
       header: Authorization: Bearer <token>
       body:   {type:"http", local_host:"127.0.0.1", local_port:8080}

3. portx_server.py allocates a random 6-char subdomain (e.g. "x7k29m")
       returns: {tunnel_id, subdomain, public_url, frps_host, frps_port, proxy_name}

4. frp_config.py generates ~/.portx/tunnels/swift-falcon.toml

5. state.py saves tunnel record to ~/.portx/tunnels.toml

6. commands.py spawns worker.py as a detached background process

7. worker.py → frp_runner.py → launches frpc with the TOML config

8. frpc connects to frps on portx.infinitynoob.lol:7000

9. Tunnel is live:
       https://x7k29m.infinitynoob.lol → frps → frpc → 127.0.0.1:8080
```

### What happens on `portx stop swift-falcon`

```
1. Read tunnel PID from tunnels.toml
2. Send SIGTERM to the worker process group (also kills frpc)
3. DELETE /api/v1/tunnel/<tunnel_id>  (server releases the subdomain)
4. Update tunnel status to "stopped"
```

---

## 8. Project File Structure

```
portx/
│
├── portx                         ← Dev entry point (./portx http 8080)
│
├── cli/                          ← All client-side code
│   ├── portx.py                  # CLI entry point — argument parsing & dispatch
│   ├── commands.py               # All command implementations
│   ├── config.py                 # Config manager (reads ~/.portx/config.toml)
│   ├── api_client.py             # HTTP client for the PortX API server
│   ├── state.py                  # Tunnel state management (tunnels.toml)
│   ├── frp_config.py             # Generates frpc TOML config files
│   ├── frp_runner.py             # Launches and monitors frpc process
│   ├── worker.py                 # Background daemon (runs frpc, updates state)
│   └── address.py                # Parses local address strings
│
├── installer/
│   └── portx_install.py          # Python installer (downloads CLI + FRP)
│
├── server/                       ← VPS-side code
│   ├── portx_server.py           # PortX REST API server
│   ├── frps.toml                 # FRP server configuration
│   └── setup.sh                  # One-command VPS setup script
│
├── Formula/
│   └── portx.rb                  # Homebrew formula
│
├── scripts/
│   ├── install-macos.sh          # macOS curl-pipe installer
│   └── install-linux.sh          # Linux curl-pipe installer
│
├── README.md                     ← User-facing quick reference
└── DOCUMENTATION.md              ← This file
```

**Runtime layout (~/.portx/ and ~/.local/):**

```
~/.portx/
├── config.toml                   # Auth token + API URL
├── tunnels.toml                  # All tunnel state records
├── bin/
│   └── frpc                      # FRP client binary
├── tunnels/
│   └── <name>.toml               # Per-tunnel frpc config
└── logs/
    └── <name>.log                # Per-tunnel log output

~/.local/
├── bin/
│   └── portx                     # CLI executable wrapper
└── lib/
    └── portx/                    # All CLI Python modules
```

---

## 9. Module Reference (CLI)

### `portx.py` — Entry point

Parses all CLI arguments and dispatches to the correct command function.

**Key function:** `main()` — called by the wrapper at `~/.local/bin/portx`

---

### `config.py` — Configuration manager

Reads/writes `~/.portx/config.toml`. Uses a hand-rolled TOML parser (no deps).

| Function                 | Description |
|--------------------------|-------------|
| `get_api_url()`          | Returns configured API URL. Falls back to default. |
| `get_auth_token()`       | Returns auth token. **Prompts interactively on first use** and persists it. |
| `set_auth_token(token)`  | Saves a new token without changing other config keys. |
| `set_api_url(url)`       | Saves a new API URL without changing other config keys. |

**Infrastructure constants (not user-configurable):**

| Constant              | Default                           |
|-----------------------|-----------------------------------|
| `FRPS_HOST`           | `portx.infinitynoob.lol`          |
| `FRPS_PORT`           | `7000`                            |
| `HTTP_TUNNEL_DOMAIN`  | `infinitynoob.lol`                |
| `TCP_TUNNEL_DOMAIN`   | `tcp.portx.infinitynoob.lol`      |
| `UDP_TUNNEL_DOMAIN`   | `udp.portx.infinitynoob.lol`      |
| `FRP_BINARY`          | `~/.portx/bin/frpc`               |
| `API_TIMEOUT`         | `15` seconds                      |
| `FRPC_CONNECT_TIMEOUT`| `15` seconds                      |

---

### `api_client.py` — PortX API client

Makes HTTP requests to the PortX API server. Reads API URL from `config.get_api_url()`
and attaches `Authorization: Bearer <token>` on every request.

| Function                                        | Description |
|-------------------------------------------------|-------------|
| `request_tunnel(type, host, port, subdomain?)`  | Ask server to allocate a tunnel. Returns response dict. |
| `release_tunnel(tunnel_id)`                     | Notify server to free the allocation. Best-effort. |

Raises `APIError` with a human-readable message on failure.

---

### `state.py` — Tunnel state management

Reads/writes `~/.portx/tunnels.toml`.

| Function                    | Description |
|-----------------------------|-------------|
| `load_tunnels()`            | Load all tunnel records |
| `save_tunnels(tunnels)`     | Overwrite the state file |
| `get_tunnel(name)`          | Get single tunnel with PID liveness check |
| `list_tunnels()`            | All tunnels with liveness checks |
| `update_tunnel(name, **kw)` | Create or update a tunnel record |
| `remove_tunnel(name)`       | Delete a tunnel record |
| `is_pid_alive(pid)`         | Check if an OS process is running |

---

### `frp_config.py` — frpc TOML generator

Generates the TOML config files that `frpc` reads. Uses `config.get_auth_token()`
so the auth token in the tunnel config is always in sync with the user's saved token.

| Function                    | Description |
|-----------------------------|-------------|
| `generate_http_config(...)` | Generate TOML for an HTTP tunnel |
| `generate_tcp_config(...)`  | Generate TOML for a TCP tunnel |
| `generate_udp_config(...)`  | Generate TOML for a UDP tunnel |

---

### `frp_runner.py` — frpc process manager

| Function                                    | Description |
|---------------------------------------------|-------------|
| `start_frpc(config_path, frp_binary, timeout)` | Launch frpc, wait for success/failure signal. Returns `Popen`. Raises `FRPError`. |
| `stop_frpc(proc)`                           | SIGTERM then SIGKILL after 5s. |

**Success markers watched in frpc log output:**
- `"start proxy success"`, `"login to server success"`

**Failure markers:**
- `"login to server failed"`, `"proxy name conflict"`, `"port already used"`,
  `"failed to login"`, `"no such host"`, `"connection refused"`,
  `"i/o timeout"`, `"authentication failed"`

---

### `worker.py` — Background daemon

Spawned as a **detached child process**. Lifecycle:

1. Load tunnel config from `tunnels.toml`
2. Redirect stdout/stderr to the tunnel's log file
3. Launch `frpc` via `frp_runner.start_frpc()`
4. Update tunnel status to `"running"` on success, `"failed"` on error
5. Poll `frpc` every second until it exits
6. Mark tunnel as `"stopped"` when frpc exits
7. Handle `SIGTERM`/`SIGINT` by cleanly terminating frpc

---

### `address.py` — Local address parser

| Input              | Output                    |
|--------------------|---------------------------|
| `"8080"`           | `("127.0.0.1", 8080)`     |
| `"localhost:3000"` | `("127.0.0.1", 3000)`     |
| `"127.0.0.1:8080"` | `("127.0.0.1", 8080)`     |
| `"0.0.0.0:8080"`   | `("0.0.0.0", 8080)`       |

Raises `AddressError` for invalid input.

---

### `commands.py` — Command implementations

| Function                   | Command               |
|----------------------------|-----------------------|
| `cmd_list()`               | `portx list`          |
| `cmd_info(name)`           | `portx info <name>`   |
| `cmd_stop(name)`           | `portx stop <name>`   |
| `cmd_stop_all()`           | `portx stop --all`    |
| `cmd_remove(name)`         | `portx remove <name>` |
| `cmd_remove_all()`         | `portx remove --all`  |
| `cmd_restart(name)`        | `portx restart <name>`|
| `cmd_status()`             | `portx status`        |
| `cmd_api_set(token)`       | `portx api <token>`   |
| `cmd_api_ls()`             | `portx api ls`        |
| `cmd_cleanup(force)`       | `portx cleanup`       |
| `cmd_uninstall()`          | `portx uninstall`     |

---

## 10. Server Reference

> These files run on the VPS, not on the user's machine.

### `portx_server.py`

A lightweight Python HTTP server (stdlib `http.server`). No external dependencies.

**`TunnelAllocator` class — thread-safe**

| Method                              | Description |
|-------------------------------------|-------------|
| `allocate_http(host, port, sub?)`   | Allocate a random or requested subdomain. |
| `allocate_tcp(host, port)`          | Allocate a random port from 30000–31999. |
| `allocate_udp(host, port)`          | Allocate a random port from 32000–33999. |
| `release(tunnel_id)`                | Free the allocation. Returns `True` if found. |

**Environment variables:**

| Variable             | Default                           | Description |
|----------------------|-----------------------------------|-------------|
| `PORTX_API_HOST`     | `0.0.0.0`                         | API bind address |
| `PORTX_API_PORT`     | `8765`                            | API listen port |
| `PORTX_FRPS_HOST`    | `portx.infinitynoob.lol`          | frps hostname returned to clients |
| `PORTX_FRPS_PORT`    | `7000`                            | frps port returned to clients |
| `PORTX_HTTP_DOMAIN`  | `infinitynoob.lol`                | HTTP subdomain base domain |
| `PORTX_TCP_DOMAIN`   | `tcp.portx.infinitynoob.lol`      | TCP tunnel hostname |
| `PORTX_UDP_DOMAIN`   | `udp.portx.infinitynoob.lol`      | UDP tunnel hostname |
| `PORTX_TCP_PORT_MIN` | `30000`                           | TCP port pool start |
| `PORTX_TCP_PORT_MAX` | `31999`                           | TCP port pool end |
| `PORTX_UDP_PORT_MIN` | `32000`                           | UDP port pool start |
| `PORTX_UDP_PORT_MAX` | `33999`                           | UDP port pool end |

---

## 11. Server API Reference

Base URL: `http://portx.infinitynoob.lol:8765`

---

### `POST /api/v1/tunnel` — Create a tunnel

**Headers:**
```
Authorization: Bearer <auth-token>
Content-Type: application/json
```

**Body:**
```json
{
  "type":       "http" | "tcp" | "udp",
  "local_host": "127.0.0.1",
  "local_port": 8080,
  "subdomain":  "myapp"
}
```

**Response 200 — HTTP:**
```json
{
  "tunnel_id":  "uuid",
  "type":       "http",
  "subdomain":  "x7k29m",
  "public_url": "https://x7k29m.infinitynoob.lol",
  "proxy_name": "portx-http-x7k29m",
  "frps_host":  "portx.infinitynoob.lol",
  "frps_port":  7000
}
```

**Response 200 — TCP/UDP:**
```json
{
  "tunnel_id":   "uuid",
  "type":        "tcp",
  "remote_port": 30125,
  "public_host": "tcp.portx.infinitynoob.lol",
  "public_url":  "tcp.portx.infinitynoob.lol:30125",
  "proxy_name":  "portx-tcp-30125",
  "frps_host":   "portx.infinitynoob.lol",
  "frps_port":   7000
}
```

| Code | Meaning                            |
|------|------------------------------------|
| 200  | Tunnel allocated successfully      |
| 400  | Invalid tunnel type or port        |
| 503  | No ports/subdomains available      |

---

### `DELETE /api/v1/tunnel/<tunnel_id>` — Release a tunnel

Frees the subdomain or port. Always returns `204`.

---

### `GET /health` — Health check

```json
{ "status": "ok" }
```

---

## 12. VPS Deployment

### One-command setup (Ubuntu 22.04 / Debian 12)

```bash
git clone https://github.com/aushaif/portX /opt/portx-src
sudo bash /opt/portx-src/server/setup.sh
```

**The setup script does:**
1. Installs Python 3 and tools via `apt-get`
2. Auto-detects latest FRP version from GitHub
3. Downloads and installs `frps` to `/usr/local/bin/frps`
4. Copies server files to `/opt/portx/`
5. Creates and enables systemd services: `frps` and `portx-api`
6. Opens required firewall ports via `ufw`

### Verify

```bash
systemctl status frps portx-api
curl http://localhost:8765/health
```

### Required DNS records

| Record                          | Type | Target | Purpose                  |
|---------------------------------|------|--------|--------------------------|
| `*.portx.infinitynoob.lol`      | A    | VPS IP | HTTP wildcard tunnels    |
| `tcp.portx.infinitynoob.lol`    | A    | VPS IP | TCP tunnel hostname      |
| `udp.portx.infinitynoob.lol`    | A    | VPS IP | UDP tunnel hostname      |
| `portx.infinitynoob.lol`        | A    | VPS IP | API server + frps        |

### Firewall ports

| Port        | Protocol | Service                      |
|-------------|----------|------------------------------|
| 7000        | TCP      | frps — frpc client connections |
| 80          | TCP      | HTTP tunnel traffic           |
| 443         | TCP      | HTTPS tunnel traffic          |
| 8765        | TCP      | PortX API server              |
| 30000–31999 | TCP      | TCP tunnel remote ports       |
| 32000–33999 | UDP      | UDP tunnel remote ports       |

---

## 13. Supported Platforms

### Client

| OS     | Architecture          | Notes                                   |
|--------|-----------------------|-----------------------------------------|
| macOS  | ARM64 (Apple Silicon) | Python auto-installed via Homebrew      |
| macOS  | AMD64 (Intel)         | Python auto-installed via Homebrew      |
| Linux  | ARM64                 | Python auto-installed via apt/dnf/etc.  |
| Linux  | AMD64                 | Python auto-installed via apt/dnf/etc.  |

### Server

| OS            | Notes          |
|---------------|----------------|
| Ubuntu 22.04+ | Fully tested   |
| Debian 12+    | Fully tested   |

---

## 14. Troubleshooting

### `portx` command not found after install

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### FRP binary missing

```bash
ls -la ~/.portx/bin/frpc

# Reinstall to restore
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install-macos.sh | bash
```

### `portx list` empty after deleting `~/.portx`

`~/.portx/tunnels.toml` holds all state. If deleted manually, `portx list`
will be empty. Background frpc processes may still be running.

```bash
portx cleanup --force    # Clean up lingering state
portx uninstall          # Or fully remove and reinstall
```

### Tunnel not connecting (`authentication failed`)

The auth token in `config.toml` doesn't match what the server expects. Update it:

```bash
portx api <correct-token>
```

### Subdomain already in use

Use a different `--subdomain` value or omit it entirely for a random one.

### `portx status` shows `Server: Unreachable`

- Check your internet connection
- Verify the API server is running: `systemctl status portx-api`
- Check configured URL: `portx api ls`
