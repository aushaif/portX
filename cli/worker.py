"""
Background worker daemon for PortX tunnels.

This script is spawned in a detached session by the main CLI.
It runs frpc, monitors its health, and automatically reconnects
when frpc exits for any reason (server restart, network loss,
power failure, etc.).

Single-worker guarantee
───────────────────────
Each worker acquires an exclusive flock on ~/.portx/locks/<name>.lock
at startup. If the lock is already held, this process exits immediately.
This prevents any possibility of duplicate workers, even across restarts.

Reconnection strategy
─────────────────────
1. If frpc exits: wait backoff, restart frpc with the same TOML config.
   (In most cases frps still knows our proxy — this is all that’s needed.)

2. If frpc can’t start due to a proxy-name conflict or port conflict:
   The server may have lost our allocation (e.g. state.json was deleted).
   → Call POST /api/v1/tunnel/<id>/reregister to reclaim the same URL/port.
   → If reclaimed: regenerate TOML config and retry frpc immediately.
   → If conflict (someone else took our slot): request a brand-new tunnel.

3. Fatal errors on the very first connection attempt (bad auth, unknown host):
   → Mark tunnel as "failed" and exit (no retry). The CLI shows the error.

4. Backoff: starts at 2 s, doubles on each failure, caps at 120 s.
   Resets to 2 s on any successful connection.

Signals
───────
  SIGTERM / SIGINT  →  graceful shutdown (kills frpc, sets status=stopped)
  SIGUSR1           →  graceful reload: kills frpc and restarts it immediately
                        (no backoff). Brief reconnect of ~1-3 s. The same
                        proxy name / subdomain / port is preserved.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
import fcntl
from pathlib import Path

# Add cli dir to sys path so we can import modules
_CLI_DIR = Path(__file__).resolve().parent
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

import api_client as _api
import config as _cfg
import frp_config as _toml
import frp_runner as _runner
import state as _state

# ── Constants ─────────────────────────────────────────────────────────────
_INITIAL_BACKOFF    = 2    # seconds
_MAX_BACKOFF        = 120  # seconds
_HEARTBEAT_INTERVAL = 60   # seconds between heartbeats

# frpc log markers that signal a fatal configuration problem
_FATAL_MARKERS = (
    "authentication failed",
    "no such host",
    "login to server failed",
    "failed to login",
)

# frpc log markers that signal an allocation conflict (reregister needed)
_CONFLICT_MARKERS = (
    "proxy name conflict",
    "port already used",
)

# ── Global state ──────────────────────────────────────────────────────────
_proc:             "subprocess.Popen | None" = None  # noqa: F821
_tunnel_name:      str = ""
_shutdown_flag:    bool = False
_reload_flag:      bool = False
_was_reload:       bool = False   # set to skip backoff after SIGUSR1 reload
_log_fd            = None
_worker_lock_fd    = None     # exclusive flock fd — held for entire lifetime


# ── Logging ───────────────────────────────────────────────────────────────

def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str) -> None:
    if _log_fd:
        try:
            _log_fd.write(f"[{_ts()}] {msg}\n")
            _log_fd.flush()
        except Exception:
            pass


# ── Signal handlers ───────────────────────────────────────────────────────

def _shutdown(signum=None, frame=None) -> None:
    """SIGTERM / SIGINT — kill frpc and exit cleanly."""
    global _shutdown_flag, _proc
    _log(f"Received signal {signum}, shutting down...")
    _shutdown_flag = True
    _kill_frpc()
    # Update state synchronously before exit
    if _tunnel_name:
        try:
            _state.update_tunnel(_tunnel_name, status="stopped", pid=0)
        except Exception:
            pass
    sys.exit(0)


def _reload(signum=None, frame=None) -> None:
    """SIGUSR1 — flag for graceful reload: kill frpc and restart it with no backoff."""
    global _reload_flag
    _log("Received SIGUSR1, flagging for graceful reload (brief reconnect ~1-3s)...")
    _reload_flag = True


def _kill_frpc() -> None:
    global _proc
    if _proc is not None:
        try:
            _proc.terminate()
            time.sleep(0.4)
            if _proc.poll() is None:
                _proc.kill()
        except OSError:
            pass


# ── Heartbeat thread ──────────────────────────────────────────────────────

def _heartbeat_loop(tunnel_id: str, stop_event: threading.Event) -> None:
    """Send periodic heartbeats to keep the server allocation alive."""
    while not stop_event.wait(timeout=_HEARTBEAT_INTERVAL):
        try:
            alive = _api.heartbeat(tunnel_id)
            if not alive:
                # Server no longer knows this tunnel_id — flag for reregister
                _log("Heartbeat returned 404 — server may need reregister on next reconnect")
        except Exception as exc:
            _log(f"Heartbeat error (non-fatal): {exc}")


# ── Config helpers ────────────────────────────────────────────────────────

def _regenerate_config(info: dict) -> None:
    """Rewrite the frpc TOML config file from fresh server allocation info."""
    tunnel = _state.get_tunnel(_tunnel_name)
    if not tunnel:
        return

    t           = tunnel.get("type", "")
    local_host  = tunnel.get("local_host", "127.0.0.1")
    local_port  = int(tunnel.get("local_port", 0))
    config_path = Path(tunnel["frp_config_path"])
    frps_host   = info.get("frps_host", _cfg.FRPS_HOST)
    frps_port   = info.get("frps_port", _cfg.FRPS_PORT)
    proxy_name  = info.get("proxy_name", "")

    if t == "http":
        toml = _toml.generate_http_config(
            local_host=local_host, local_port=local_port,
            subdomain=info.get("subdomain", tunnel.get("subdomain", "")),
            proxy_name=proxy_name, frps_host=frps_host, frps_port=frps_port,
        )
    elif t == "tcp":
        toml = _toml.generate_tcp_config(
            local_host=local_host, local_port=local_port,
            remote_port=int(info.get("remote_port", tunnel.get("remote_port", 0))),
            proxy_name=proxy_name, frps_host=frps_host, frps_port=frps_port,
        )
    else:
        toml = _toml.generate_udp_config(
            local_host=local_host, local_port=local_port,
            remote_port=int(info.get("remote_port", tunnel.get("remote_port", 0))),
            proxy_name=proxy_name, frps_host=frps_host, frps_port=frps_port,
        )

    config_path.write_text(toml, "utf-8")

    # Persist any allocation changes to state
    updates: dict = {"proxy_name": proxy_name}
    if info.get("tunnel_id"):
        updates["tunnel_id"] = info["tunnel_id"]
    if info.get("public_url"):
        updates["public_url"] = info["public_url"]
    if t == "http" and info.get("subdomain"):
        updates["subdomain"] = info["subdomain"]
    if t in ("tcp", "udp") and info.get("remote_port"):
        updates["remote_port"] = info["remote_port"]
    _state.update_tunnel(_tunnel_name, **updates)


# ── Reregister / fallback ─────────────────────────────────────────────────

def _try_reregister_or_new() -> bool:
    """
    Attempt to reclaim our existing allocation, then fall back to a new tunnel.
    Updates the frpc TOML config file in place.
    Returns True on success.
    """
    tunnel = _state.get_tunnel(_tunnel_name)
    if not tunnel:
        _log("Tunnel record missing from state, cannot reconnect")
        return False

    tunnel_id  = tunnel.get("tunnel_id", "")
    t          = tunnel.get("type", "")
    local_host = tunnel.get("local_host", "127.0.0.1")
    local_port = int(tunnel.get("local_port", 0))
    subdomain  = tunnel.get("subdomain")
    proxy_name = tunnel.get("proxy_name", "")
    remote_port = tunnel.get("remote_port")

    # Build reregister request body
    rereg_body: dict = {
        "type":       t,
        "local_host": local_host,
        "local_port": local_port,
        "proxy_name": proxy_name,
    }
    if t == "http" and subdomain:
        rereg_body["subdomain"] = subdomain
    if t in ("tcp", "udp") and remote_port:
        rereg_body["remote_port"] = int(remote_port)

    # Step 1: reregister (reclaim same URL / port)
    if tunnel_id:
        try:
            _log(f"Attempting to reclaim allocation (tunnel_id={tunnel_id[:8]}...)...")
            info = _api.reregister_tunnel(tunnel_id, rereg_body)
            _log(f"Allocation reclaimed: {info.get('public_url', info.get('proxy_name'))}")
            _regenerate_config(info)
            return True
        except _api.APIError as exc:
            _log(f"Reregister failed: {exc}")
            if "conflict" in str(exc).lower():
                _log("Our subdomain/port was taken — requesting a new tunnel...")
            # Fall through to step 2

    # Step 2: request a completely new tunnel (last resort — URL will change)
    try:
        _log("Requesting a new tunnel allocation (URL may change)...")
        info = _api.request_tunnel(t, local_host, local_port, subdomain)
        _log(f"New tunnel allocated: {info.get('public_url')}")
        _regenerate_config(info)
        return True
    except _api.APIError as exc:
        _log(f"Failed to request new tunnel: {exc}")
        return False


# ── Wait helper ───────────────────────────────────────────────────────────

def _wait(seconds: int) -> None:
    """Sleep for `seconds`, breaking early if shutdown is requested."""
    for _ in range(max(1, seconds)):
        if _shutdown_flag:
            return
        time.sleep(1)


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    global _proc, _tunnel_name, _log_fd, _worker_lock_fd

    if len(sys.argv) < 2:
        sys.exit(1)

    _tunnel_name = sys.argv[1]

    # Acquire exclusive lock
    lock_path = Path(_state.PORTX_DIR) / "locks" / f"{_tunnel_name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _worker_lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(_worker_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(1)

    # Register signal handlers
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGUSR1, _reload)

    # Load initial tunnel state
    tunnel = _state.get_tunnel(_tunnel_name)
    if not tunnel:
        sys.exit(1)

    frp_config_path = Path(tunnel["frp_config_path"])
    log_path        = Path(tunnel["log_path"])

    # Redirect stdout/stderr to the log file
    _log_fd = open(log_path, "a", buffering=1)
    sys.stdout = _log_fd
    sys.stderr = _log_fd

    _log(f"Worker started for tunnel '{_tunnel_name}' (PID={os.getpid()})")

    # If config file is already missing before our first attempt, try to recover
    if not frp_config_path.exists():
        _log("FRP config file missing on startup — trying reregister...")
        if not _try_reregister_or_new():
            _log("Cannot recover config — marking tunnel as failed")
            _state.update_tunnel(_tunnel_name, status="failed", error="Config missing on startup")
            sys.exit(1)
        # Reload state after reregister regenerated config
        tunnel = _state.get_tunnel(_tunnel_name)
        frp_config_path = Path(tunnel["frp_config_path"])

    backoff = _INITIAL_BACKOFF
    attempt = 0

    while not _shutdown_flag:
        attempt += 1

        # Refresh state (could have been updated externally via 'portx reload')
        tunnel = _state.get_tunnel(_tunnel_name)
        if not tunnel:
            _log("Tunnel record removed from state — stopping worker")
            break

        # Respect an administrative stop (portx stop command)
        if tunnel.get("admin_stopped"):
            _log("Tunnel was administratively stopped — exiting worker")
            break

        # Reset reload flag before each attempt
        global _reload_flag
        _reload_flag = False

        frp_config_path = Path(tunnel["frp_config_path"])

        _log(f"Connection attempt #{attempt}...")

        # ── Try to start frpc ─────────────────────────────────────────────
        try:
            _proc = _runner.start_frpc(
                config_path=frp_config_path,
                frp_binary=_cfg.FRP_BINARY,
                timeout=_cfg.FRPC_CONNECT_TIMEOUT,
            )
        except _runner.FRPError as exc:
            exc_lower = str(exc).lower()
            _log(f"frpc failed to start: {exc}")

            # Allocation conflict → try to reregister
            if any(m in exc_lower for m in _CONFLICT_MARKERS):
                _log("Proxy/port conflict detected — attempting reregister...")
                if _try_reregister_or_new():
                    _log("Reregister successful, retrying frpc immediately...")
                    # Reset backoff on successful reregister
                    backoff = _INITIAL_BACKOFF
                    continue
                else:
                    _log("Reregister also failed — backing off...")

            # Fatal config error on first attempt → fail fast (CLI shows error)
            if attempt == 1 and any(m in exc_lower for m in _FATAL_MARKERS):
                _log(f"Fatal configuration error — not retrying")
                _state.update_tunnel(_tunnel_name, status="failed", error=str(exc))
                return

            # Transient failure → back off and retry
            _state.update_tunnel(_tunnel_name, status="reconnecting", error=str(exc))
            _log(f"Retrying in {backoff}s...")
            _wait(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)
            continue

        # ── frpc started successfully ──────────────────────────────────────
        tunnel_id = _state.get_tunnel(_tunnel_name).get("tunnel_id", "")
        _log(f"Connected (attempt #{attempt}, worker PID={os.getpid()}, frpc PID={_proc.pid})")
        _state.update_tunnel(_tunnel_name, status="running", pid=os.getpid(), error="")
        backoff = _INITIAL_BACKOFF  # successful connection → reset backoff

        # Start heartbeat thread
        hb_stop = threading.Event()
        hb_thread: threading.Thread | None = None
        if tunnel_id:
            hb_thread = threading.Thread(
                target=_heartbeat_loop,
                args=(tunnel_id, hb_stop),
                daemon=True,
                name=f"hb-{_tunnel_name}",
            )
            hb_thread.start()

        # ── Monitor frpc ───────────────────────────────────────────────────
        while not _shutdown_flag:
            ret = _proc.poll()
            if ret is not None:
                _log(f"frpc exited (code {ret})")
                break

            if _reload_flag:
                global _was_reload
                _reload_flag = False
                _was_reload  = True
                _log("Graceful reload: restarting frpc (brief reconnect ~1-3s)...")
                _kill_frpc()
                break

            time.sleep(1)

        # Stop heartbeat
        hb_stop.set()
        if hb_thread:
            hb_thread.join(timeout=3)

        if _shutdown_flag:
            break

        # ── frpc exited: decide how quickly to reconnect ──────────────────────
        if _was_reload:
            # Reload path: restart frpc IMMEDIATELY with no backoff.
            # frpc reconnects in ~1-3 s; this is the minimal-interruption reload.
            _was_reload = False
            _log("Reload complete, restarting frpc immediately...")
            _state.update_tunnel(_tunnel_name, status="reconnecting")
            continue

        # Normal reconnect path: apply exponential backoff
        _log(f"frpc disconnected. Reconnecting in {backoff}s (attempt #{attempt + 1})...")
        _state.update_tunnel(_tunnel_name, status="reconnecting")
        _wait(backoff)
        backoff = min(backoff * 2, _MAX_BACKOFF)

    # ── Worker exiting ────────────────────────────────────────────────────
    _state.update_tunnel(_tunnel_name, status="stopped", pid=0)
    _log(f"Worker for '{_tunnel_name}' stopped cleanly")


if __name__ == "__main__":
    main()
