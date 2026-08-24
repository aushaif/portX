"""
Background worker daemon for PortX tunnels.
This script is spawned in a detached session by the main CLI.
It runs frpc, monitors its health, and updates the TOML state.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

# Add cli dir to sys path so we can import modules
_CLI_DIR = Path(__file__).resolve().parent
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

import config as _cfg
import frp_runner as _runner
import state as _state

_proc = None

def _shutdown(signum=None, frame=None):
    """Clean shutdown: kill frpc when the worker itself is killed."""
    global _proc
    if _proc is not None:
        try:
            _proc.terminate()
            time.sleep(0.3)
            if _proc.poll() is None:
                _proc.kill()
        except OSError:
            pass
    sys.exit(0)


def main() -> None:
    global _proc

    if len(sys.argv) < 2:
        sys.exit(1)
        
    tunnel_name = sys.argv[1]
    
    # Register shutdown handler so frpc dies when worker is killed
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # 1. Load the tunnel configuration
    tunnel = _state.get_tunnel(tunnel_name)
    if not tunnel:
        sys.exit(1)
        
    frp_config_path = Path(tunnel["frp_config_path"])
    log_path = Path(tunnel["log_path"])
    
    if not frp_config_path.exists():
        _state.update_tunnel(tunnel_name, status="failed", error="FRP config file missing")
        sys.exit(1)

    # 2. Redirect stdout/stderr to the log file
    log_fd = open(log_path, "a", buffering=1)
    sys.stdout = log_fd
    sys.stderr = log_fd

    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Starting tunnel '{tunnel_name}'...")
    
    # 3. Start frpc
    try:
        _proc = _runner.start_frpc(
            config_path=frp_config_path,
            frp_binary=_cfg.FRP_BINARY,
            timeout=_cfg.FRPC_CONNECT_TIMEOUT,
        )
    except _runner.FRPError as exc:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Tunnel failed to start: {exc}")
        _state.update_tunnel(tunnel_name, status="failed", error=str(exc))
        sys.exit(1)
    
    # 4. Connection successful! Update state with worker PID (os.getpid).
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connected. Worker PID={os.getpid()}, frpc PID={_proc.pid}")
    _state.update_tunnel(tunnel_name, status="running")
    
    # 5. Monitor until exit
    while True:
        ret = _proc.poll()
        if ret is not None:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] frpc exited with code {ret}")
            break
        time.sleep(1)

    # 6. Mark as stopped
    _state.update_tunnel(tunnel_name, status="stopped")


if __name__ == "__main__":
    main()
