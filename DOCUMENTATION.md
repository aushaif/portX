# PortX — Official Product & Technical Documentation

> **Website Content & AI Generation Reference**  
> Everything required to generate the public website, documentation portal, landing page copy, interactive CLI demos, and API reference for PortX.

---

## 1. Brand & Value Proposition

### Product Identity
- **Name:** PortX
- **Tagline:** Fast, rock-solid tunnels from localhost to the internet.
- **Short Subtitle:** Expose your local web apps, game servers, databases, and services to the public internet with a single command. Zero config, background daemons, and unbreakable uptime.
- **Key Promise:** **Tunnels stay alive.** While traditional tunneling tools drop after hours or days due to silent NAT expirations and idle timeouts, PortX uses active TCP-level keepalives and 90-second heartbeat failure detection to run indefinitely without manual reloads.

### Core Value Pillars (Website Feature Cards)
1. **Unbreakable Reliability:**
   Active TCP-level keepalives every 30 seconds prevent home routers and ISP firewalls from killing idle connections. If a network blip occurs, PortX detects it within 90 seconds and reconnects automatically with exponential backoff.
2. **Background Daemons by Default:**
   No need to keep terminal windows open or run screen/tmux. PortX detaches tunnels into lightweight system daemons managed cleanly via the CLI.
3. **Multi-Protocol Support (HTTP, TCP, UDP):**
   Expose anything: web applications (HTTP/HTTPS with automatic SSL), game servers like Minecraft Java/Bedrock (TCP/UDP), SSH servers, databases (Postgres/MySQL), and VoIP.
4. **Boot-Time Auto-Recovery:**
   Enable the native system watchdog (`portx watchdog install`) to automatically restore all your active tunnels upon system boot or power failure — before user login.
5. **Zero-Downtime Hot Reloads:**
   Update tunnel parameters or switch ports interactively (`portx edit` and `portx reload`) without losing your reserved public URL or dropping healthy connections.
6. **Zero External Python Dependencies:**
   Built purely on Python 3.12+ standard library with official FRP (Fast Reverse Proxy) binaries downloaded directly from GitHub Releases.

---

## 2. Quickstart & Installation

### Option A: Universal Installer (Recommended)
One command for **macOS** and **Linux** (automatically configures Python 3.12+ and installs FRP):

```bash
curl -fsSL https://raw.githubusercontent.com/aushaif/portX/main/scripts/install.sh | bash
```

### Option B: Homebrew (macOS & Linux)
One-command installation via custom tap:

```bash
brew install aushaif/portx/portx
```

### First-Time Authentication Setup
On first execution, PortX prompts for your auth token, saving it to `~/.portx/config.toml`:

```bash
portx api <your-auth-token>
```

---

## 3. How It Works (Visual Architecture)

```
┌────────────────────────────────────────────────────────────┐
│                    Your Local Machine                      │
│                                                            │
│   Web App (8080)   /   Minecraft (25565)   /   SSH (22)    │
│                           ▲                                │
│                           │ local forward                  │
│                     FRP Client (frpc)                      │
│                (Managed by PortX Daemon)                   │
└───────────────────────────┬────────────────────────────────┘
                            │ Encrypted FRP Tunnel (Port 7000)
                            │ + TCP Keepalives (Every 30s)
                            │ + Heartbeat Probes (Every 30s)
                            ▼
┌────────────────────────────────────────────────────────────┐
│                 PortX Cloud Gateway (VPS)                  │
│                                                            │
│   HTTP/HTTPS: https://<subdomain>.infinitynoob.lol         │
│   TCP:        tcp.portx.infinitynoob.lol:<port>            │
│   UDP:        udp.portx.infinitynoob.lol:<port>            │
└────────────────────────────────────────────────────────────┘
```

### What happens when you run `portx http 8080`:
1. PortX talks to the PortX API, reserves a secure subdomain, and fetches proxy credentials.
2. Generates an optimized FRP client configuration equipped with 30s keepalives and 90s dead-connection timeouts.
3. Spawns an isolated, locked background daemon that launches the high-performance FRP client.
4. Returns your live HTTPS public address in seconds.

---

## 4. Connection Reliability Engine: Why PortX Never Drops

Most developers experience tunnels dropping after 1 to 5 days because routers, firewalls, and NAT gateways silently discard idle TCP sessions from their routing tables without sending a TCP RST packet (creating "zombie" tunnels). PortX eliminates this with a 6-layer reliability engine:

| Layer | Mechanism | How It Works |
|:------|:----------|:-------------|
| **1. TCP Mux Keepalive** | `tcpMuxKeepaliveInterval = 30s` | Sends keepalive frames at the transport layer every 30 seconds. Keeps router NAT states active indefinitely. |
| **2. Heartbeat Probes** | `heartbeatInterval = 30s` | Actively pings the remote server every 30 seconds to verify bidirectional data transfer. |
| **3. Dead-Connection Detection** | `heartbeatTimeout = 90s` | If no heartbeat response is received within 90 seconds, the client self-terminates immediately. |
| **4. Live Log Monitoring** | Real-time stream inspection | The background worker daemon scans frpc output for error signatures (e.g. `heartbeat timeout`, `connection closed`, `i/o timeout`) and immediately triggers reconnect. |
| **5. Exponential Auto-Reconnect** | Backoff loop (2s → 120s max) | Reconnects automatically when internet drops or server reboots. Uses the `reregister` API to reclaim the exact same URL/port. |
| **6. Server Stale Tunnel Reaper** | 5-min cleanup cycle | The server frees abandoned tunnels after 10 minutes of inactivity, ensuring reconnecting clients never hit port collisions. |

---

## 5. CLI Command Reference

### `portx http` / `portx https`
Expose a local web server via public HTTPS.

```bash
# Basic usage
portx http 8080

# Specify host and port with custom name
portx http 127.0.0.1:3000 my-portfolio

# Request a custom subdomain
portx http 8080 --s preview
# Output: https://preview.infinitynoob.lol
```

### `portx tcp`
Expose any TCP service (Minecraft, SSH, PostgreSQL, Redis, custom TCP sockets).

```bash
# Expose local Minecraft Java server (assigns random public port)
portx tcp 25565

# Expose with a specific custom public port (e.g. 25565)
portx tcp 25565 minecraft --p 25565
# Output: tcp.portx.infinitynoob.lol:25565

# Forward local SSH server
portx tcp 22 my-mac-ssh --p 2222
```

### `portx udp`
Expose UDP-based protocols (Minecraft Bedrock, gaming servers, DNS, VoIP).

```bash
# Expose Minecraft Bedrock on default port 19132
portx udp 19132 bedrock --p 19132
# Output: udp.portx.infinitynoob.lol:19132
```

### `portx list`
View all tunnels, their protocols, local targets, public endpoints, and real-time status.

```bash
portx list
```

**Output:**
```text
PORTX TUNNELS

NAME            TYPE   LOCAL             PUBLIC                                STATUS
──────────────────────────────────────────────────────────────────────────────────────────
my-portfolio    HTTP   127.0.0.1:3000    https://preview.infinitynoob.lol      RUNNING
minecraft       TCP    127.0.0.1:25565   tcp.portx.infinitynoob.lol:25565      RUNNING
bedrock         UDP    127.0.0.1:19132   udp.portx.infinitynoob.lol:19132      RUNNING
```

### `portx info <name>`
Detailed diagnostic view for a specific tunnel: PID, log path, config path, uptime, and last errors.

```bash
portx info my-portfolio
```

### `portx stop <name>` / `portx stop --all`
Gracefully halt tunnels without releasing public URLs or ports. Allows you to resume later with the identical address.

```bash
portx stop my-portfolio
portx stop --all
```

### `portx start <name>` / `portx start --all`
Resume previously stopped tunnels.

```bash
portx start my-portfolio
portx start --all
```

### `portx restart <name>`
Restart a running tunnel's worker and frpc processes cleanly.

```bash
portx restart my-portfolio
```

### `portx reload [name]`
Hot-reload tunnel configuration on the fly with zero backoff (~1-2s reconnect).

```bash
portx reload my-portfolio
```

### `portx edit <name>`
Interactive in-terminal configuration editor. Safely modifies ports or parameters with validation before applying changes.

```bash
portx edit minecraft
```

### `portx remove <name>` / `portx remove --all`
Permanently delete a tunnel, release its remote port/subdomain back to the pool, and purge local logs.

```bash
portx remove my-portfolio
portx remove --all
```

### `portx status`
Overall system health check showing API connectivity, active tunnel counts, and watchdog daemon status.

```bash
portx status
```

### `portx watchdog install | uninstall | status`
Set up the operating system service (`LaunchDaemon` on macOS, `systemd` on Linux) to restore all active tunnels when your computer reboots.

```bash
sudo portx watchdog install
sudo portx watchdog status
```

### `portx api <token>` / `portx api ls`
Configure or inspect your API authentication credentials.

```bash
portx api your-token-here
portx api ls
```

### `portx cleanup [--force]`
Remove leftover temporary logs and orphaned configs.

```bash
portx cleanup
```

### `portx uninstall`
Completely remove PortX, background daemons, and binaries from your machine.

```bash
portx uninstall
```

---

## 6. Popular Real-World Use Cases

### 1. Webhooks & API Integration Testing (Stripe, GitHub, Shopify)
Expose your local development server to test third-party webhooks without deploying to staging:
```bash
portx http 3000 --s stripe-hooks
```
Configure `https://stripe-hooks.infinitynoob.lol/api/webhooks` in your provider's dashboard.

### 2. Minecraft Java & Bedrock Dedicated Servers
Host multiplayer servers for your friends directly from your computer with static ports:
```bash
# Java Edition (TCP)
portx tcp 25565 --p 25565 minecraft-java

# Bedrock Edition (UDP)
portx udp 19132 --p 19132 minecraft-bedrock
```

### 3. Remote Access & SSH Forwarding
Access your home machine or Raspberry Pi from anywhere in the world:
```bash
portx tcp 22 home-pi --p 22022
# Connect from anywhere:
# ssh -p 22022 user@tcp.portx.infinitynoob.lol
```

### 4. Database Sharing & Client Demos
Securely let team members access a local database or preview in-progress work:
```bash
portx tcp 5432 pg-dev
portx http 8080 client-demo
```

---

## 7. Developer REST API Reference

Base Endpoint: `http://portx.infinitynoob.lol:8765`  
Header: `Authorization: Bearer <token>`

### Endpoints Overview

| Method | Route | Description |
|:-------|:------|:------------|
| `POST` | `/api/v1/tunnel` | Request a new tunnel allocation (subdomain / remote port) |
| `POST` | `/api/v1/tunnel/<id>/reregister` | Reclaim an existing allocation during reconnection |
| `PUT` | `/api/v1/tunnel/<id>/heartbeat` | Send liveness heartbeat (sent every 60s by worker) |
| `GET` | `/api/v1/tunnel/<id>` | Inspect tunnel metadata and allocation details |
| `DELETE` | `/api/v1/tunnel/<id>` | Release allocation back to public pool |
| `GET` | `/health` | Server health check (`{"status": "ok"}`) |

### Allocation Request Example (`POST /api/v1/tunnel`)
```json
{
  "type": "http",
  "local_host": "127.0.0.1",
  "local_port": 8080,
  "subdomain": "my-preview"
}
```

### Allocation Response Example (200 OK)
```json
{
  "tunnel_id": "9a7b1c3d-11e2-4b5a-90ef-8f12345678ab",
  "type": "http",
  "subdomain": "my-preview",
  "public_url": "https://my-preview.infinitynoob.lol",
  "proxy_name": "portx-http-my-preview",
  "frps_host": "portx.infinitynoob.lol",
  "frps_port": 7000
}
```

---

## 8. Self-Hosting & VPS Deployment

Developers who prefer running their own private tunneling relay can deploy the PortX server stack on Ubuntu or Debian in under 2 minutes:

```bash
git clone https://github.com/aushaif/portX /opt/portx-src
sudo bash /opt/portx-src/server/setup.sh
```

**What the setup script provisions:**
- Installs Python 3, `ufw` firewall rules, and dependencies.
- Downloads and provisions the matching `frps` binary.
- Configures systemd units for `frps.service` and `portx-api.service`.
- Enables persistent state tracking in `/opt/portx/state.json` with atomic backup guards.

---

## 9. Frequently Asked Questions (FAQ)

#### Q: How does PortX keep tunnels alive for days without dropping?
Traditional tools rely on idle TCP connections. When no traffic flows, domestic routers drop the connection from their NAT translation tables, causing silent connection failure. PortX sends bidirectional TCP-level keepalives every 30 seconds and probes application heartbeats. If a packet is lost, it detects failure within 90 seconds and automatically reconnects with zero manual intervention.

#### Q: Does my computer need to stay on?
Yes. The service you are exposing runs locally on your machine. If your machine sleeps or shuts down, the tunnel pauses. However, with `sudo portx watchdog install`, PortX immediately brings all your tunnels back online as soon as your machine wakes up or boots.

#### Q: Can I run multiple tunnels simultaneously?
Yes. You can run dozens of HTTP, TCP, and UDP tunnels concurrently. Each tunnel runs in its own isolated process with dedicated kernel-level file locks.

#### Q: Will someone else take my subdomain if my internet blips?
No. Your subdomain and remote ports are securely registered to your tunnel ID. When your connection recovers, PortX automatically invokes the `reregister` API to reclaim the exact same endpoints.

#### Q: Is PortX free and open-source?
Yes. PortX is 100% open source under the MIT License and uses official Fast Reverse Proxy binaries directly from GitHub Releases.

---

## 10. Website UI / AI Generation Blueprint

When generating the PortX website, use this architectural layout:

1. **Header / Navbar:** Logo, Features, Commands, Reliability, Use Cases, GitHub Link, "Get Started" CTA.
2. **Hero Section:**
   - Bold headline: *"Instant, Unbreakable Tunnels to Localhost."*
   - Subtitle: *"Expose HTTP, TCP, and UDP ports in seconds. Tunnels run in the background, survive network drops, and stay alive indefinitely."*
   - Interactive terminal / copyable curl command.
   - Live badge: *"Python 3.12+ • Pure Stdlib • 90s Auto-Recovery"*.
3. **Interactive Terminal Component:**
   - Tabs for `HTTP Web App`, `Minecraft Server`, `SSH Remote Access`.
   - Realistic animated output showing URL generation.
4. **Reliability Comparison Table:**
   - Compare PortX vs. traditional alternatives (Keepalives, Background daemon, Boot auto-recovery, UDP support, Hot reload).
5. **Interactive Command Playground:**
   - Interactive list of CLI commands (`http`, `tcp`, `udp`, `list`, `edit`, `reload`, `watchdog`).
6. **Use Cases Grid:**
   - 4-card grid (Webhooks, Gaming / Minecraft, SSH, Databases).
7. **Developer Docs & API Section:**
   - Clean markdown-rendered documentation with quick search.
8. **Footer:** GitHub repository link, license, and community links.
