#!/usr/bin/env python3
"""
PortX CLI — v2.1 Background Tunnels
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
    """Generate a random human-readable tunnel name."""
    adjectives = [
        "swift", "blue", "brave", "calm", "clever", "eager", "fierce", "gentle",
        "happy", "jolly", "kind", "lively", "proud", "quiet", "red", "silent",
        "witty", "wild", "cool", "epic",
    ]
    nouns = [
        "falcon", "lion", "tiger", "bear", "wolf", "eagle", "shark", "hawk",
        "fox", "panther", "rhino", "snake", "whale", "owl", "bison", "cobra",
        "raven", "lynx",
    ]
    return f"{random.choice(adjectives)}-{random.choice(nouns)}"


def _start_tunnel(
    tunnel_type: str,
    local_addr_str: str,
    name: str | None,
    subdomain: str | None = None,
    public_port: int | None = None,
    auto_start: bool = False,
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

    # 2. Port validation & conflict check (for custom TCP/UDP ports)
    if public_port is not None:
        if not (1 <= public_port <= 65000):
            _err(f"Invalid public port: {public_port} — must be between 1 and 65000.")
        for t_name, t_data in tunnels.items():
            if t_data.get("type") == tunnel_type and t_data.get("remote_port") == public_port:
                _err(
                    f"Public port {public_port} is already used by {tunnel_type.upper()} tunnel '{t_name}'.\n"
                    f"  Choose a different port or stop/remove '{t_name}' first."
                )

    # 3. Parse address
    try:
        local_host, local_port = _address.parse_local_address(local_addr_str)
    except _address.AddressError as exc:
        _err(str(exc))

    display_local = _address.format_local(local_host, local_port)

    # 4. Request tunnel from server
    print(f"  → Requesting {tunnel_type.upper()} tunnel...")
    try:
        info = _api.request_tunnel(
            tunnel_type, local_host, local_port,
            subdomain=subdomain, remote_port=public_port,
        )
    except _api.APIError as exc:
        _err(str(exc))

    tunnel_id  = info["tunnel_id"]
    public_url = info.get("public_url", "")
    proxy_name = info["proxy_name"]
    frps_host  = info.get("frps_host", _cfg.FRPS_HOST)
    frps_port  = info.get("frps_port", _cfg.FRPS_PORT)

    # 4. Generate TOML config
    if tunnel_type == "http":
        assigned_sub = subdomain if subdomain else info.get("subdomain", "")
        public_url   = f"https://{assigned_sub}.{_cfg.HTTP_TUNNEL_DOMAIN}"
        toml = _toml.generate_http_config(
            local_host=local_host, local_port=local_port,
            subdomain=assigned_sub, proxy_name=proxy_name,
            frps_host=frps_host, frps_port=frps_port,
        )
    elif tunnel_type == "tcp":
        toml = _toml.generate_tcp_config(
            local_host=local_host, local_port=local_port,
            remote_port=info["remote_port"], proxy_name=proxy_name,
            frps_host=frps_host, frps_port=frps_port,
        )
    else:
        toml = _toml.generate_udp_config(
            local_host=local_host, local_port=local_port,
            remote_port=info["remote_port"], proxy_name=proxy_name,
            frps_host=frps_host, frps_port=frps_port,
        )

    # 5. Write config to persistent file
    config_path = _state.CONFIGS_DIR / f"{name}.toml"
    config_path.write_text(toml, "utf-8")

    log_path = _state.LOGS_DIR / f"{name}.log"

    subdomain_to_save  = assigned_sub if tunnel_type == "http" else None
    remote_port_to_save = info.get("remote_port") if tunnel_type in ("tcp", "udp") else None

    # 6. Save state (includes proxy_name and remote_port for reconnect)
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
        proxy_name=proxy_name,
        subdomain=subdomain_to_save,
        remote_port=remote_port_to_save,
        auto_start=1,
        admin_stopped=0,
    )

    # 7. Spawn background worker
    _cmds._spawn_worker(name)

    print("  ✓ Tunnel active\n")
    print(f"  Name:        {name}")
    print(f"  Local:       {display_local}")
    print(f"  Public:      {public_url}")
    print()
    print("  ✓ Running in background\n")
    print("  Tip: Run 'portx watchdog install' if you haven't already,")
    print("       to enable boot-time auto-start for all tunnels.\n")


_HELP_EPILOG = """
Examples:
  portx http 8080                                       # HTTP tunnel to local port 8080
  portx http 192.168.0.9:8080 my-app -s test            # portx http <ip:port> <name> -s <subdomain>
  portx https 127.0.0.1:3000 my-app -s test             # portx https <ip:port> <name> -s <subdomain>
  portx tcp 25565                                       # TCP tunnel (auto-assigned public port)
  portx tcp 192.168.0.9:25565 mc-server -p 25565       # portx tcp <ip:port> <name> -p <remote port>
  portx udp 7777                                        # UDP tunnel (auto-assigned public port)
  portx udp 192.168.0.9:19132 bedrock -p 19132         # portx udp <ip:port> <name> -p <remote port>
  portx stop my-app                                     # Stop a tunnel (URL/port reserved)
  portx stop --all                                      # Stop all active tunnels
  portx start my-app                                    # Start a saved stopped tunnel
  portx start --all                                     # Start all saved stopped tunnels
  portx restart my-app                                  # Restart a running or stopped tunnel
  portx reload                                          # Gracefully reload all running tunnels (zero-downtime)
  portx reload my-app                                   # Gracefully reload a specific tunnel
  portx edit my-app                                     # Interactively edit a tunnel's configuration
  portx remove my-app                                   # Permanently delete tunnel and release URL/port
  portx remove --all                                    # Permanently delete all tunnels
  portx list                                            # View all tunnels and their status
  portx info my-app                                     # Show detailed tunnel configuration
  portx status                                          # System health and server connection
  portx watchdog install                                # Enable boot-time auto-start background service
  portx watchdog status                                 # Check watchdog daemon health
  portx api <token>                                     # Set or update your auth token
  portx api ls                                          # Show current API URL and token
"""

def main() -> None:
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in ("help", "-h", "--help")):
        _hdr()
        print("  PortX — Simple tunnels")
        print("\n  Usage:")
        print("    portx <command> [options]\n")
        print("  Commands:")
        print("    http        Create an HTTP tunnel")
        print("    https       Create an HTTPS tunnel")
        print("    tcp         Create a TCP tunnel")
        print("    udp         Create a UDP tunnel")
        print("    list        List all tunnels")
        print("    info        Show detailed info for a tunnel")
        print("    stop        Stop a running tunnel (keeps URL/port reserved)")
        print("    start       Start a stopped tunnel")
        print("    restart     Restart a tunnel")
        print("    reload      Gracefully reload tunnel config (zero-downtime)")
        print("    edit        Interactively edit a tunnel's configuration")
        print("    remove      Permanently delete a tunnel and release its URL/port")
        print("    status      Show PortX system status")
        print("    watchdog    Manage the boot-time auto-start service")
        print("    api         Set auth token or show config")
        print("    cleanup     Clean up orphaned tunnel files")
        print("    uninstall   Complete system uninstall of PortX\n")
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
    p_http = subparsers.add_parser(
        "http", help="Create an HTTP tunnel",
        description="Creates a persistent background HTTP tunnel exposing your local server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  portx http 8080
  portx http 8080 my-app
  portx http 192.168.0.9:8080 my-app -s test
  portx http <ip:port> <name> -s <subdomain>""",
    )
    p_http.add_argument("local_address", help="Port or host:port (e.g., 8080 or 127.0.0.1:8080)")
    p_http.add_argument("name", nargs="?", help="Optional custom tunnel name. If omitted, one is generated.")
    p_http.add_argument("-s", "--s", "--subdomain", dest="subdomain", help="Request a specific subdomain (e.g., 'noob')")

    # --- HTTPS ---
    p_https = subparsers.add_parser(
        "https", help="Create an HTTPS tunnel",
        description="Creates a persistent background HTTPS tunnel exposing your local server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  portx https 8080
  portx https 8080 my-app
  portx https 127.0.0.1:3000 my-app -s test
  portx https <ip:port> <name> -s <subdomain>""",
    )
    p_https.add_argument("local_address", help="Port or host:port (e.g., 8080 or 127.0.0.1:8080)")
    p_https.add_argument("name", nargs="?", help="Optional custom tunnel name. If omitted, one is generated.")
    p_https.add_argument("-s", "--s", "--subdomain", dest="subdomain", help="Request a specific subdomain (e.g., 'noob')")

    # --- TCP ---
    p_tcp = subparsers.add_parser(
        "tcp", help="Create a TCP tunnel",
        description="Creates a persistent background TCP tunnel exposing your local port.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  portx tcp 25565
  portx tcp 192.168.0.9:25565 mc-server -p 25565
  portx tcp <ip:port> <name> -p <remote port>""",
    )
    p_tcp.add_argument("local_address", help="Port or host:port")
    p_tcp.add_argument("name", nargs="?", help="Optional custom tunnel name")
    p_tcp.add_argument("-p", "--p", "--port", dest="public_port", type=int, help="Optional custom public port (1-65000, e.g., 25565)")

    # --- UDP ---
    p_udp = subparsers.add_parser(
        "udp", help="Create a UDP tunnel",
        description="Creates a persistent background UDP tunnel exposing your local port.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  portx udp 7777
  portx udp 192.168.0.9:19132 bedrock -p 19132
  portx udp <ip:port> <name> -p <remote port>""",
    )
    p_udp.add_argument("local_address", help="Port or host:port")
    p_udp.add_argument("name", nargs="?", help="Optional custom tunnel name")
    p_udp.add_argument("-p", "--p", "--port", dest="public_port", type=int, help="Optional custom public port (1-65000, e.g., 19132)")

    # --- LIST ---
    subparsers.add_parser("list", help="List all tunnels",
        description="List all tunnels and their current running state.")

    # --- INFO ---
    p_info = subparsers.add_parser("info", help="Show tunnel info")
    p_info.add_argument("name", help="Tunnel name")

    # --- STOP ---
    p_stop = subparsers.add_parser(
        "stop", help="Stop a tunnel (keeps URL/port reserved)",
        description=(
            "Stops the tunnel worker process but keeps the server-side allocation.\n"
            "The same public URL or TCP port is preserved and can be reclaimed\n"
            "with 'portx restart <name>'."
        ),
    )
    p_stop.add_argument("name", nargs="?", help="Tunnel name to stop")
    p_stop.add_argument("--all", action="store_true", help="Stop all active tunnels")

    # --- START ---
    p_start = subparsers.add_parser(
        "start", help="Start a stopped tunnel",
        description="Starts the tunnel worker process for a saved tunnel.",
    )
    p_start.add_argument("name", nargs="?", help="Tunnel name to start")
    p_start.add_argument("--all", action="store_true", help="Start all saved stopped tunnels")

    # --- REMOVE ---
    p_remove = subparsers.add_parser(
        "remove", help="Remove a tunnel and release its URL/port",
        description=(
            "Permanently removes a tunnel and releases its public URL or TCP port\n"
            "back to the pool. This cannot be undone — the URL/port may be reassigned."
        ),
    )
    p_remove.add_argument("name", nargs="?", help="Tunnel name to remove")
    p_remove.add_argument("--all", action="store_true", help="Remove all tunnels")

    # --- RESTART ---
    p_restart = subparsers.add_parser("restart", help="Restart a tunnel")
    p_restart.add_argument("name", help="Tunnel name to restart")

    # --- EDIT ---
    p_edit = subparsers.add_parser(
        "edit", help="Interactively edit a tunnel's configuration",
        description="Opens the tunnel's configuration file in your editor ($EDITOR).",
    )
    p_edit.add_argument("name", help="Tunnel name to edit")

    # --- RELOAD ---
    p_reload = subparsers.add_parser(
        "reload",
        help="Gracefully reload running tunnels (zero-downtime where possible)",
        description=(
            "Sends SIGUSR1 to each running tunnel worker, which kills and immediately\n"
            "restarts frpc with the latest config. The same proxy name, subdomain,\n"
            "and TCP/UDP port are preserved — existing connections resume within seconds.\n\n"
            "If no name is given, all running tunnels are reloaded.\n"
            "Stopped or failed tunnels are skipped (use 'portx restart' for those)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_reload.add_argument("name", nargs="?", help="Tunnel name to reload (default: all running)")

    # --- STATUS ---
    subparsers.add_parser("status", help="Show PortX status")

    # --- WATCHDOG ---
    p_watchdog = subparsers.add_parser(
        "watchdog",
        help="Manage the boot-time auto-start service",
        description=(
            "The PortX watchdog is a background daemon that automatically starts\n"
            "tunnels marked with --auto-start after a reboot or power failure.\n\n"
            "Subcommands:\n"
            "  portx watchdog install     Install and start the watchdog service\n"
            "  portx watchdog uninstall   Remove the watchdog service\n"
            "  portx watchdog status      Show watchdog health\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_watchdog.add_argument(
        "subcommand",
        choices=["install", "uninstall", "status"],
        help="install | uninstall | status",
    )

    # --- CLEANUP ---
    p_cleanup = subparsers.add_parser("cleanup", help="Clean up orphaned tunnel files")
    p_cleanup.add_argument("--force", action="store_true",
        help="Force cleanup of all stopped tunnels")

    # --- UNINSTALL ---
    subparsers.add_parser("uninstall", aliases=["unistall"],
        help="Complete system uninstall of PortX")

    # --- API ---
    p_api = subparsers.add_parser(
        "api",
        help="Set auth token or show config",
        description=(
            "Manage your PortX auth token and API configuration.\n\n"
            "  portx api <token>   Set or update your auth token\n"
            "  portx api ls        Show the current API URL and token\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_api.add_argument(
        "subcommand",
        nargs="?",
        metavar="<token>|ls",
        help="Auth token to save, or 'ls' to display current config",
    )

    args = parser.parse_args()

    try:
        if args.command in ("http", "https"):
            _start_tunnel("http", args.local_address, args.name, args.subdomain)
        elif args.command == "tcp":
            _start_tunnel("tcp", args.local_address, args.name, public_port=getattr(args, "public_port", None))
        elif args.command == "udp":
            _start_tunnel("udp", args.local_address, args.name, public_port=getattr(args, "public_port", None))
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
        elif args.command == "start":
            if args.all:
                _cmds.cmd_start_all()
            elif args.name:
                _cmds.cmd_start(args.name)
            else:
                _err("Specify a tunnel name or use --all.")
        elif args.command == "restart":
            _cmds.cmd_restart(args.name)
        elif args.command == "edit":
            _cmds.cmd_edit(args.name)
        elif args.command == "reload":
            _cmds.cmd_reload(getattr(args, "name", None))
        elif args.command == "status":
            _cmds.cmd_status()
        elif args.command == "watchdog":
            sub = args.subcommand
            if sub == "install":
                _cmds.cmd_watchdog_install()
            elif sub == "uninstall":
                _cmds.cmd_watchdog_uninstall()
            elif sub == "status":
                _cmds.cmd_watchdog_status()
        elif args.command == "cleanup":
            _cmds.cmd_cleanup(args.force)
        elif args.command in ("uninstall", "unistall"):
            _cmds.cmd_uninstall()
        elif args.command == "api":
            sub = getattr(args, "subcommand", None)
            if sub is None or sub == "":
                _err("Usage: portx api <token>  or  portx api ls")
            elif sub == "ls":
                _cmds.cmd_api_ls()
            else:
                _cmds.cmd_api_set(sub)
    except KeyboardInterrupt:
        print("\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
