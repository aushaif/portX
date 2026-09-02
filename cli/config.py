"""
PortX client configuration.

All runtime settings (API URL, auth token) are stored in ~/.portx/config.toml
and read from there — never hardcoded.

On first use, if the config file doesn't exist or has no auth token, the user
is prompted interactively to enter their PortX auth token.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────
PORTX_DIR   = Path.home() / ".portx"
CONFIG_TOML = PORTX_DIR / "config.toml"

# ── FRP server (frps) — infrastructure constants, not user-configurable ───
FRPS_HOST: str = os.environ.get("PORTX_FRPS_HOST", "portx.infinitynoob.lol")
FRPS_PORT: int = int(os.environ.get("PORTX_FRPS_PORT", "7000"))
FRPS_TOKEN: str = os.environ.get("PORTX_FRPS_TOKEN", "k3rnel-p4nic")

# ── Public DNS ────────────────────────────────────────────────────────────
HTTP_TUNNEL_DOMAIN: str = os.environ.get("PORTX_HTTP_DOMAIN", "infinitynoob.lol")
TCP_TUNNEL_DOMAIN: str  = os.environ.get("PORTX_TCP_DOMAIN",  "tcp.portx.infinitynoob.lol")
UDP_TUNNEL_DOMAIN: str  = os.environ.get("PORTX_UDP_DOMAIN",  "udp.portx.infinitynoob.lol")

# ── Local FRP binary ──────────────────────────────────────────────────────
FRP_BINARY: Path = Path(
    os.environ.get("PORTX_FRP_BINARY", str(PORTX_DIR / "bin" / "frpc"))
)
if not FRP_BINARY.exists():
    _fallback = Path(__file__).resolve().parent.parent / "bin" / "frpc"
    if _fallback.exists():
        FRP_BINARY = _fallback

# ── Timeouts ──────────────────────────────────────────────────────────────
API_TIMEOUT: int          = 15
FRPC_CONNECT_TIMEOUT: int = 15

# ── Defaults ──────────────────────────────────────────────────────────────
_DEFAULT_API_URL = "http://portx.infinitynoob.lol:8765"


# ---------------------------------------------------------------------------
# Minimal TOML helpers (flat [section] only, same style as state.py)
# ---------------------------------------------------------------------------

def _toml_loads(text: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            result.setdefault(section, {})
        elif "=" in line and section is not None:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if v.startswith('"') and v.endswith('"'):
                result[section][k] = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            else:
                result[section][k] = v
    return result


def _toml_dumps(data: dict[str, dict]) -> str:
    lines: list[str] = []
    for section, kv in data.items():
        lines.append(f"[{section}]")
        for k, v in kv.items():
            escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{escaped}"')
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

def _load_config() -> dict[str, dict]:
    """Load ~/.portx/config.toml, returning parsed dict."""
    PORTX_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_TOML.exists():
        return {}
    try:
        return _toml_loads(CONFIG_TOML.read_text("utf-8"))
    except Exception:
        return {}


def _save_config(data: dict[str, dict]) -> None:
    """Write data back to ~/.portx/config.toml."""
    PORTX_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_TOML.write_text(_toml_dumps(data), "utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_api_url() -> str:
    """Return the configured PortX API URL (falls back to default)."""
    cfg = _load_config()
    return cfg.get("portx", {}).get("api_url", _DEFAULT_API_URL)


def get_auth_token() -> str:
    """
    Return the configured auth token.
    If no token exists, prompt the user interactively and persist it.
    """
    cfg = _load_config()
    token = cfg.get("portx", {}).get("auth_token", "").strip()
    if token:
        return token

    # First use — prompt the user
    print()
    print("  PortX — First Time Setup")
    print("  ─────────────────────────────────────────")
    print()
    print("  No auth token found. Please enter your PortX auth token.")
    print("  You can find your token at: https://portx.infinitynoob.lol/dashboard")
    print()

    while True:
        try:
            token = input("  Auth token: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            sys.exit(0)

        if token:
            break
        print("  ✗ Token cannot be empty. Please try again.")

    # Persist
    cfg.setdefault("portx", {})
    cfg["portx"]["auth_token"] = token
    if "api_url" not in cfg["portx"]:
        cfg["portx"]["api_url"] = _DEFAULT_API_URL
    _save_config(cfg)

    print()
    print(f"  ✓ Auth token saved to {CONFIG_TOML}")
    print()
    return token


def set_auth_token(token: str) -> None:
    """Set or replace the auth token in ~/.portx/config.toml."""
    cfg = _load_config()
    cfg.setdefault("portx", {})
    if "api_url" not in cfg["portx"]:
        cfg["portx"]["api_url"] = _DEFAULT_API_URL
    cfg["portx"]["auth_token"] = token
    _save_config(cfg)


def set_api_url(url: str) -> None:
    """Set or replace the API URL in ~/.portx/config.toml."""
    cfg = _load_config()
    cfg.setdefault("portx", {})
    cfg["portx"]["api_url"] = url
    _save_config(cfg)
