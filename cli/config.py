"""
PortX client configuration.

Resolution priority for every setting:
  1. ~/.portx/config.toml            (user override — set via `portx config set`)
  2. Environment variables           (PORTX_FRPS_HOST, PORTX_API_URL, …)
  3. portx.config.json               (project-level defaults next to this file)
  4. Built-in hardcoded constants    (failsafe if nothing else is found)

On first use, if no auth token is found the user is prompted interactively.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


# ── Runtime directories ────────────────────────────────────────────────────
PORTX_DIR   = Path.home() / ".portx"
CONFIG_TOML = PORTX_DIR / "config.toml"

# ── Locate portx.config.json (project-level central config) ───────────────
def _find_project_config() -> Path | None:
    """Walk up from this file to find portx.config.json."""
    here = Path(__file__).resolve().parent
    for candidate in [here, here.parent]:
        p = candidate / "portx.config.json"
        if p.exists():
            return p
    # Also check ~/.portx/ (installed copy)
    installed = PORTX_DIR / "portx.config.json"
    if installed.exists():
        return installed
    return None


def _load_project_config() -> dict:
    """Load portx.config.json, return empty dict if not found."""
    path = _find_project_config()
    if path is None:
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception:
        return {}


_PROJECT_CFG: dict = _load_project_config()


def _proj(section: str, key: str, fallback: object) -> object:
    """Read a value from portx.config.json with a built-in fallback."""
    return _PROJECT_CFG.get(section, {}).get(key, fallback)


# ── Local FRP binary ──────────────────────────────────────────────────────
FRP_BINARY: Path = Path(
    os.environ.get("PORTX_FRP_BINARY", str(PORTX_DIR / "bin" / "frpc"))
)
if not FRP_BINARY.exists():
    _fallback = Path(__file__).resolve().parent.parent / "bin" / "frpc"
    if _fallback.exists():
        FRP_BINARY = _fallback


# ── Timeouts (from project config or env, not user-overridable per-session) ─
API_TIMEOUT: int          = int(os.environ.get("PORTX_API_TIMEOUT",
    str(_proj("timeouts", "api_timeout", 15))))
FRPC_CONNECT_TIMEOUT: int = int(os.environ.get("PORTX_FRPC_TIMEOUT",
    str(_proj("timeouts", "frpc_connect_timeout", 15))))


# ---------------------------------------------------------------------------
# Minimal TOML helpers (flat [section] only)
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


def _get(section: str, key: str, env_var: str | None, proj_section: str, proj_key: str, default: str) -> str:
    """
    Unified getter with priority chain:
      ~/.portx/config.toml → env var → portx.config.json → hardcoded default
    """
    # 1. User config file
    cfg = _load_config()
    val = cfg.get(section, {}).get(key, "").strip()
    if val:
        return val
    # 2. Environment variable
    if env_var:
        val = os.environ.get(env_var, "").strip()
        if val:
            return val
    # 3. portx.config.json
    val = str(_proj(proj_section, proj_key, "")).strip()
    if val:
        return val
    # 4. Built-in default
    return default


def _set(section: str, key: str, value: str) -> None:
    """Write key into ~/.portx/config.toml under [section]."""
    cfg = _load_config()
    cfg.setdefault(section, {})
    cfg[section][key] = value
    _save_config(cfg)


def _unset(section: str, key: str) -> None:
    """Remove key from ~/.portx/config.toml if present."""
    cfg = _load_config()
    if section in cfg and key in cfg[section]:
        del cfg[section][key]
        _save_config(cfg)


# ---------------------------------------------------------------------------
# Public getters — connection / domain settings
# ---------------------------------------------------------------------------

def get_frps_host() -> str:
    return _get("portx", "frps_host", "PORTX_FRPS_HOST",
                "server", "frps_host", "server.infinitynoob.lol")

def get_frps_port() -> int:
    return int(_get("portx", "frps_port", "PORTX_FRPS_PORT",
                    "server", "frps_port", "7000"))

def get_api_url() -> str:
    return _get("portx", "api_url", "PORTX_API_URL",
                "server", "api_url", "http://server.infinitynoob.lol:8765")

def get_http_domain() -> str:
    return _get("portx", "http_domain", "PORTX_HTTP_DOMAIN",
                "domains", "http", "infinitynoob.lol")

def get_tcp_domain() -> str:
    return _get("portx", "tcp_domain", "PORTX_TCP_DOMAIN",
                "domains", "tcp", "tcp.portx.infinitynoob.lol")

def get_udp_domain() -> str:
    return _get("portx", "udp_domain", "PORTX_UDP_DOMAIN",
                "domains", "udp", "udp.portx.infinitynoob.lol")

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
    api_url = get_api_url()
    host = api_url.split("//")[-1].split(":")[0]
    print(f"  You can find your token at: https://{host}/dashboard")
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
        cfg["portx"]["api_url"] = get_api_url()
    _save_config(cfg)

    print()
    print(f"  ✓ Auth token saved to {CONFIG_TOML}")
    print()
    return token


# ---------------------------------------------------------------------------
# Public setters
# ---------------------------------------------------------------------------

def set_auth_token(token: str) -> None:
    """Set or replace the auth token in ~/.portx/config.toml."""
    _set("portx", "auth_token", token)

def set_api_url(url: str) -> None:
    _set("portx", "api_url", url)

def set_frps_host(host: str) -> None:
    _set("portx", "frps_host", host)

def set_frps_port(port: int) -> None:
    _set("portx", "frps_port", str(port))

def set_http_domain(domain: str) -> None:
    _set("portx", "http_domain", domain)

def set_tcp_domain(domain: str) -> None:
    _set("portx", "tcp_domain", domain)

def set_udp_domain(domain: str) -> None:
    _set("portx", "udp_domain", domain)


# ---------------------------------------------------------------------------
# Backward-compatible module-level aliases (used by legacy callers)
# ---------------------------------------------------------------------------
# These are resolved once at import time; tunnels started in the same
# process will see the values that were active at startup.
# For dynamic use (e.g. after `portx config set`), call the getter functions.

FRPS_HOST: str            = get_frps_host()
FRPS_PORT: int            = get_frps_port()
HTTP_TUNNEL_DOMAIN: str   = get_http_domain()
TCP_TUNNEL_DOMAIN: str    = get_tcp_domain()
UDP_TUNNEL_DOMAIN: str    = get_udp_domain()


# ---------------------------------------------------------------------------
# Aggregate helpers
# ---------------------------------------------------------------------------

# Keys the user can customise via `portx config set`
CONFIG_KEYS: dict[str, tuple[str, str]] = {
    "frps_host":   ("Server hostname for the FRP relay (frps)", "portx"),
    "frps_port":   ("TCP port frps listens on (default 7000)",   "portx"),
    "api_url":     ("PortX coordination API URL",                "portx"),
    "http_domain": ("Wildcard domain for HTTP tunnels",          "portx"),
    "tcp_domain":  ("Hostname for TCP tunnels",                  "portx"),
    "udp_domain":  ("Hostname for UDP tunnels",                  "portx"),
    "auth_token":  ("Your PortX authentication token",           "portx"),
}

_SETTERS: dict[str, object] = {
    "frps_host":   set_frps_host,
    "frps_port":   lambda v: set_frps_port(int(v)),
    "api_url":     set_api_url,
    "http_domain": set_http_domain,
    "tcp_domain":  set_tcp_domain,
    "udp_domain":  set_udp_domain,
    "auth_token":  set_auth_token,
}

_GETTERS: dict[str, object] = {
    "frps_host":   get_frps_host,
    "frps_port":   lambda: str(get_frps_port()),
    "api_url":     get_api_url,
    "http_domain": get_http_domain,
    "tcp_domain":  get_tcp_domain,
    "udp_domain":  get_udp_domain,
    "auth_token":  lambda: (lambda t: t[:6] + "*" * max(0, len(t)-6) if t else "(not set)")(
        _load_config().get("portx", {}).get("auth_token", "")),
}


def get_all_config() -> dict[str, str]:
    """Return current effective values for all user-configurable keys."""
    return {k: _GETTERS[k]() for k in CONFIG_KEYS}   # type: ignore[operator]


def set_config_key(key: str, value: str) -> None:
    """Set any of the user-configurable keys by name."""
    if key not in _SETTERS:
        raise KeyError(f"Unknown config key: {key!r}. Valid keys: {list(CONFIG_KEYS)}")
    _SETTERS[key](value)   # type: ignore[operator]


def reset_config() -> None:
    """Remove all user overrides from ~/.portx/config.toml (keeps auth token)."""
    cfg = _load_config()
    portx_section = cfg.get("portx", {})
    # Keep only auth_token — everything else is reset to project defaults
    token = portx_section.get("auth_token", "")
    cfg["portx"] = {}
    if token:
        cfg["portx"]["auth_token"] = token
    _save_config(cfg)
