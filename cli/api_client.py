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

  GET /api/v1/tunnel/<tunnel_id>
    200:  tunnel info dict
    404:  {"error": "not found"}

  PUT /api/v1/tunnel/<tunnel_id>/heartbeat
    200:  {"status": "ok"}
    404:  {"error": "not found"}  ← client should reregister

  POST /api/v1/tunnel/<tunnel_id>/reregister
    Body:  {same fields as original allocation}
    200:  tunnel info (same as POST /api/v1/tunnel)
    409:  {"error": "...conflict..."}
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import config as _cfg


class APIError(Exception):
    """Raised when the PortX server returns an error or is unreachable."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _request(method: str, path: str, body: dict | None = None) -> dict | None:
    api_url = _cfg.get_api_url()
    url = f"{api_url}{path}"
    data = json.dumps(body).encode() if body is not None else None

    token = _cfg.get_auth_token()
    headers: dict[str, str] = {
        "User-Agent":    "PortX-Client/2.1",
        "Authorization": f"Bearer {token}",
    }
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
        raise APIError(f"PortX server error ({exc.code}): {msg}")
    except urllib.error.URLError as exc:
        raise APIError(
            f"Cannot reach PortX server at {api_url}\n"
            f"  Reason: {exc.reason}\n"
            "  Check your internet connection and try again."
        )
    except Exception as exc:
        raise APIError(f"Unexpected API error: {exc}")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def request_tunnel(
    tunnel_type: str,
    local_host: str,
    local_port: int,
    subdomain: str | None = None,
) -> dict:
    """
    Ask the PortX server to allocate a new tunnel.
    Returns the server's response dict (see module docstring for shape).
    Raises APIError on failure.
    """
    body: dict = {
        "type":       tunnel_type,
        "local_host": local_host,
        "local_port": local_port,
    }
    if subdomain:
        body["subdomain"] = subdomain

    result = _request("POST", "/api/v1/tunnel", body)
    if not result:
        raise APIError("Server returned an empty response to tunnel request.")
    return result


def release_tunnel(tunnel_id: str) -> None:
    """
    Notify the server that a tunnel has been permanently closed.
    Best-effort: errors are silently ignored so cleanup never blocks exit.
    """
    try:
        _request("DELETE", f"/api/v1/tunnel/{tunnel_id}")
    except Exception:
        pass


def heartbeat(tunnel_id: str) -> bool:
    """
    Renew the server's record of this tunnel's liveness.
    Returns True on success, False if the server no longer knows this tunnel.
    Does NOT raise APIError — heartbeat failures are non-fatal.
    """
    try:
        result = _request("PUT", f"/api/v1/tunnel/{tunnel_id}/heartbeat")
        return True
    except APIError as exc:
        # 404 means server lost our record — caller should reregister
        if "404" in str(exc) or "not found" in str(exc).lower():
            return False
        return True  # other errors (network) → assume still alive, try later
    except Exception:
        return True


def reregister_tunnel(tunnel_id: str, tunnel_info: dict) -> dict:
    """
    Ask the server to reclaim an existing tunnel allocation.
    The server will either return the same allocation info (if the tunnel_id
    is still known) or attempt to re-create it with the same subdomain/port.

    Returns the allocation info dict on success.
    Raises APIError on failure (e.g., 409 conflict, 400 bad request).
    """
    result = _request("POST", f"/api/v1/tunnel/{tunnel_id}/reregister", tunnel_info)
    if not result:
        raise APIError("Server returned empty response to reregister request.")
    return result
