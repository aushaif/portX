#!/usr/bin/env python3
"""
PortX API Server — v2.1
Runs on the VPS alongside frps.

Responsibilities:
  • Allocate random HTTP subdomains (6-char alphanumeric, collision-safe)
  • Allocate TCP ports from a configurable range
  • Allocate UDP ports from a configurable range
  • Return frps connection info to PortX CLI clients
  • Release allocations when a tunnel is closed
  • Persist allocations to disk so server restarts don't lose tunnel URLs
  • Allow clients to reclaim their exact allocation (reregister) after reconnect

REST API:

  POST  /api/v1/tunnel
    Body:     {"type": "http"|"tcp"|"udp", "local_host": str, "local_port": int}
    200:      see _build_response() below
    400/503:  {"error": str}

  DELETE /api/v1/tunnel/<tunnel_id>
    204:  no body

  GET /api/v1/tunnel/<tunnel_id>
    200:  tunnel info dict
    404:  {"error": "not found"}

  PUT /api/v1/tunnel/<tunnel_id>/heartbeat
    200:  {"status": "ok"}
    404:  {"error": "not found"}

  POST /api/v1/tunnel/<tunnel_id>/reregister
    Body:     {"type": str, "local_host": str, "local_port": int,
               "subdomain": str (HTTP only), "remote_port": int (TCP/UDP only),
               "proxy_name": str}
    200:  full tunnel info (same as POST /api/v1/tunnel)
    409:  {"error": "allocation taken by another tunnel"}
    400:  {"error": str}

Usage:
  python3 server/portx_server.py

Environment variables (all optional):
  PORTX_API_HOST       Bind address          (default: 0.0.0.0)
  PORTX_API_PORT       API listen port       (default: 8765)
  PORTX_FRPS_HOST      frps hostname         (default: portx.infinitynoob.lol)
  PORTX_FRPS_PORT      frps bind port        (default: 7000)
  PORTX_HTTP_DOMAIN    Wildcard HTTP domain  (default: portx.infinitynoob.lol)
  PORTX_TCP_DOMAIN     TCP tunnel hostname   (default: tcp.portx.infinitynoob.lol)
  PORTX_UDP_DOMAIN     UDP tunnel hostname   (default: udp.portx.infinitynoob.lol)
  PORTX_TCP_PORT_MIN   TCP port pool start   (default: 30000)
  PORTX_TCP_PORT_MAX   TCP port pool end     (default: 31999)
  PORTX_UDP_PORT_MIN   UDP port pool start   (default: 32000)
  PORTX_UDP_PORT_MAX   UDP port pool end     (default: 33999)
  PORTX_STATE_FILE     Path for persistent allocation state
                       (default: /opt/portx/state.json)
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import string
import sys
import shutil
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables)
# ---------------------------------------------------------------------------

API_HOST = os.environ.get("PORTX_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("PORTX_API_PORT", "8765"))

FRPS_HOST = os.environ.get("PORTX_FRPS_HOST", "portx.infinitynoob.lol")
FRPS_PORT = int(os.environ.get("PORTX_FRPS_PORT", "7000"))

HTTP_DOMAIN = os.environ.get("PORTX_HTTP_DOMAIN", "infinitynoob.lol")
TCP_DOMAIN  = os.environ.get("PORTX_TCP_DOMAIN",  "tcp.portx.infinitynoob.lol")
UDP_DOMAIN  = os.environ.get("PORTX_UDP_DOMAIN",  "udp.portx.infinitynoob.lol")

TCP_PORT_MIN = int(os.environ.get("PORTX_TCP_PORT_MIN", "30000"))
TCP_PORT_MAX = int(os.environ.get("PORTX_TCP_PORT_MAX", "31999"))
UDP_PORT_MIN = int(os.environ.get("PORTX_UDP_PORT_MIN", "32000"))
UDP_PORT_MAX = int(os.environ.get("PORTX_UDP_PORT_MAX", "33999"))

# Path for persistent allocation state — survives server restarts
STATE_FILE = Path(os.environ.get("PORTX_STATE_FILE", "/opt/portx/state.json"))

SUBDOMAIN_LEN   = 6
SUBDOMAIN_CHARS = string.ascii_lowercase + string.digits

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("portx-server")


# ---------------------------------------------------------------------------
# Tunnel allocator (thread-safe, persistent)
# ---------------------------------------------------------------------------

class TunnelAllocator:
    """
    Manages subdomain and port allocations for active tunnels.
    All public methods are thread-safe.
    Allocations are persisted to STATE_FILE and reloaded on startup,
    ensuring tunnel URLs survive server restarts.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # tunnel_id → {type, subdomain/remote_port, proxy_name, local_host, local_port, created_at, last_seen}
        self._tunnels: dict[str, dict] = {}
        self._used_subdomains: set[str] = set()
        self._used_tcp_ports:  set[int] = set()
        self._used_udp_ports:  set[int] = set()
        self._load_state()

    # ── Persistence ───────────────────────────────────────────────────────

    def _load_state(self) -> None:
        """Load persisted allocations from disk on startup."""
        bak_file = STATE_FILE.with_suffix(".json.bak")
        
        if not STATE_FILE.exists() and not bak_file.exists():
            log.info("No state files found — starting fresh")
            return
            
        data = None
        
        # Try loading primary state
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text("utf-8"))
            except Exception as exc:
                log.error("CRITICAL: Failed to parse primary state file %s: %s", STATE_FILE, exc)
                # If backup exists, we will try it next. Otherwise, fail hard.
        
        # Try loading backup state if primary failed
        if data is None and bak_file.exists():
            try:
                log.info("Attempting to recover from backup state file %s...", bak_file)
                data = json.loads(bak_file.read_text("utf-8"))
                log.info("Successfully recovered state from backup.")
            except Exception as exc:
                log.error("CRITICAL: Failed to parse backup state file %s: %s", bak_file, exc)
        
        # If both failed and we got here, it means corruption occurred.
        if data is None:
            log.critical("FATAL: State file corruption detected and no valid backups found.")
            log.critical("Aborting startup to prevent accidental release of existing tunnel URLs.")
            log.critical("Please manually fix or delete %s to start fresh.", STATE_FILE)
            sys.exit(1)

        tunnels = data.get("tunnels", {})
        loaded = 0
        for tid, info in tunnels.items():
            t = info.get("type", "")
            self._tunnels[tid] = info
            if t == "http":
                self._used_subdomains.add(info.get("subdomain", ""))
            elif t == "tcp":
                port = info.get("remote_port")
                if port:
                    self._used_tcp_ports.add(int(port))
            elif t == "udp":
                port = info.get("remote_port")
                if port:
                    self._used_udp_ports.add(int(port))
            loaded += 1
        log.info(
            "Loaded %d persisted tunnel allocation(s)",
            loaded,
        )

    def _save_state(self) -> None:
        """Persist current allocations to disk safely. Called under self._lock."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            
            # Serialize first — if this fails (e.g. memory), we don't touch disk
            json_data = json.dumps({"tunnels": self._tunnels}, indent=2)
            
            tmp = STATE_FILE.with_suffix(".json.tmp")
            
            # Write to tmp — if this fails (e.g. disk full), we don't touch STATE_FILE
            tmp.write_text(json_data, "utf-8")
            
            # If we have an existing state file, move it to backup
            bak_file = STATE_FILE.with_suffix(".json.bak")
            if STATE_FILE.exists():
                try:
                    shutil.copy2(STATE_FILE, bak_file)
                except Exception as exc:
                    log.warning("Failed to create backup state file %s: %s", bak_file, exc)
            
            # Atomic replace on POSIX
            tmp.replace(STATE_FILE)
            
        except OSError as exc:
            log.error("CRITICAL: Failed to persist state to disk (Disk full? Permissions?): %s", exc)
            # We don't crash here because we want to keep serving active tunnels,
            # but we log loudly so the admin knows state is unsaved.
        except Exception as exc:
            log.error("CRITICAL: Unexpected error saving state: %s", exc)

    # ── HTTP ─────────────────────────────────────────────────────────────

    def allocate_http(self, local_host: str, local_port: int, req_sub: str | None = None) -> dict:
        with self._lock:
            if req_sub:
                subdomain = req_sub
                if subdomain in self._used_subdomains:
                    raise RuntimeError(f"Subdomain '{subdomain}' is already in use.")
            else:
                subdomain = self._new_subdomain()

            proxy_name = f"portx-http-{subdomain}"
            tunnel_id  = str(uuid.uuid4())
            now        = time.time()

            self._used_subdomains.add(subdomain)
            self._tunnels[tunnel_id] = {
                "type":       "http",
                "subdomain":  subdomain,
                "proxy_name": proxy_name,
                "local_host": local_host,
                "local_port": local_port,
                "created_at": now,
                "last_seen":  now,
            }
            self._save_state()

            return {
                "tunnel_id":  tunnel_id,
                "type":       "http",
                "subdomain":  subdomain,
                "public_url": f"https://{subdomain}.{HTTP_DOMAIN}",
                "proxy_name": proxy_name,
                "frps_host":  FRPS_HOST,
                "frps_port":  FRPS_PORT,
            }

    # ── TCP ──────────────────────────────────────────────────────────────

    def allocate_tcp(self, local_host: str, local_port: int) -> dict:
        with self._lock:
            port = self._new_port(self._used_tcp_ports, TCP_PORT_MIN, TCP_PORT_MAX)
            if port is None:
                raise RuntimeError("No TCP ports available. Try again later.")

            proxy_name = f"portx-tcp-{port}"
            tunnel_id  = str(uuid.uuid4())
            now        = time.time()

            self._used_tcp_ports.add(port)
            self._tunnels[tunnel_id] = {
                "type":        "tcp",
                "remote_port": port,
                "proxy_name":  proxy_name,
                "local_host":  local_host,
                "local_port":  local_port,
                "created_at":  now,
                "last_seen":   now,
            }
            self._save_state()

            return {
                "tunnel_id":   tunnel_id,
                "type":        "tcp",
                "remote_port": port,
                "public_host": TCP_DOMAIN,
                "public_url":  f"{TCP_DOMAIN}:{port}",
                "proxy_name":  proxy_name,
                "frps_host":   FRPS_HOST,
                "frps_port":   FRPS_PORT,
            }

    # ── UDP ──────────────────────────────────────────────────────────────

    def allocate_udp(self, local_host: str, local_port: int) -> dict:
        with self._lock:
            port = self._new_port(self._used_udp_ports, UDP_PORT_MIN, UDP_PORT_MAX)
            if port is None:
                raise RuntimeError("No UDP ports available. Try again later.")

            proxy_name = f"portx-udp-{port}"
            tunnel_id  = str(uuid.uuid4())
            now        = time.time()

            self._used_udp_ports.add(port)
            self._tunnels[tunnel_id] = {
                "type":        "udp",
                "remote_port": port,
                "proxy_name":  proxy_name,
                "local_host":  local_host,
                "local_port":  local_port,
                "created_at":  now,
                "last_seen":   now,
            }
            self._save_state()

            return {
                "tunnel_id":   tunnel_id,
                "type":        "udp",
                "remote_port": port,
                "public_host": UDP_DOMAIN,
                "public_url":  f"{UDP_DOMAIN}:{port}",
                "proxy_name":  proxy_name,
                "frps_host":   FRPS_HOST,
                "frps_port":   FRPS_PORT,
            }

    # ── Release ───────────────────────────────────────────────────────────

    def release(self, tunnel_id: str) -> bool:
        """
        Free allocations for `tunnel_id`.
        Returns True if the tunnel existed and was released, False otherwise.
        """
        with self._lock:
            info = self._tunnels.pop(tunnel_id, None)
            if info is None:
                return False

            t = info.get("type", "")
            if t == "http":
                self._used_subdomains.discard(info.get("subdomain", ""))
            elif t == "tcp":
                port = info.get("remote_port")
                if port:
                    self._used_tcp_ports.discard(int(port))
            elif t == "udp":
                port = info.get("remote_port")
                if port:
                    self._used_udp_ports.discard(int(port))

            self._save_state()
            return True

    # ── Reregister ────────────────────────────────────────────────────────

    def reregister(self, tunnel_id: str, req: dict) -> dict:
        """
        Allow a client to reclaim its exact allocation after reconnecting.

        Strategy:
          1. If tunnel_id still in our state → return the existing allocation
             (this covers normal frpc reconnections and server restarts that
             loaded state.json from disk).
          2. If tunnel_id not found (state.json was lost):
             → Try to re-add the requested subdomain/port with the same tunnel_id.
             → If the requested resource is free: succeed.
             → If taken by a different tunnel: raise RuntimeError("conflict").

        Raises RuntimeError on conflict.
        """
        with self._lock:
            # Case 1: allocation is still alive
            existing = self._tunnels.get(tunnel_id)
            if existing:
                # Update last_seen and return
                existing["last_seen"] = time.time()
                existing["local_host"] = req.get("local_host", existing.get("local_host", "127.0.0.1"))
                existing["local_port"] = req.get("local_port", existing.get("local_port", 0))
                self._save_state()
                return self._build_response(tunnel_id, existing)

            # Case 2: not found — try to reclaim
            t = req.get("type", "")
            local_host = req.get("local_host", "127.0.0.1")
            local_port = int(req.get("local_port", 0))
            now        = time.time()

            if t == "http":
                subdomain  = req.get("subdomain", "")
                proxy_name = req.get("proxy_name") or f"portx-http-{subdomain}"
                if not subdomain:
                    raise RuntimeError("Cannot reregister HTTP tunnel: subdomain missing")
                if subdomain in self._used_subdomains:
                    raise RuntimeError(
                        f"Subdomain '{subdomain}' is now held by a different tunnel — "
                        "request a new tunnel instead"
                    )
                self._used_subdomains.add(subdomain)
                self._tunnels[tunnel_id] = {
                    "type": "http", "subdomain": subdomain,
                    "proxy_name": proxy_name, "local_host": local_host,
                    "local_port": local_port, "created_at": now, "last_seen": now,
                }
                self._save_state()
                return {
                    "tunnel_id":  tunnel_id, "type": "http",
                    "subdomain":  subdomain,
                    "public_url": f"https://{subdomain}.{HTTP_DOMAIN}",
                    "proxy_name": proxy_name,
                    "frps_host":  FRPS_HOST, "frps_port": FRPS_PORT,
                }

            elif t in ("tcp", "udp"):
                remote_port = int(req.get("remote_port") or 0)
                proxy_name  = req.get("proxy_name") or f"portx-{t}-{remote_port}"
                if not remote_port:
                    raise RuntimeError(f"Cannot reregister {t.upper()} tunnel: remote_port missing")
                used_set = self._used_tcp_ports if t == "tcp" else self._used_udp_ports
                if remote_port in used_set:
                    raise RuntimeError(
                        f"Port {remote_port} is now held by a different tunnel — "
                        "request a new tunnel instead"
                    )
                used_set.add(remote_port)
                self._tunnels[tunnel_id] = {
                    "type": t, "remote_port": remote_port,
                    "proxy_name": proxy_name, "local_host": local_host,
                    "local_port": local_port, "created_at": now, "last_seen": now,
                }
                self._save_state()
                domain = TCP_DOMAIN if t == "tcp" else UDP_DOMAIN
                return {
                    "tunnel_id": tunnel_id, "type": t,
                    "remote_port": remote_port, "public_host": domain,
                    "public_url":  f"{domain}:{remote_port}",
                    "proxy_name": proxy_name,
                    "frps_host":  FRPS_HOST, "frps_port": FRPS_PORT,
                }

            raise RuntimeError(f"Unknown tunnel type for reregister: {t!r}")

    # ── Heartbeat ─────────────────────────────────────────────────────────

    def heartbeat(self, tunnel_id: str) -> bool:
        """Update last_seen timestamp. Returns False if tunnel_id unknown."""
        with self._lock:
            info = self._tunnels.get(tunnel_id)
            if info is None:
                return False
            info["last_seen"] = time.time()
            # Save state periodically but not on every heartbeat (debounced)
            # State is persisted every allocate/release; heartbeat is best-effort.
            return True

    # ── Info ──────────────────────────────────────────────────────────────

    def get_info(self, tunnel_id: str) -> dict | None:
        with self._lock:
            info = self._tunnels.get(tunnel_id)
            if info is None:
                return None
            return self._build_response(tunnel_id, info)

    # ── Internals ─────────────────────────────────────────────────────────

    def _build_response(self, tunnel_id: str, info: dict) -> dict:
        t = info.get("type", "")
        if t == "http":
            subdomain = info.get("subdomain", "")
            return {
                "tunnel_id":  tunnel_id, "type": "http",
                "subdomain":  subdomain,
                "public_url": f"https://{subdomain}.{HTTP_DOMAIN}",
                "proxy_name": info.get("proxy_name", f"portx-http-{subdomain}"),
                "frps_host":  FRPS_HOST, "frps_port": FRPS_PORT,
            }
        elif t in ("tcp", "udp"):
            port   = info.get("remote_port", 0)
            domain = TCP_DOMAIN if t == "tcp" else UDP_DOMAIN
            return {
                "tunnel_id":   tunnel_id, "type": t,
                "remote_port": port, "public_host": domain,
                "public_url":  f"{domain}:{port}",
                "proxy_name":  info.get("proxy_name", f"portx-{t}-{port}"),
                "frps_host":   FRPS_HOST, "frps_port": FRPS_PORT,
            }
        return {"tunnel_id": tunnel_id, **info}

    def _new_subdomain(self) -> str:
        """Generate a unique random subdomain."""
        for _ in range(1000):
            sub = "".join(random.choices(SUBDOMAIN_CHARS, k=SUBDOMAIN_LEN))
            if sub not in self._used_subdomains:
                return sub
        raise RuntimeError("Could not generate a unique subdomain.")

    @staticmethod
    def _new_port(used: set[int], lo: int, hi: int) -> int | None:
        """Pick a random unused port from [lo, hi]."""
        available = list(set(range(lo, hi + 1)) - used)
        if not available:
            return None
        return random.choice(available)


# Singleton allocator shared by all request handlers
_allocator = TunnelAllocator()


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class PortXHandler(BaseHTTPRequestHandler):

    # ── Silence default access log — we use our own ───────────────────────
    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    # ── Helpers ───────────────────────────────────────────────────────────

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_empty(self, code: int) -> None:
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode())
        except Exception:
            return None

    # ── POST /api/v1/tunnel ───────────────────────────────────────────────

    def do_POST(self) -> None:
        # New tunnel
        if self.path == "/api/v1/tunnel":
            self._handle_new_tunnel()
            return

        # Reregister: POST /api/v1/tunnel/<id>/reregister
        m = re.fullmatch(r"/api/v1/tunnel/([0-9a-f-]+)/reregister", self.path)
        if m:
            self._handle_reregister(m.group(1))
            return

        self._send_json(404, {"error": "Not found"})

    def _handle_new_tunnel(self) -> None:
        body = self._read_json_body()
        if body is None:
            self._send_json(400, {"error": "Invalid JSON body"})
            return

        tunnel_type = body.get("type", "").lower()
        local_host  = body.get("local_host", "127.0.0.1")
        local_port  = body.get("local_port")
        req_sub     = body.get("subdomain")

        if tunnel_type not in ("http", "tcp", "udp"):
            self._send_json(400, {"error": f"Invalid tunnel type: '{tunnel_type}'"})
            return

        if not isinstance(local_port, int) or not (1 <= local_port <= 65535):
            self._send_json(400, {"error": f"Invalid local_port: {local_port!r}"})
            return

        try:
            if tunnel_type == "http":
                info = _allocator.allocate_http(local_host, local_port, req_sub)
            elif tunnel_type == "tcp":
                info = _allocator.allocate_tcp(local_host, local_port)
            else:
                info = _allocator.allocate_udp(local_host, local_port)
        except RuntimeError as exc:
            self._send_json(503, {"error": str(exc)})
            return

        log.info(
            "Tunnel created  type=%-4s  id=%s  public=%s",
            tunnel_type, info["tunnel_id"], info["public_url"],
        )
        self._send_json(200, info)

    def _handle_reregister(self, tunnel_id: str) -> None:
        body = self._read_json_body()
        if body is None:
            self._send_json(400, {"error": "Invalid JSON body"})
            return

        try:
            info = _allocator.reregister(tunnel_id, body)
        except RuntimeError as exc:
            err = str(exc)
            if "held by a different tunnel" in err:
                log.warning("Reregister conflict  id=%s  reason=%s", tunnel_id, err)
                self._send_json(409, {"error": err})
            else:
                log.warning("Reregister failed    id=%s  reason=%s", tunnel_id, err)
                self._send_json(400, {"error": err})
            return

        log.info("Tunnel reregistered  id=%s  public=%s", tunnel_id, info.get("public_url"))
        self._send_json(200, info)

    # ── DELETE /api/v1/tunnel/<id> ────────────────────────────────────────

    def do_DELETE(self) -> None:
        m = re.fullmatch(r"/api/v1/tunnel/([0-9a-f-]+)", self.path)
        if not m:
            self._send_json(404, {"error": "Not found"})
            return

        tunnel_id = m.group(1)
        released  = _allocator.release(tunnel_id)

        if released:
            log.info("Tunnel released  id=%s", tunnel_id)
        else:
            log.warning("Release request for unknown tunnel id=%s", tunnel_id)

        self._send_empty(204)

    # ── GET (health, tunnel info) ─────────────────────────────────────────

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "tunnels": len(_allocator._tunnels)})
            return

        m = re.fullmatch(r"/api/v1/tunnel/([0-9a-f-]+)", self.path)
        if m:
            info = _allocator.get_info(m.group(1))
            if info:
                self._send_json(200, info)
            else:
                self._send_json(404, {"error": "Tunnel not found"})
            return

        self._send_json(404, {"error": "Not found"})

    # ── PUT /api/v1/tunnel/<id>/heartbeat ─────────────────────────────────

    def do_PUT(self) -> None:
        m = re.fullmatch(r"/api/v1/tunnel/([0-9a-f-]+)/heartbeat", self.path)
        if not m:
            self._send_json(404, {"error": "Not found"})
            return

        tunnel_id = m.group(1)
        found = _allocator.heartbeat(tunnel_id)
        if found:
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "Tunnel not found — may need to reregister"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("PortX API server v2.1 starting...")
    log.info("  State file  : %s", STATE_FILE)
    log.info("  HTTP domain : *.%s", HTTP_DOMAIN)
    log.info("  TCP domain  : %s  (ports %d–%d)", TCP_DOMAIN, TCP_PORT_MIN, TCP_PORT_MAX)
    log.info("  UDP domain  : %s  (ports %d–%d)", UDP_DOMAIN, UDP_PORT_MIN, UDP_PORT_MAX)
    log.info("  frps        : %s:%d", FRPS_HOST, FRPS_PORT)

    server = HTTPServer((API_HOST, API_PORT), PortXHandler)
    log.info("Listening on %s:%d", API_HOST, API_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
