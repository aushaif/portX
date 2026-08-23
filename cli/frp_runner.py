"""
FRP client process manager.

Starts frpc with a generated TOML config file, monitors its output for a
successful connection, and provides a clean shutdown.
"""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path


class FRPError(Exception):
    """Raised when frpc fails to start or exits unexpectedly."""


# ── Log-line classifiers ──────────────────────────────────────────────────
_SUCCESS_MARKERS = (
    "start proxy success",
    "login to server success",
)

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
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    # Shared state between the watcher thread and this thread
    _ready    = threading.Event()
    _failed   = threading.Event()
    _fail_msg: list[str] = []
    _all_lines: list[str] = []

    def _watch() -> None:
        """Read frpc output lines and signal success / failure events."""
        for raw_line in proc.stdout:  # type: ignore[union-attr]
            line = raw_line.rstrip()
            _all_lines.append(line)
            lower = line.lower()

            if any(m in lower for m in _SUCCESS_MARKERS):
                _ready.set()

            if any(m in lower for m in _FAILURE_MARKERS):
                _fail_msg.append(line)
                _failed.set()
                _ready.set()   # unblock the wait below

        # stdout EOF — process has ended
        _ready.set()

    watcher = threading.Thread(target=_watch, daemon=True)
    watcher.start()

    _ready.wait(timeout=timeout)

    # ── Process already exited ─────────────────────────────────────────────
    if proc.poll() is not None:
        tail = "\n    ".join(_all_lines[-8:]) or "frpc produced no output."
        raise FRPError(
            "frpc exited unexpectedly during startup.\n"
            f"    {tail}"
        )

    # ── Explicit failure marker detected ──────────────────────────────────
    if _failed.is_set():
        stop_frpc(proc)
        msg = _fail_msg[0] if _fail_msg else "frpc reported a connection error."
        raise FRPError(f"Tunnel connection failed: {msg}")

    # ── Timeout reached but process is still running → assume success ──────
    # (frpc on newer versions may not print a per-proxy "success" line)
    return proc


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
