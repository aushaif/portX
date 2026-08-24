"""
Management commands for PortX background tunnels.
Implements list, info, stop, remove, restart, and status.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import api_client as _api
import config as _cfg
import state as _state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kill_process(pid: int) -> None:
    if pid <= 0:
        return
    try:
        # Kill the entire process group to ensure child frpc dies too
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(0.5)
        if _state.is_pid_alive(pid):
            os.killpg(pgid, signal.SIGKILL)
    except OSError:
        pass


def _stop_tunnel(name: str, tunnel: dict) -> None:
    """Stops the given tunnel processes and releases it from the server."""
    pid = int(tunnel.get("pid", 0) or 0)
    if _state.is_pid_alive(pid):
        _kill_process(pid)
    
    tunnel_id = tunnel.get("tunnel_id")
    if tunnel_id:
        _api.release_tunnel(tunnel_id)
        
    _state.update_tunnel(name, status="stopped", pid=0)


def _spawn_worker(name: str) -> None:
    """Spawn the worker process in the background."""
    worker_script = Path(__file__).resolve().parent / "worker.py"
    
    proc = subprocess.Popen(
        [sys.executable, str(worker_script), name],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # Detach completely
    )
    
    _state.update_tunnel(name, pid=proc.pid)
    
    # Wait briefly for worker to either fail or succeed
    time.sleep(1.0)
    
    t = _state.get_tunnel(name)
    if t and t.get("status") == "failed":
        print(f"\n  ✗ Tunnel failed to start: {t.get('error', 'Unknown error')}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list() -> None:
    tunnels = _state.list_tunnels()
    
    print("\n  PORTX TUNNELS\n")
    if not tunnels:
        print("  No tunnels found.")
        print()
        return

    # Formatting columns
    print(f"  {'NAME':<15} {'TYPE':<6} {'LOCAL':<20} {'PUBLIC':<40} {'STATUS':<10}")
    print("  " + "-" * 95)
    
    for name, t in tunnels.items():
        t_type = t.get("type", "???").upper()
        local = f"{t.get('local_host', '')}:{t.get('local_port', '')}"
        public = t.get("public_url", "")
        status = t.get("status", "unknown").upper()
        
        print(f"  {name[:14]:<15} {t_type[:5]:<6} {local[:19]:<20} {public[:39]:<40} {status[:9]:<10}")
    
    print()


def cmd_info(name: str) -> None:
    t = _state.get_tunnel(name)
    if not t:
        print(f"\n  ✗ Tunnel '{name}' not found.\n")
        sys.exit(1)
        
    print()
    print(f"  Name:    {name}")
    print(f"  ID:      {t.get('tunnel_id', 'N/A')}")
    print(f"  Type:    {t.get('type', 'N/A').upper()}")
    print(f"  Local:   {t.get('local_host')}:{t.get('local_port')}")
    print(f"  Public:  {t.get('public_url', 'N/A')}")
    print(f"  Status:  {t.get('status', 'unknown').upper()}")
    print(f"  PID:     {t.get('pid', 'N/A')}")
    print(f"  Config:  {t.get('frp_config_path', 'N/A')}")
    print(f"  Log:     {t.get('log_path', 'N/A')}")
    print()


def cmd_stop(name: str) -> None:
    tunnels = _state.list_tunnels()
    if name not in tunnels:
        print(f"\n  ✗ Tunnel '{name}' not found.\n")
        sys.exit(1)
        
    _stop_tunnel(name, tunnels[name])
    print(f"\n  ✓ Tunnel '{name}' stopped.\n")


def cmd_stop_all() -> None:
    tunnels = _state.list_tunnels()
    if not tunnels:
        print("\n  ✓ No active tunnels to stop.\n")
        return
        
    for name, t in list(tunnels.items()):
        _stop_tunnel(name, t)
        
    print("\n  ✓ All tunnels stopped.\n")


def cmd_remove(name: str) -> None:
    t = _state.get_tunnel(name)
    if not t:
        print(f"\n  ✗ Tunnel '{name}' not found.\n")
        sys.exit(1)
        
    _stop_tunnel(name, t)
    
    # Clean up files
    frp_path = t.get("frp_config_path")
    if frp_path and Path(frp_path).exists():
        Path(frp_path).unlink()
        
    log_path = t.get("log_path")
    if log_path and Path(log_path).exists():
        Path(log_path).unlink()
        
    _state.remove_tunnel(name)
    print(f"\n  ✓ Tunnel '{name}' removed permanently.\n")


def cmd_remove_all() -> None:
    tunnels = _state.list_tunnels()
    if not tunnels:
        print("\n  ✓ No active tunnels to remove.\n")
        return
        
    for name in list(tunnels.keys()):
        cmd_remove(name)
        
    print("\n  ✓ All tunnels removed permanently.\n")


def cmd_restart(name: str) -> None:
    t = _state.get_tunnel(name)
    if not t:
        print(f"\n  ✗ Tunnel '{name}' not found.\n")
        sys.exit(1)
        
    if t.get("status") in ("starting", "running"):
        _stop_tunnel(name, t)
        
    print(f"\n  → Restarting tunnel '{name}'...")
    
    _state.update_tunnel(name, status="starting")
    _spawn_worker(name)
    
    t = _state.get_tunnel(name)
    print(f"  ✓ Tunnel '{name}' restarted.")
    print(f"  Public: {t.get('public_url')}\n")


def cmd_status() -> None:
    tunnels = _state.list_tunnels()
    
    running = sum(1 for t in tunnels.values() if t.get("status") == "running")
    stopped = sum(1 for t in tunnels.values() if t.get("status") in ("stopped", "failed"))
    
    print("\n  PortX v2.0\n")
    
    # Check server
    server_status = "Connected"
    try:
        import urllib.request
        req = urllib.request.Request(f"{_cfg.PORTX_API_URL}/health")
        with urllib.request.urlopen(req, timeout=3) as r:
            pass
    except Exception:
        server_status = "Unreachable"
        
    print(f"  Server:    {server_status}")
    print(f"  Tunnels:   {running} running")
    print(f"  Stopped:   {stopped}")
    print()
