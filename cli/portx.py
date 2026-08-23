#!/usr/bin/env python3
"""
PortX CLI — v2
Simple tunnels, no configuration required.

Usage:
  portx http <local-address>
  portx tcp  <local-address>
  portx udp  <local-address>

  portx --help
  portx http --help
"""

from __future__ import annotations

import os
import signal
import sys
import tempfile
import time
from pathlib import Path

# ── Make this file runnable directly (python3 cli/portx.py …) ─────────────
_CLI_DIR = Path(__file__).resolve().parent
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

import address   as _address
import api_client as _api
import config    as _cfg
import frp_config as _toml
import frp_runner as _runner


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _hdr() -> None:
    print()
    print("  ██████╗  ██████╗ ██████╗ ████████╗██╗  ██╗")
    print("  ██╔══██╗██╔═══██╗██╔══██╗╚══██╔══╝╚██╗██╔╝")
    print("  ██████╔╝██║   ██║██████╔╝   ██║    ╚███╔╝ ")
    print("  ██╔═══╝ ██║   ██║██╔══██╗   ██║    ██╔██╗ ")
    print("  ██║     ╚██████╔╝██║  ██║   ██║   ██╔╝ ██╗")
    print("  ╚═╝      ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝")
    print()


def _step(msg: str) -> None:
    print(f"  → {msg}")


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _err(msg: str, *, code: int = 1) -> None:
    print(f"\n  ✗ {msg}", file=sys.stderr)
    sys.exit(code)


def _sep() -> None:
    print("  ─────────────────────────────────────────")


# ---------------------------------------------------------------------------
# Help texts
# ---------------------------------------------------------------------------

_HELP_MAIN = """\
  PortX — Simple tunnels

  Usage:
    portx <type> <local-address>

  Tunnel types:
    http     Create an HTTP tunnel  (public HTTPS URL)
    tcp      Create a TCP tunnel    (public host:port)
    udp      Create a UDP tunnel    (public host:port)

  Examples:
    portx http 8080
    portx http localhost:3000
    portx http 127.0.0.1:8080
    portx tcp  25565
    portx udp  7777

  Run 'portx <type> --help' for type-specific help.
"""

_HELP_HTTP = """\
  portx http — Create an HTTP tunnel

  Usage:
    portx http <local-address>

  Arguments:
    local-address   Port or host:port of your local HTTP server.
                    Examples: 8080  |  localhost:3000  |  127.0.0.1:8080

  What happens:
    PortX assigns a random public subdomain and starts a tunnel so that
    traffic to https://<random>.portx.infinitynoob.lol is forwarded to
    your local server.

  Example:
    portx http 8080
    → Public: https://x7k29m.portx.infinitynoob.lol
"""

_HELP_TCP = """\
  portx tcp — Create a TCP tunnel

  Usage:
    portx tcp <local-address>

  Arguments:
    local-address   Port or host:port of your local TCP service.
                    Examples: 25565  |  127.0.0.1:25565

  What happens:
    PortX assigns a random public port on tcp.portx.infinitynoob.lol.
    Clients connect to that host:port and traffic is forwarded to your
    local service.

  Example:
    portx tcp 25565
    → Public: tcp.portx.infinitynoob.lol:30125
"""

_HELP_UDP = """\
  portx udp — Create a UDP tunnel

  Usage:
    portx udp <local-address>

  Arguments:
    local-address   Port or host:port of your local UDP service.
                    Examples: 7777  |  127.0.0.1:7777

  What happens:
    PortX assigns a random public port on udp.portx.infinitynoob.lol.

  Example:
    portx udp 7777
    → Public: udp.portx.infinitynoob.lol:32001
"""


# ---------------------------------------------------------------------------
# Core tunnel runner
# ---------------------------------------------------------------------------

def _run_tunnel(
    tunnel_type: str,
    local_addr_str: str,
    toml_content: str,
    display_local: str,
    display_public: str,
    tunnel_id: str,
) -> None:
    """
    Write the TOML config to a temp file, start frpc, display tunnel info,
    and block until Ctrl+C.  Always cleans up on exit.
    """
    proc = None
    toml_path: Path | None = None

    def _cleanup(signum=None, frame=None) -> None:
        print()
        print()
        _step("Stopping tunnel...")
        if proc:
            _runner.stop_frpc(proc)
        if toml_path and toml_path.exists():
            toml_path.unlink(missing_ok=True)
        _api.release_tunnel(tunnel_id)
        _ok("Tunnel stopped.")
        print()
        sys.exit(0)

    # Register Ctrl+C handler
    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    # Write TOML to a temp file
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".toml",
        prefix="portx_",
        delete=False,
    )
    tmp.write(toml_content)
    tmp.close()
    toml_path = Path(tmp.name)

    # Start frpc
    _step("Connecting to PortX server...")
    try:
        proc = _runner.start_frpc(
            toml_path,
            _cfg.FRP_BINARY,
            timeout=_cfg.FRPC_CONNECT_TIMEOUT,
        )
    except _runner.FRPError as exc:
        toml_path.unlink(missing_ok=True)
        _api.release_tunnel(tunnel_id)
        _err(str(exc))

    _ok("Connected")
    print()
    _ok(f"Tunnel active")
    print()
    _sep()
    print(f"  Local:  {display_local}")
    print(f"  Public: {display_public}")
    _sep()
    print()
    print("  Forwarding traffic...")
    print("  Press Ctrl+C to stop.")
    print()

    # Block until frpc exits or the user presses Ctrl+C
    while True:
        ret = proc.poll()
        if ret is not None:
            # frpc exited on its own (unexpected)
            toml_path.unlink(missing_ok=True)
            _api.release_tunnel(tunnel_id)
            _err(f"frpc exited unexpectedly (code {ret}).")
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# HTTP tunnel command
# ---------------------------------------------------------------------------

def cmd_http(local_addr_str: str) -> None:
    """portx http <local-address>"""
    _hdr()

    # 1. Parse local address
    try:
        local_host, local_port = _address.parse_local_address(local_addr_str)
    except _address.AddressError as exc:
        _err(str(exc))

    display_local = _address.format_local(local_host, local_port)

    # 2. Request tunnel from PortX server
    _step("Requesting HTTP tunnel from PortX server...")
    try:
        info = _api.request_tunnel("http", local_host, local_port)
    except _api.APIError as exc:
        _err(str(exc))

    tunnel_id   = info["tunnel_id"]
    subdomain   = info["subdomain"]
    public_url  = info["public_url"]
    proxy_name  = info["proxy_name"]
    frps_host   = info.get("frps_host", _cfg.FRPS_HOST)
    frps_port   = info.get("frps_port", _cfg.FRPS_PORT)

    _ok(f"Subdomain assigned: {subdomain}")
    print()

    # 3. Generate TOML
    toml = _toml.generate_http_config(
        local_host=local_host,
        local_port=local_port,
        subdomain=subdomain,
        proxy_name=proxy_name,
        frps_host=frps_host,
        frps_port=frps_port,
    )

    # 4. Run tunnel
    _run_tunnel(
        tunnel_type="http",
        local_addr_str=local_addr_str,
        toml_content=toml,
        display_local=display_local,
        display_public=public_url,
        tunnel_id=tunnel_id,
    )


# ---------------------------------------------------------------------------
# TCP tunnel command
# ---------------------------------------------------------------------------

def cmd_tcp(local_addr_str: str) -> None:
    """portx tcp <local-address>"""
    _hdr()

    try:
        local_host, local_port = _address.parse_local_address(local_addr_str)
    except _address.AddressError as exc:
        _err(str(exc))

    display_local = _address.format_local(local_host, local_port)

    _step("Requesting TCP tunnel from PortX server...")
    try:
        info = _api.request_tunnel("tcp", local_host, local_port)
    except _api.APIError as exc:
        _err(str(exc))

    tunnel_id   = info["tunnel_id"]
    remote_port = info["remote_port"]
    public_url  = info["public_url"]
    proxy_name  = info["proxy_name"]
    frps_host   = info.get("frps_host", _cfg.FRPS_HOST)
    frps_port   = info.get("frps_port", _cfg.FRPS_PORT)

    _ok(f"Public port assigned: {remote_port}")
    print()

    toml = _toml.generate_tcp_config(
        local_host=local_host,
        local_port=local_port,
        remote_port=remote_port,
        proxy_name=proxy_name,
        frps_host=frps_host,
        frps_port=frps_port,
    )

    _run_tunnel(
        tunnel_type="tcp",
        local_addr_str=local_addr_str,
        toml_content=toml,
        display_local=display_local,
        display_public=public_url,
        tunnel_id=tunnel_id,
    )


# ---------------------------------------------------------------------------
# UDP tunnel command
# ---------------------------------------------------------------------------

def cmd_udp(local_addr_str: str) -> None:
    """portx udp <local-address>"""
    _hdr()

    try:
        local_host, local_port = _address.parse_local_address(local_addr_str)
    except _address.AddressError as exc:
        _err(str(exc))

    display_local = _address.format_local(local_host, local_port)

    _step("Requesting UDP tunnel from PortX server...")
    try:
        info = _api.request_tunnel("udp", local_host, local_port)
    except _api.APIError as exc:
        _err(str(exc))

    tunnel_id   = info["tunnel_id"]
    remote_port = info["remote_port"]
    public_url  = info["public_url"]
    proxy_name  = info["proxy_name"]
    frps_host   = info.get("frps_host", _cfg.FRPS_HOST)
    frps_port   = info.get("frps_port", _cfg.FRPS_PORT)

    _ok(f"Public port assigned: {remote_port}")
    print()

    toml = _toml.generate_udp_config(
        local_host=local_host,
        local_port=local_port,
        remote_port=remote_port,
        proxy_name=proxy_name,
        frps_host=frps_host,
        frps_port=frps_port,
    )

    _run_tunnel(
        tunnel_type="udp",
        local_addr_str=local_addr_str,
        toml_content=toml,
        display_local=display_local,
        display_public=public_url,
        tunnel_id=tunnel_id,
    )


# ---------------------------------------------------------------------------
# Entry point / argument routing
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]

    # ── portx  /  portx --help ─────────────────────────────────────────────
    if not args or args[0] in ("-h", "--help", "help"):
        _hdr()
        print(_HELP_MAIN)
        sys.exit(0)

    cmd = args[0].lower()

    # ── portx http --help, etc. ────────────────────────────────────────────
    if len(args) == 1 and cmd in ("http", "tcp", "udp"):
        _hdr()
        helps = {"http": _HELP_HTTP, "tcp": _HELP_TCP, "udp": _HELP_UDP}
        print(helps[cmd])
        sys.exit(0)

    if len(args) >= 2 and args[1] in ("-h", "--help"):
        _hdr()
        helps = {"http": _HELP_HTTP, "tcp": _HELP_TCP, "udp": _HELP_UDP}
        if cmd in helps:
            print(helps[cmd])
        else:
            print(_HELP_MAIN)
        sys.exit(0)

    # ── Route to command ───────────────────────────────────────────────────
    if cmd not in ("http", "tcp", "udp"):
        _err(
            f"Unknown command: '{cmd}'\n"
            "  Run 'portx --help' to see available commands."
        )

    if len(args) < 2:
        _err(
            f"'portx {cmd}' requires a local address.\n"
            f"  Example: portx {cmd} 8080"
        )

    local_addr = args[1]

    dispatch = {"http": cmd_http, "tcp": cmd_tcp, "udp": cmd_udp}
    dispatch[cmd](local_addr)


if __name__ == "__main__":
    main()
