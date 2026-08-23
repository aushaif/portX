"""
Local address parser.

Normalises user-supplied local address strings into (host, port) tuples.

Accepted formats:
  "8080"              → ("127.0.0.1", 8080)
  "127.0.0.1:8080"   → ("127.0.0.1", 8080)
  "localhost:3000"    → ("127.0.0.1", 3000)
  "0.0.0.0:8080"     → ("0.0.0.0",   8080)
"""

from __future__ import annotations

_MIN_PORT = 1
_MAX_PORT = 65535


class AddressError(ValueError):
    """Raised when a local address string cannot be parsed or is invalid."""


def parse_local_address(addr: str) -> tuple[str, int]:
    """
    Parse a local address string into (host, port).
    Raises AddressError with a clear message on bad input.
    """
    addr = addr.strip()
    if not addr:
        raise AddressError("Local address cannot be empty.")

    if ":" in addr:
        # Split on the LAST colon to support IPv6 literals in future
        host, _, port_str = addr.rpartition(":")
        host = host.strip()
        if host.lower() == "localhost":
            host = "127.0.0.1"
        if not host:
            raise AddressError(f"Invalid address '{addr}': host part is empty.")
    else:
        # Plain port number
        host = "127.0.0.1"
        port_str = addr

    try:
        port = int(port_str)
    except ValueError:
        raise AddressError(
            f"Invalid port: '{port_str}' — port must be an integer."
        )

    if not (_MIN_PORT <= port <= _MAX_PORT):
        raise AddressError(
            f"Invalid port: {port} — must be between {_MIN_PORT} and {_MAX_PORT}."
        )

    return host, port


def format_local(host: str, port: int) -> str:
    """Human-readable 'host:port' string."""
    return f"{host}:{port}"
