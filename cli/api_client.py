"""
PortX API client.
Communicates with the PortX coordination server to allocate and release tunnels.

API contract:

  POST /api/v1/tunnel
    Body:    {"type": "http"|"tcp"|"udp", "local_host": str, "local_port": int}
    200 OK:  {
               "tunnel_id": str,
               "type": str,

               -- HTTP only --
               "subdomain": str,
               "public_url": str,               e.g. "https://x7k29m.portx.infinitynoob.lol"

               -- TCP/UDP only --
               "remote_port": int,
               "public_host": str,              e.g. "tcp.portx.infinitynoob.lol"
               "public_url":  str,              e.g. "tcp.portx.infinitynoob.lol:30125"

               -- always present --
               "frps_host": str,
               "frps_port": int,
               "proxy_name": str,
             }

  DELETE /api/v1/tunnel/<tunnel_id>
    204 No Content
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

# Import config from same directory (sys.path is set by portx.py entrypoint)
import config as _cfg


class APIError(Exception):
    """Raised when the PortX server returns an error or is unreachable."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _request(method: str, path: str, body: dict | None = None) -> dict | None:
    url = f"{_cfg.PORTX_API_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None

    headers: dict[str, str] = {"User-Agent": "PortX-Client/2.0"}
    if data:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=_cfg.API_TIMEOUT) as resp:
            raw = resp.read()
            if raw:
                return json.loads(raw.decode())
            return None
    except urllib.error.HTTPError as exc:
        try:
            err_body = json.loads(exc.read().decode())
            msg = err_body.get("error", str(exc))
        except Exception:
            msg = f"HTTP {exc.code} {exc.reason}"
        raise APIError(f"PortX server error: {msg}")
    except urllib.error.URLError as exc:
        raise APIError(
            f"Cannot reach PortX server at {_cfg.PORTX_API_URL}\n"
            f"  Reason: {exc.reason}\n"
            "  Check your internet connection and try again."
        )
    except Exception as exc:
        raise APIError(f"Unexpected API error: {exc}")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def request_tunnel(tunnel_type: str, local_host: str, local_port: int) -> dict:
    """
    Ask the PortX server to allocate a tunnel.
    Returns the server's response dict (see module docstring for shape).
    Raises APIError on failure.
    """
    result = _request("POST", "/api/v1/tunnel", {
        "type":       tunnel_type,
        "local_host": local_host,
        "local_port": local_port,
    })
    if not result:
        raise APIError("Server returned an empty response to tunnel request.")
    return result


def release_tunnel(tunnel_id: str) -> None:
    """
    Notify the server that a tunnel has been closed.
    Best-effort: errors are silently ignored so cleanup never blocks exit.
    """
    try:
        _request("DELETE", f"/api/v1/tunnel/{tunnel_id}")
    except Exception:
        pass
