#!/usr/bin/env python3
"""
PortX API Server — v2
Runs on the VPS alongside frps.

Responsibilities:
  • Allocate random HTTP subdomains (6-char alphanumeric, collision-safe)
  • Allocate TCP ports from a configurable range
  • Allocate UDP ports from a configurable range
  • Return frps connection info to PortX CLI clients
  • Release allocations when a tunnel is closed

REST API:

  POST  /api/v1/tunnel
    Body:     {"type": "http"|"tcp"|"udp", "local_host": str, "local_port": int}
    200:      see _build_response() below
    400/503:  {"error": str}

  DELETE /api/v1/tunnel/<tunnel_id>
    204:  no body

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
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import string
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
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
# Tunnel allocator (thread-safe)
# ---------------------------------------------------------------------------

class TunnelAllocator:
    """
    Manages subdomain and port allocations for active tunnels.
    All public methods are thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # tunnel_id → {type, subdomain/remote_port, ...}
        self._tunnels: dict[str, dict] = {}
        self._used_subdomains: set[str] = set()
        self._used_tcp_ports:  set[int] = set()
        self._used_udp_ports:  set[int] = set()

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
            
            public_url = f"https://{subdomain}.{HTTP_DOMAIN}"

            self._used_subdomains.add(subdomain)
            self._tunnels[tunnel_id] = {
                "type":       "http",
                "subdomain":  subdomain,
                "proxy_name": proxy_name,
                "local_host": local_host,
                "local_port": local_port,
            }

            return {
                "tunnel_id":  tunnel_id,
                "type":       "http",
                "subdomain":  subdomain,
                "public_url": public_url,
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

            self._used_tcp_ports.add(port)
            self._tunnels[tunnel_id] = {
                "type":        "tcp",
                "remote_port": port,
                "proxy_name":  proxy_name,
                "local_host":  local_host,
                "local_port":  local_port,
            }

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

            self._used_udp_ports.add(port)
            self._tunnels[tunnel_id] = {
                "type":        "udp",
                "remote_port": port,
                "proxy_name":  proxy_name,
                "local_host":  local_host,
                "local_port":  local_port,
            }

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

            t = info["type"]
            if t == "http":
                self._used_subdomains.discard(info["subdomain"])
            elif t == "tcp":
                self._used_tcp_ports.discard(info["remote_port"])
            elif t == "udp":
                self._used_udp_ports.discard(info["remote_port"])

            return True

    # ── Internals ─────────────────────────────────────────────────────────

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
        if self.path != "/api/v1/tunnel":
            self._send_json(404, {"error": "Not found"})
            return

        body = self._read_json_body()
        if body is None:
            self._send_json(400, {"error": "Invalid JSON body"})
            return

        tunnel_type = body.get("type", "").lower()
        local_host  = body.get("local_host", "127.0.0.1")
        local_port  = body.get("local_port")
        req_sub     = body.get("subdomain")
        req_dom     = body.get("domain")

        # Validate
        if tunnel_type not in ("http", "tcp", "udp"):
            self._send_json(400, {"error": f"Invalid tunnel type: '{tunnel_type}'"})
            return

        if not isinstance(local_port, int) or not (1 <= local_port <= 65535):
            self._send_json(400, {"error": f"Invalid local_port: {local_port!r}"})
            return

        # Allocate
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

    # ── Health check ──────────────────────────────────────────────────────

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "Not found"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    server = HTTPServer((API_HOST, API_PORT), PortXHandler)
    log.info("PortX API server listening on %s:%d", API_HOST, API_PORT)
    log.info(
        "  HTTP domain : *.%s", HTTP_DOMAIN,
    )
    log.info("  TCP domain  : %s  (ports %d–%d)", TCP_DOMAIN, TCP_PORT_MIN, TCP_PORT_MAX)
    log.info("  UDP domain  : %s  (ports %d–%d)", UDP_DOMAIN, UDP_PORT_MIN, UDP_PORT_MAX)
    log.info("  frps        : %s:%d", FRPS_HOST, FRPS_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
