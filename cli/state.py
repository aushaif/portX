"""
PortX state management.
Handles reading/writing the persistent tunnels.toml database.
Includes a lightweight zero-dependency TOML parser for flat dictionaries.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────
PORTX_DIR = Path.home() / ".portx"
TUNNELS_TOML = PORTX_DIR / "tunnels.toml"
CONFIGS_DIR = PORTX_DIR / "tunnels"
LOGS_DIR = PORTX_DIR / "logs"

# Ensure directories exist
for d in (PORTX_DIR, CONFIGS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Ensure tunnels.toml exists
if not TUNNELS_TOML.exists():
    TUNNELS_TOML.write_text("", "utf-8")


# ── Lightweight TOML Parser ───────────────────────────────────────────────

def _dumps_toml(tunnels: dict[str, dict]) -> str:
    """Format a dict of flat dicts into TOML."""
    lines = []
    for name, data in tunnels.items():
        lines.append(f"[{name}]")
        for k, v in data.items():
            if isinstance(v, str):
                # Escape minimal characters
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


# ── State Management ──────────────────────────────────────────────────────

def load_tunnels() -> dict[str, dict]:
    """Load and return all tunnels from the state file."""
    if not TUNNELS_TOML.exists():
        return {}
    try:
        return _loads_toml(TUNNELS_TOML.read_text("utf-8"))
    except Exception:
        return {}


def save_tunnels(tunnels: dict[str, dict]) -> None:
    """Save all tunnels to the state file."""
    TUNNELS_TOML.write_text(_dumps_toml(tunnels), "utf-8")


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
    if t.get("status") in ("starting", "running"):
        pid = t.get("pid", 0)
        if not is_pid_alive(pid):
            t["status"] = "stopped"
            save_tunnels(tunnels)
    
    return t


def list_tunnels() -> dict[str, dict]:
    """Return all tunnels, updating liveness statuses first."""
    tunnels = load_tunnels()
    changed = False
    for name, t in tunnels.items():
        if t.get("status") in ("starting", "running"):
            pid = t.get("pid", 0)
            if not is_pid_alive(pid):
                t["status"] = "stopped"
                changed = True
    
    if changed:
        save_tunnels(tunnels)
        
    return tunnels


def update_tunnel(name: str, **kwargs) -> None:
    """Create or update a tunnel record."""
    tunnels = load_tunnels()
    if name not in tunnels:
        tunnels[name] = {"creation_time": time.time()}
    
    tunnels[name].update(kwargs)
    save_tunnels(tunnels)


def remove_tunnel(name: str) -> None:
    """Remove a tunnel record."""
    tunnels = load_tunnels()
    if name in tunnels:
        del tunnels[name]
        save_tunnels(tunnels)
