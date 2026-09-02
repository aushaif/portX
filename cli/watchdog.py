"""
PortX Watchdog — boot-time tunnel auto-start daemon.

Spawned at login/boot via a macOS LaunchAgent or Linux systemd --user service.

Responsibilities:
  - On startup: find all tunnels marked auto_start=1 and ensure their
    worker processes are alive.
  - Every 30 seconds: re-check liveness and restart any dead workers.
  - Log all actions to ~/.portx/logs/watchdog.log.

The watchdog respects admin_stopped=1: tunnels explicitly stopped by the
user via 'portx stop' will not be auto-restarted.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Add cli dir to sys.path
_CLI_DIR = Path(__file__).resolve().parent
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

import state as _state

# ── Configuration ─────────────────────────────────────────────────────────
_CHECK_INTERVAL  = 30   # seconds between liveness checks
_STARTUP_DELAY   = 8    # seconds to wait after boot before first check
_LOG_FILE        = _state.PORTX_DIR / "logs" / "watchdog.log"

# ── Globals ───────────────────────────────────────────────────────────────
_running = True
_log_fd  = None


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str) -> None:
    entry = f"[{_ts()}] WATCHDOG  {msg}\n"
    if _log_fd:
        try:
            _log_fd.write(entry)
            _log_fd.flush()
        except Exception:
            pass


def _shutdown(signum=None, frame=None) -> None:
    global _running
    _log(f"Received signal {signum}, shutting down")
    _running = False
    sys.exit(0)


def _spawn_worker(name: str) -> None:
    """Start a background worker process for the given tunnel name."""
    worker_script = _CLI_DIR / "worker.py"
    try:
        proc = subprocess.Popen(
            [sys.executable, str(worker_script), name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        _state.update_tunnel(name, pid=proc.pid, status="starting")
        _log(f"Spawned worker for '{name}' (PID={proc.pid})")
    except Exception as exc:
        _log(f"Failed to spawn worker for '{name}': {exc}")


def _check_and_restore() -> None:
    """Inspect all tunnels and restart any that should be running but aren't."""
    tunnels = _state.load_tunnels()
    for name, t in tunnels.items():
        # Only manage tunnels that are opted into auto-start
        if not t.get("auto_start"):
            continue

        # Don't restart tunnels that were deliberately stopped by the user
        if t.get("admin_stopped"):
            continue

        status = t.get("status", "unknown")
        pid    = int(t.get("pid", 0) or 0)

        # Tunnel is healthy — worker process is alive (checked via fcntl lock)
        if _state.is_worker_locked(name):
            continue

        _log(
            f"Tunnel '{name}' needs recovery "
            f"(status={status}, pid={pid}, locked=False)"
        )
        _spawn_worker(name)


def main() -> None:
    global _log_fd

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Ensure log directory exists
    _state.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _log_fd = open(_LOG_FILE, "a", buffering=1)
    sys.stdout = _log_fd
    sys.stderr = _log_fd

    _log(f"PortX watchdog started (PID={os.getpid()})")

    # Wait for the system to settle after boot (network may not be ready yet)
    _log(f"Waiting {_STARTUP_DELAY}s for system to settle...")
    time.sleep(_STARTUP_DELAY)

    while _running:
        try:
            _check_and_restore()
        except Exception as exc:
            _log(f"Error during health check: {exc}")

        # Sleep in small increments so we can respond to signals promptly
        for _ in range(_CHECK_INTERVAL):
            if not _running:
                break
            time.sleep(1)

    _log("PortX watchdog stopped")


if __name__ == "__main__":
    main()
