"""
PortX client configuration.

All server addresses and tunables live here — never hardcoded elsewhere.
Override at runtime via environment variables if needed.
"""

from __future__ import annotations

import os
from pathlib import Path

# ── PortX API server ──────────────────────────────────────────────────────
# The PortX coordination server that allocates subdomains and ports.
PORTX_API_URL: str = os.environ.get(
    "PORTX_API_URL", "http://portx.infinitynoob.lol:8765"
)

# ── FRP server (frps) ─────────────────────────────────────────────────────
FRPS_HOST: str = os.environ.get("PORTX_FRPS_HOST", "portx.infinitynoob.lol")
FRPS_PORT: int = int(os.environ.get("PORTX_FRPS_PORT", "7000"))

# ── Public DNS ────────────────────────────────────────────────────────────
# HTTP tunnels use wildcard *.portx.infinitynoob.lol
HTTP_TUNNEL_DOMAIN: str = os.environ.get(
    "PORTX_HTTP_DOMAIN", "infinitynoob.lol"
)
# TCP/UDP tunnels use dedicated subdomains (DNS-only in Cloudflare)
TCP_TUNNEL_DOMAIN: str = os.environ.get(
    "PORTX_TCP_DOMAIN", "tcp.portx.infinitynoob.lol"
)
UDP_TUNNEL_DOMAIN: str = os.environ.get(
    "PORTX_UDP_DOMAIN", "udp.portx.infinitynoob.lol"
)

# ── Local FRP binary (installed by v1 installer or custom install) ────────────
# Defaults to ~/.portx/bin/frpc, fallback to src/bin/frpc
FRP_BINARY: Path = Path(
    os.environ.get(
        "PORTX_FRP_BINARY",
        str(Path.home() / ".portx" / "bin" / "frpc")
    )
)
if not FRP_BINARY.exists():
    fallback = Path(__file__).resolve().parent.parent / "bin" / "frpc"
    if fallback.exists():
        FRP_BINARY = fallback

# ── Timeouts ──────────────────────────────────────────────────────────────
API_TIMEOUT: int = 15           # seconds for PortX API calls
FRPC_CONNECT_TIMEOUT: int = 15  # seconds to wait for frpc to connect
