"""
FRP client process manager.

Starts frpc with a generated TOML config file, monitors its output for a
successful connection, and provides a clean shutdown.
"""

from __future__ import annotations

import subprocess
import selectors
import os
import time
from pathlib import Path


class FRPError(Exception):
    """Raised when frpc fails to start or exits unexpectedly."""


# ── Log-line classifiers ──────────────────────────────────────────────────
_FAILURE_MARKERS = (
    "login to server failed",
    "proxy name conflict",
    "port already used",
    "failed to login",
    "no such host",
    "connection refused",
    "i/o timeout",
    "authentication failed",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_frpc(
    config_path: Path,
    frp_binary: Path,
    *,
    timeout: int = 15,
) -> subprocess.Popen:
    """
    Launch frpc with `config_path`.  Block for up to `timeout` seconds while
    watching stdout/stderr for a success or failure signal.

    Returns the running Popen object on success.
    Raises FRPError if frpc exits or emits a failure marker before the timeout.
    """
    if not frp_binary.exists():
        raise FRPError(
            f"FRP binary not found at {frp_binary}\n"
            "  Run the PortX installer first:\n"
            "    python3 installer/portx_install.py"
        )

    proc = subprocess.Popen(
        [str(frp_binary), "-c", str(config_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # One reader owns stdout during startup. Hand it to the worker only after
    # the proxy (not merely the control connection) has been accepted.
    lines = []
    pending = b""
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    try:
        while time.monotonic() < deadline:
            for key, _ in selector.select(max(0, deadline - time.monotonic())):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    raise FRPError("frpc exited during startup: " + "\n".join(lines[-8:]))
                pending += chunk
                while b"\n" in pending:
                    raw, pending = pending.split(b"\n", 1)
                    line = raw.decode("utf-8", errors="replace").rstrip()
                    lines.append(line)
                    lower = line.lower()
                    if any(m in lower for m in _FAILURE_MARKERS) or "start error" in lower:
                        raise FRPError("Tunnel connection failed: " + line)
                    if "start proxy success" in lower:
                        if proc.poll() is not None:
                            raise FRPError("frpc exited immediately after proxy startup")
                        return proc
        raise FRPError("Timed out waiting for proxy startup: " + "\n".join(lines[-8:]))
    except BaseException:
        stop_frpc(proc)
        if proc.stdout:
            proc.stdout.close()
        raise
    finally:
        selector.close()


def stop_frpc(proc: subprocess.Popen) -> None:
    """
    Gracefully terminate frpc.
    Sends SIGTERM; escalates to SIGKILL after 5 seconds if it does not exit.
    """
    if proc.poll() is not None:
        return  # already exited
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
