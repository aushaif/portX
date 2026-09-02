"""
PortX state management.
Handles reading/writing the persistent tunnels.toml database.
Includes a lightweight zero-dependency TOML parser for flat dictionaries.

File locking:
  • tunnels.toml writes use fcntl.flock for multi-process safety.
  • Per-tunnel worker locks in ~/.portx/locks/<name>.lock guarantee
    only one worker/frpc process runs per tunnel at any time.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import time
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────
PORTX_DIR    = Path.home() / ".portx"
TUNNELS_TOML = PORTX_DIR / "tunnels.toml"
CONFIGS_DIR  = PORTX_DIR / "tunnels"
LOGS_DIR     = PORTX_DIR / "logs"
LOCKS_DIR    = PORTX_DIR / "locks"

# Ensure directories exist
for d in (PORTX_DIR, CONFIGS_DIR, LOGS_DIR, LOCKS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Ensure tunnels.toml exists
if not TUNNELS_TOML.exists():
    TUNNELS_TOML.write_text("", "utf-8")


# ── File Locking ─────────────────────────────────────────────────────────

_LOCK_PATH = PORTX_DIR / ".tunnels.lock"


@contextlib.contextmanager
def _lock():
    """
    Exclusive advisory lock protecting tunnels.toml.
    All callers that modify the state file must acquire this lock first.
    Uses fcntl.flock (POSIX — Linux and macOS).
    """
    _LOCK_PATH.touch(exist_ok=True)
    with open(_LOCK_PATH, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


# ── Lightweight TOML Parser ───────────────────────────────────────────────

def _dumps_toml(tunnels: dict[str, dict]) -> str:
    """Format a dict of flat dicts into TOML."""
    lines = []
    for name, data in tunnels.items():
        lines.append(f"[{name}]")
        for k, v in data.items():
            if isinstance(v, str):
                escaped = v.replace('\\', '\\\\').replace('"', '\\"')
                lines.append(f'{k} = "{escaped}"')
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            elif v is None:
                lines.append(f'{k} = ""')
        lines.append("")
    return "\n".join(lines)


def _loads_toml(text: str) -> dict[str, dict]:
    """Parse flat TOML into a dict of dicts."""
    tunnels: dict[str, dict] = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            tunnels[current] = {}
        elif "=" in line and current is not None:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if v.startswith('"') and v.endswith('"'):
                tunnels[current][k] = v[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            elif "." in v:
                try:
                    tunnels[current][k] = float(v)
                except ValueError:
                    tunnels[current][k] = v
            else:
                try:
                    tunnels[current][k] = int(v)
                except ValueError:
                    tunnels[current][k] = v
    return tunnels


# ── Raw I/O (no lock — callers must hold lock) ────────────────────────────

def _read_tunnels_raw() -> dict[str, dict]:
    """Read tunnels.toml without acquiring the lock."""
    if not TUNNELS_TOML.exists():
        return {}
    try:
        return _loads_toml(TUNNELS_TOML.read_text("utf-8"))
    except Exception:
        return {}


def _write_tunnels_raw(tunnels: dict[str, dict]) -> None:
    """Write tunnels.toml atomically without acquiring the lock."""
    tmp = TUNNELS_TOML.with_suffix(".toml.tmp")
    tmp.write_text(_dumps_toml(tunnels), "utf-8")
    tmp.replace(TUNNELS_TOML)  # atomic on POSIX


# ── State Management ──────────────────────────────────────────────────────

def load_tunnels() -> dict[str, dict]:
    """Load and return all tunnels from the state file (no lock needed for read)."""
    if not TUNNELS_TOML.exists():
        return {}
    try:
        return _loads_toml(TUNNELS_TOML.read_text("utf-8"))
    except Exception:
        return {}


def save_tunnels(tunnels: dict[str, dict]) -> None:
    """Save all tunnels to the state file (acquires lock)."""
    with _lock():
        _write_tunnels_raw(tunnels)


def is_pid_alive(pid: int) -> bool:
    """Check if a process is still running."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_tunnel(name: str) -> dict | None:
    """Get a single tunnel, updating its liveness status if needed."""
    tunnels = load_tunnels()
    if name not in tunnels:
        return None

    t = tunnels[name]
    # If the tunnel thinks it's running but the worker PID is dead, mark stopped
    if t.get("status") in ("starting", "running", "reconnecting"):
        pid = t.get("pid", 0)
        if not is_pid_alive(int(pid) if pid else 0):
            # Only update to stopped if not already reconnecting via new worker
            t["status"] = "stopped"
            with _lock():
                current = _read_tunnels_raw()
                if name in current:
                    current[name]["status"] = "stopped"
                    current[name]["pid"] = 0
                    _write_tunnels_raw(current)

    return t


def list_tunnels() -> dict[str, dict]:
    """Return all tunnels, updating liveness statuses first."""
    tunnels = load_tunnels()
    changed = False

    for name, t in tunnels.items():
        if t.get("status") in ("starting", "running", "reconnecting"):
            pid = t.get("pid", 0)
            if not is_pid_alive(int(pid) if pid else 0):
                t["status"] = "stopped"
                t["pid"] = 0
                changed = True

    if changed:
        with _lock():
            # Re-read and merge to avoid overwriting concurrent changes
            current = _read_tunnels_raw()
            for name, t in tunnels.items():
                if name in current and t.get("status") == "stopped":
                    if current[name].get("status") in ("starting", "running", "reconnecting"):
                        pid = current[name].get("pid", 0)
                        if not is_pid_alive(int(pid) if pid else 0):
                            current[name]["status"] = "stopped"
                            current[name]["pid"] = 0
            _write_tunnels_raw(current)
            return current

    return tunnels


def update_tunnel(name: str, **kwargs) -> None:
    """Create or update a tunnel record atomically."""
    with _lock():
        tunnels = _read_tunnels_raw()
        if name not in tunnels:
            tunnels[name] = {"creation_time": time.time()}
        tunnels[name].update(kwargs)
        _write_tunnels_raw(tunnels)


def remove_tunnel(name: str) -> None:
    """Remove a tunnel record atomically."""
    with _lock():
        tunnels = _read_tunnels_raw()
        if name in tunnels:
            del tunnels[name]
            _write_tunnels_raw(tunnels)


# ── Per-tunnel Worker Locks ───────────────────────────────────────────────
# Each worker acquires an exclusive flock on ~/.portx/locks/<name>.lock.
# This is the authoritative single-worker guarantee — PID checks in
# tunnels.toml are supplementary; the flock is the definitive source.

def acquire_worker_lock(name: str):
    """
    Try to acquire an exclusive per-tunnel worker lock.

    Returns an open file object on success (the caller MUST keep it alive
    for the duration of the worker process — closing it releases the lock).
    Returns None if another worker already holds the lock.
    """
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCKS_DIR / f"{name}.lock"
    fd = open(lock_path, "w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(f"{os.getpid()}\n")
        fd.flush()
        return fd
    except (BlockingIOError, OSError):
        fd.close()
        return None


def is_worker_locked(name: str) -> bool:
    """
    Return True if a worker currently holds the exclusive lock for `name`.
    Uses a non-blocking lock attempt — does NOT acquire the lock.
    """
    lock_path = LOCKS_DIR / f"{name}.lock"
    if not lock_path.exists():
        return False
    try:
        with open(lock_path, "w") as fd:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Acquired → no worker running
            return False
    except (BlockingIOError, OSError):
        # Could not acquire → a worker is alive
        return True
