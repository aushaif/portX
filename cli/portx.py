#!/usr/bin/env python3
"""
PortX CLI — v2 Background Tunnels
"""

from __future__ import annotations

import argparse
import random
import string
import sys
from pathlib import Path

# ── Make this file runnable directly (python3 cli/portx.py …) ─────────────
_CLI_DIR = Path(__file__).resolve().parent
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

import address   as _address
import api_client as _api
import commands  as _cmds
import config    as _cfg
import frp_config as _toml
import state     as _state


def _hdr() -> None:
    print("\n  ██████╗  ██████╗ ██████╗ ████████╗██╗  ██╗")
    print("  ██╔══██╗██╔═══██╗██╔══██╗╚══██╔══╝╚██╗██╔╝")
    print("  ██████╔╝██║   ██║██████╔╝   ██║    ╚███╔╝ ")
    print("  ██╔═══╝ ██║   ██║██╔══██╗   ██║    ██╔██╗ ")
    print("  ██║     ╚██████╔╝██║  ██║   ██║   ██╔╝ ██╗")
    print("  ╚═╝      ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝\n")

def _err(msg: str) -> None:
    print(f"\n  ✗ {msg}\n", file=sys.stderr)
    sys.exit(1)

def _generate_name() -> str:
    """Generate a random human-readable name."""
    adjectives = ["swift", "blue", "brave", "calm", "clever", "eager", "fierce", "gentle", "happy", "jolly", "kind", "lively", "proud", "quiet", "red", "silent", "witty", "wild", "cool", "epic"]
    nouns = ["falcon", "lion", "tiger", "bear", "wolf", "eagle", "shark", "hawk", "fox", "panther", "rhino", "snake", "whale", "owl", "bison", "cobra", "raven", "lynx"]
    return f"{random.choice(adjectives)}-{random.choice(nouns)}"


def _start_tunnel(
    tunnel_type: str,
    local_addr_str: str,
    name: str | None,
    subdomain: str | None = None,
) -> None:
    _hdr()
    
    # 1. Name validation
    tunnels = _state.list_tunnels()
    if not name:
        name = _generate_name()
        while name in tunnels:
            name = _generate_name()
            
    if name in tunnels and tunnels[name].get("status") in ("starting", "running"):
        _err(f"Tunnel '{name}' is already running. Stop it first.")

    # 2. Parse address
    try:
        local_host, local_port = _address.parse_local_address(local_addr_str)
    except _address.AddressError as exc:
        _err(str(exc))

    display_local = _address.format_local(local_host, local_port)

    # 3. Request tunnel from server
    print(f"  → Requesting {tunnel_type.upper()} tunnel...")
    try:
        info = _api.request_tunnel(tunnel_type, local_host, local_port, subdomain)
    except _api.APIError as exc:
        _err(str(exc))

    tunnel_id   = info["tunnel_id"]
    public_url  = info.get("public_url", "")
    proxy_name  = info["proxy_name"]
    frps_host   = info.get("frps_host", _cfg.FRPS_HOST)
    frps_port   = info.get("frps_port", _cfg.FRPS_PORT)

    # 4. Generate TOML
    if tunnel_type == "http":
        assigned_sub = subdomain if subdomain else info.get("subdomain", "")
        public_url = f"https://{assigned_sub}.{_cfg.HTTP_TUNNEL_DOMAIN}"
            
        toml = _toml.generate_http_config(
            local_host=local_host,
            local_port=local_port,
            subdomain=assigned_sub,
            proxy_name=proxy_name,
            frps_host=frps_host,
            frps_port=frps_port,
        )
    elif tunnel_type == "tcp":
        toml = _toml.generate_tcp_config(
            local_host=local_host,
            local_port=local_port,
            remote_port=info["remote_port"],
            proxy_name=proxy_name,
            frps_host=frps_host,
            frps_port=frps_port,
        )
    else:
        toml = _toml.generate_udp_config(
            local_host=local_host,
            local_port=local_port,
            remote_port=info["remote_port"],
            proxy_name=proxy_name,
            frps_host=frps_host,
            frps_port=frps_port,
        )

    # 5. Write config to persistent file
    config_path = _state.CONFIGS_DIR / f"{name}.toml"
    config_path.write_text(toml, "utf-8")
    
    log_path = _state.LOGS_DIR / f"{name}.log"

    subdomain_to_save = None
    if tunnel_type == "http":
        subdomain_to_save = assigned_sub

    # 6. Save state
    _state.update_tunnel(
        name,
        type=tunnel_type,
        local_host=local_host,
        local_port=local_port,
        public_url=public_url,
        status="starting",
        frp_config_path=str(config_path),
        log_path=str(log_path),
        tunnel_id=tunnel_id,
        subdomain=subdomain_to_save,
    )

    # 7. Spawn background worker
    _cmds._spawn_worker(name)

    print("  ✓ Tunnel active\n")
    print(f"  Name:   {name}")
    print(f"  Local:  {display_local}")
    print(f"  Public: {public_url}\n")
    print("  ✓ Running in background\n")


_HELP_EPILOG = """
Examples:
  portx http 8080                   # HTTP tunnel to local port 8080
  portx http 8080 my-app            # HTTP tunnel named 'my-app'
  portx http 8080 --subdomain test  # HTTP tunnel on test.infinitynoob.lol
  portx tcp 25565                   # TCP tunnel to 25565
  portx stop my-app                 # Stop the tunnel
  portx list                        # View all running tunnels
"""

def main() -> None:
    # If standard 'help' is called or no arguments
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in ("help", "-h", "--help")):
        _hdr()
        print("  PortX — Simple tunnels")
        print("\n  Usage:")
        print("    portx <command> [options]\n")
        print("  Commands:")
        print("    http      Create an HTTP tunnel")
        print("    tcp       Create a TCP tunnel")
        print("    udp       Create a UDP tunnel")
        print("    list      List all active tunnels")
        print("    info      Show detailed info for a tunnel")
        print("    stop      Stop a running tunnel")
        print("    remove    Permanently delete a tunnel")
        print("    restart   Restart a stopped tunnel")
        print("    status    Show PortX system status")
        print("    cleanup   Clean up orphaned tunnel files")
        print("    uninstall Complete system uninstall of PortX\n")
        print("  Run 'portx <command> --help' for more information on a command.")
        print(_HELP_EPILOG)
        sys.exit(0)

    parser = argparse.ArgumentParser(
        prog="portx",
        description="PortX — Simple tunnels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_HELP_EPILOG,
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- HTTP ---
    p_http = subparsers.add_parser("http", help="Create an HTTP tunnel", description="Creates a persistent background HTTP tunnel exposing your local server.")
    p_http.add_argument("local_address", help="Port or host:port (e.g., 8080 or 127.0.0.1:8080)")
    p_http.add_argument("name", nargs="?", help="Optional custom tunnel name (e.g. 'website'). If omitted, one is generated.")
    p_http.add_argument("--subdomain", help="Request a specific subdomain (e.g., 'noob')")

    # --- TCP ---
    p_tcp = subparsers.add_parser("tcp", help="Create a TCP tunnel", description="Creates a persistent background TCP tunnel exposing your local port.")
    p_tcp.add_argument("local_address", help="Port or host:port")
    p_tcp.add_argument("name", nargs="?", help="Optional custom tunnel name")

    # --- UDP ---
    p_udp = subparsers.add_parser("udp", help="Create a UDP tunnel", description="Creates a persistent background UDP tunnel exposing your local port.")
    p_udp.add_argument("local_address", help="Port or host:port")
    p_udp.add_argument("name", nargs="?", help="Optional custom tunnel name")

    # --- LIST ---
    subparsers.add_parser("list", help="List all tunnels", description="List all tunnels and their current running state.")

    # --- INFO ---
    p_info = subparsers.add_parser("info", help="Show tunnel info")
    p_info.add_argument("name", help="Tunnel name")

    # --- STOP ---
    p_stop = subparsers.add_parser("stop", help="Stop a tunnel")
    p_stop.add_argument("name", nargs="?", help="Tunnel name to stop")
    p_stop.add_argument("--all", action="store_true", help="Stop all active tunnels")

    # --- REMOVE ---
    p_remove = subparsers.add_parser("remove", help="Remove a tunnel entirely")
    p_remove.add_argument("name", nargs="?", help="Tunnel name to remove")
    p_remove.add_argument("--all", action="store_true", help="Remove all tunnels")

    # --- RESTART ---
    p_restart = subparsers.add_parser("restart", help="Restart a tunnel")
    p_restart.add_argument("name", help="Tunnel name to restart")

    # --- STATUS ---
    subparsers.add_parser("status", help="Show PortX status")
    
    # --- CLEANUP ---
    p_cleanup = subparsers.add_parser("cleanup", help="Clean up orphaned tunnel files")
    p_cleanup.add_argument("--force", action="store_true", help="Force cleanup of all stopped tunnels")
    
    # --- UNINSTALL ---
    subparsers.add_parser("uninstall", help="Complete system uninstall of PortX")

    args = parser.parse_args()

    try:
        if args.command == "http":
            _start_tunnel("http", args.local_address, args.name, args.subdomain)
        elif args.command == "tcp":
            _start_tunnel("tcp", args.local_address, args.name)
        elif args.command == "udp":
            _start_tunnel("udp", args.local_address, args.name)
        elif args.command == "list":
            _cmds.cmd_list()
        elif args.command == "info":
            _cmds.cmd_info(args.name)
        elif args.command == "stop":
            if args.all:
                _cmds.cmd_stop_all()
            elif args.name:
                _cmds.cmd_stop(args.name)
            else:
                _err("Specify a tunnel name or use --all.")
        elif args.command == "remove":
            if args.all:
                _cmds.cmd_remove_all()
            elif args.name:
                _cmds.cmd_remove(args.name)
            else:
                _err("Specify a tunnel name or use --all.")
        elif args.command == "restart":
            _cmds.cmd_restart(args.name)
        elif args.command == "status":
            _cmds.cmd_status()
        elif args.command == "cleanup":
            _cmds.cmd_cleanup(args.force)
        elif args.command == "uninstall":
            _cmds.cmd_uninstall()
    except KeyboardInterrupt:
        print("\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
