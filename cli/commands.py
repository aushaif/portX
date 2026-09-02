"""
Management commands for PortX background tunnels.
Implements list, info, stop, remove, restart, reload, status, watchdog,
cleanup, and uninstall.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import api_client as _api
import config as _cfg
import state as _state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _kill_process(pid: int) -> None:
    if pid <= 0:
        return
    try:
        # Kill the entire process group to ensure child frpc dies too
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(0.5)
        if _state.is_pid_alive(pid):
            os.killpg(pgid, signal.SIGKILL)
    except OSError:
        pass


def _kill_worker(name: str, tunnel: dict) -> None:
    """Kill the worker process (and its frpc child) for the given tunnel."""
    pid = int(tunnel.get("pid", 0) or 0)
    if _state.is_pid_alive(pid):
        _kill_process(pid)


def _stop_tunnel(name: str, tunnel: dict) -> None:
    """
    Administratively stop a tunnel.

    Kills the worker process but does NOT release the server-side allocation,
    so the same URL/subdomain/port is preserved.  The tunnel can be restarted
    later with 'portx restart' without changing its public address.

    Sets admin_stopped=1 to tell the watchdog not to auto-restart this tunnel.
    """
    _kill_worker(name, tunnel)
    _state.update_tunnel(name, status="stopped", pid=0, admin_stopped=1)


def _spawn_worker(name: str) -> None:
    """Spawn the worker process in the background."""
    worker_script = Path(__file__).resolve().parent / "worker.py"

    proc = subprocess.Popen(
        [sys.executable, str(worker_script), name],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,  # Detach completely
    )

    _state.update_tunnel(name, pid=proc.pid)

    # Wait briefly for worker to either fail or succeed
    time.sleep(1.0)

    t = _state.get_tunnel(name)
    if t and t.get("status") == "failed":
        print(f"\n  ✗ Tunnel failed to start: {t.get('error', 'Unknown error')}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list() -> None:
    tunnels = _state.list_tunnels()

    print("\n  PORTX TUNNELS\n")
    if not tunnels:
        print("  No tunnels found.")
        print("  Tip: Run 'portx http 8080' to create a tunnel.")
        print()
        return

    # Formatting columns
    print(f"  {'NAME':<15} {'TYPE':<6} {'LOCAL':<20} {'PUBLIC':<40} {'STATUS':<14}")
    print("  " + "-" * 99)

    for name, t in tunnels.items():
        t_type = t.get("type", "???").upper()
        local  = f"{t.get('local_host', '')}:{t.get('local_port', '')}"
        public = t.get("public_url", "")
        status = t.get("status", "unknown").upper()
        auto   = " ★" if t.get("auto_start") else ""
        print(
            f"  {name[:14]:<15} {t_type[:5]:<6} {local[:19]:<20} "
            f"{public[:39]:<40} {(status + auto)[:13]:<14}"
        )

    print()
    print("  ★ = auto-start enabled (survives reboot)")
    print()


def cmd_info(name: str) -> None:
    t = _state.get_tunnel(name)
    if not t:
        print(f"\n  ✗ Tunnel '{name}' not found.\n")
        sys.exit(1)

    auto_start   = "Yes" if t.get("auto_start") else "No"
    admin_stop   = " (admin stopped)" if t.get("admin_stopped") else ""
    reconnecting = t.get("status") == "reconnecting"

    print()
    print(f"  Name:        {name}")
    print(f"  ID:          {t.get('tunnel_id', 'N/A')}")
    print(f"  Type:        {t.get('type', 'N/A').upper()}")
    print(f"  Local:       {t.get('local_host')}:{t.get('local_port')}")
    print(f"  Public:      {t.get('public_url', 'N/A')}")
    print(f"  Status:      {t.get('status', 'unknown').upper()}{admin_stop}")
    if reconnecting:
        print(f"  Last error:  {t.get('error', 'none')}")
    print(f"  Auto-start:  {auto_start}")
    print(f"  PID:         {t.get('pid', 'N/A')}")
    print(f"  Config:      {t.get('frp_config_path', 'N/A')}")
    print(f"  Log:         {t.get('log_path', 'N/A')}")
    print()


def cmd_stop(name: str) -> None:
    tunnels = _state.list_tunnels()
    if name not in tunnels:
        print(f"\n  ✗ Tunnel '{name}' not found.\n")
        sys.exit(1)

    _stop_tunnel(name, tunnels[name])
    print(f"\n  ✓ Tunnel '{name}' stopped.")
    print(f"  URL/port reservation is preserved. Use 'portx restart {name}' to reconnect.\n")


def cmd_stop_all() -> None:
    tunnels = _state.list_tunnels()
    if not tunnels:
        print("\n  ✓ No active tunnels to stop.\n")
        return

    for name, t in list(tunnels.items()):
        _stop_tunnel(name, t)

    print("\n  ✓ All tunnels stopped.\n")


def cmd_remove(name: str) -> None:
    t = _state.get_tunnel(name)
    if not t:
        print(f"\n  ✗ Tunnel '{name}' not found.\n")
        sys.exit(1)

    # Kill worker (without setting admin_stopped, since we're removing entirely)
    _kill_worker(name, t)

    # Release the server-side allocation (URL/port freed permanently)
    tunnel_id = t.get("tunnel_id")
    if tunnel_id:
        _api.release_tunnel(tunnel_id)

    # Clean up config and log files
    frp_path = t.get("frp_config_path")
    if frp_path and Path(frp_path).exists():
        Path(frp_path).unlink()

    log_path = t.get("log_path")
    if log_path and Path(log_path).exists():
        Path(log_path).unlink()

    _state.remove_tunnel(name)
    print(f"\n  ✓ Tunnel '{name}' removed permanently. URL/port allocation released.\n")


def cmd_remove_all() -> None:
    tunnels = _state.list_tunnels()
    if not tunnels:
        print("\n  ✓ No tunnels to remove.\n")
        return

    for name in list(tunnels.keys()):
        cmd_remove(name)

    print("\n  ✓ All tunnels removed permanently.\n")


def cmd_restart(name: str) -> None:
    t = _state.get_tunnel(name)
    if not t:
        print(f"\n  ✗ Tunnel '{name}' not found.\n")
        sys.exit(1)

    # Kill any existing worker gracefully
    if t.get("status") in ("starting", "running", "reconnecting"):
        _kill_worker(name, t)

    print(f"\n  → Restarting tunnel '{name}'...")

    # Clear admin_stopped so watchdog can manage it again
    _state.update_tunnel(name, status="starting", admin_stopped=0)
    _spawn_worker(name)

    t = _state.get_tunnel(name)
    print(f"  ✓ Tunnel '{name}' restarting.")
    print(f"  Public: {t.get('public_url')}\n")


def cmd_reload(name: str | None = None) -> None:
    """
    Reload tunnel configuration without stopping healthy connections.

    For each running tunnel:
      - Sends SIGUSR1 to the worker process.
      - The worker kills frpc and immediately restarts it, picking up any
        updated configuration from the state file.
      - frpc reconnects with the same proxy_name/subdomain/port.

    If the worker process is dead (crashed), the tunnel is restarted instead.
    """
    tunnels = _state.list_tunnels()
    if not tunnels:
        print("\n  No tunnels found.\n")
        return

    if name:
        if name not in tunnels:
            print(f"\n  ✗ Tunnel '{name}' not found.\n")
            sys.exit(1)
        targets = {name: tunnels[name]}
    else:
        targets = {
            n: t for n, t in tunnels.items()
            if t.get("status") not in ("stopped", "failed")
        }

    if not targets:
        print("\n  No active tunnels to reload.\n")
        return

    print("\n  Reloading tunnels...\n")
    reloaded  = 0
    restarted = 0
    skipped   = 0

    for tname, t in targets.items():
        pid    = int(t.get("pid", 0) or 0)
        status = t.get("status", "unknown")

        if _state.is_pid_alive(pid):
            try:
                os.kill(pid, signal.SIGUSR1)
                print(f"  ✓ Reloaded '{tname}'  (SIGUSR1 → PID {pid})")
                reloaded += 1
            except OSError as exc:
                print(f"  ✗ Could not reload '{tname}': {exc}")
                skipped += 1
        elif status in ("stopped", "failed"):
            print(f"  ✗ '{tname}' is {status.upper()} — use 'portx restart {tname}'")
            skipped += 1
        else:
            print(f"  → '{tname}' worker not running, restarting...")
            _state.update_tunnel(tname, status="starting", admin_stopped=0)
            _spawn_worker(tname)
            restarted += 1

    print()
    parts = []
    if reloaded:
        parts.append(f"{reloaded} reloaded (zero-downtime)")
    if restarted:
        parts.append(f"{restarted} restarted")
    if skipped:
        parts.append(f"{skipped} skipped")
    print(f"  Result: {', '.join(parts) or 'none'}\n")


def cmd_status() -> None:
    tunnels = _state.list_tunnels()

    running      = sum(1 for t in tunnels.values() if t.get("status") == "running")
    reconnecting = sum(1 for t in tunnels.values() if t.get("status") == "reconnecting")
    stopped      = sum(1 for t in tunnels.values() if t.get("status") in ("stopped", "failed"))
    auto_start   = sum(1 for t in tunnels.values() if t.get("auto_start"))

    print("\n  PortX v2.1\n")

    api_url = _cfg.get_api_url()

    # Check server reachability
    server_status = "Connected"
    try:
        import urllib.request
        req = urllib.request.Request(f"{api_url}/health")
        with urllib.request.urlopen(req, timeout=3) as r:
            pass
    except Exception:
        server_status = "Unreachable"

    # Check watchdog
    try:
        import launchd as _launchd
        watchdog_installed = _launchd.is_installed()
        watchdog_running   = _launchd.is_running() if watchdog_installed else False
        watchdog_status    = "Running" if watchdog_running else ("Installed, not running" if watchdog_installed else "Not installed")
    except Exception:
        watchdog_status = "Unknown"

    print(f"  Server:    {server_status}")
    print(f"  API URL:   {api_url}")
    print(f"  Tunnels:   {running} running, {reconnecting} reconnecting, {stopped} stopped")
    print(f"  Auto-start:{auto_start} tunnel(s) marked for auto-start")
    print(f"  Watchdog:  {watchdog_status}")
    print()


def cmd_watchdog_install() -> None:
    """Install the watchdog as a boot service (macOS LaunchAgent or Linux systemd)."""
    import launchd as _launchd
    print("\n  → Installing PortX watchdog service...")
    try:
        msg = _launchd.install()
        print(f"\n  ✓ {msg}")
        print()
        print("  The watchdog will now automatically restart your auto-start tunnels")
        print("  after login, reboot, or power failure.")
        print()
        print("  Mark a tunnel for auto-start with:")
        print("    portx http 8080 --auto-start")
        print()
    except RuntimeError as exc:
        print(f"\n  ✗ Installation failed: {exc}\n", file=sys.stderr)
        sys.exit(1)


def cmd_watchdog_uninstall() -> None:
    """Remove the watchdog boot service."""
    import launchd as _launchd
    print("\n  → Removing PortX watchdog service...")
    try:
        msg = _launchd.uninstall()
        print(f"\n  ✓ {msg}\n")
    except RuntimeError as exc:
        print(f"\n  ✗ Removal failed: {exc}\n", file=sys.stderr)
        sys.exit(1)


def cmd_watchdog_status() -> None:
    """Show the watchdog installation and running status."""
    import launchd as _launchd
    installed = _launchd.is_installed()
    running   = _launchd.is_running() if installed else False

    # Count auto-start tunnels
    tunnels   = _state.list_tunnels()
    auto_count = sum(1 for t in tunnels.values() if t.get("auto_start"))

    print()
    print(f"  Watchdog installed: {'Yes' if installed else 'No'}")
    print(f"  Watchdog running:   {'Yes' if running else 'No'}")
    print(f"  Auto-start tunnels: {auto_count}")
    if not installed:
        print()
        print("  Install with: portx watchdog install")
    print()


def _kill_all_portx_processes() -> None:
    """Kill every frpc and portx worker process on the system, regardless of state."""
    targets = ["worker.py", str(Path.home() / ".portx" / "bin" / "frpc"), "frpc", "watchdog.py"]
    killed = 0
    for pattern in targets:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True, text=True
            )
            for pid_str in result.stdout.strip().splitlines():
                try:
                    pid = int(pid_str.strip())
                    if pid == os.getpid():
                        continue  # never kill ourselves
                    try:
                        os.kill(pid, signal.SIGTERM)
                        killed += 1
                    except OSError:
                        pass
                except ValueError:
                    pass
        except FileNotFoundError:
            pass  # pgrep not available
        except Exception:
            pass

    if killed:
        time.sleep(0.8)  # give processes time to die
    print(f"  ✓ Terminated {killed} background process(es).")


def cmd_uninstall() -> None:
    """Complete system uninstall of PortX — removes every file PortX installed."""
    print("\n  PortX Uninstaller")
    print("  ─────────────────────────────────────────\n")

    # 1. Check if Homebrew-managed
    portx_bin = shutil.which("portx")
    is_homebrew = portx_bin and (
        "homebrew" in portx_bin.lower()
        or "cellar" in portx_bin.lower()
        or "/opt/homebrew" in portx_bin
    )
    if is_homebrew:
        print("  ✗ PortX was installed via Homebrew.")
        print("    Please uninstall using: brew uninstall portx")
        print("    To remove runtime data:  rm -rf ~/.portx\n")
        sys.exit(1)

    # 2. Remove watchdog boot service first
    try:
        import launchd as _launchd
        if _launchd.is_installed():
            print("  → Removing watchdog boot service...")
            _launchd.uninstall()
            print("  ✓ Watchdog service removed.")
    except Exception:
        pass

    # 3. Kill ALL lingering frpc / worker / watchdog processes
    print("  → Killing all PortX background processes...")
    _kill_all_portx_processes()

    # 4. Stop tunnels and release allocations
    try:
        tunnels = _state.list_tunnels()
        if tunnels:
            print("  → Releasing tunnel allocations...")
            for name, t in list(tunnels.items()):
                _kill_worker(name, t)
                tunnel_id = t.get("tunnel_id")
                if tunnel_id:
                    _api.release_tunnel(tunnel_id)
            print("  ✓ Allocations released.")
    except Exception:
        pass

    removed: list[str] = []

    # 5. Delete ~/.portx/ (runtime data + config)
    portx_dir = Path.home() / ".portx"
    if portx_dir.exists():
        print(f"  → Removing {portx_dir} ...")
        try:
            shutil.rmtree(portx_dir)
            removed.append("~/.portx/")
            print("  ✓ Runtime directory removed.")
        except Exception as e:
            print(f"  ✗ Failed to remove {portx_dir}: {e}")

    # 6. Delete CLI executable ~/.local/bin/portx
    local_bin_portx = Path.home() / ".local" / "bin" / "portx"
    if local_bin_portx.exists() or local_bin_portx.is_symlink():
        print(f"  → Removing {local_bin_portx} ...")
        try:
            local_bin_portx.unlink()
            removed.append("~/.local/bin/portx")
            print("  ✓ CLI executable removed.")
        except Exception as e:
            print(f"  ✗ Failed to remove executable: {e}")

    # 7. Delete CLI library ~/.local/lib/portx/
    local_lib_portx = Path.home() / ".local" / "lib" / "portx"
    if local_lib_portx.exists():
        print(f"  → Removing {local_lib_portx} ...")
        try:
            shutil.rmtree(local_lib_portx)
            removed.append("~/.local/lib/portx/")
            print("  ✓ CLI library removed.")
        except Exception as e:
            print(f"  ✗ Failed to remove library directory: {e}")

    # 8. Summary
    print("\n  ✓ PortX has been successfully uninstalled.\n")
    if removed:
        print("  Removed:")
        for path in removed:
            print(f"    - {path}")
    print()
    print("  Note: PATH entries added to your shell RC file were not removed.")
    print("  You can clean them up manually if desired.\n")


def cmd_api_set(token: str) -> None:
    """Save the PortX auth token to ~/.portx/config.toml."""
    token = token.strip()
    if not token:
        print("\n  ✗ Token cannot be empty.\n", file=sys.stderr)
        sys.exit(1)

    _cfg.set_auth_token(token)

    masked = token[:6] + "*" * max(0, len(token) - 6)
    print(f"\n  ✓ Auth token updated: {masked}")
    print(f"  Saved to: {_cfg.CONFIG_TOML}\n")


def cmd_api_ls() -> None:
    """Display the currently configured API URL and token status."""
    cfg_path = _cfg.CONFIG_TOML
    api_url  = _cfg.get_api_url()

    try:
        raw   = _cfg._load_config()
        token = raw.get("portx", {}).get("auth_token", "").strip()
    except Exception:
        token = ""

    token_display = (token[:6] + "*" * max(0, len(token) - 6)) if token else "(not set)"

    print()
    print(f"  API URL:    {api_url}")
    print(f"  Auth token: {token_display}")
    print(f"  Config:     {cfg_path}")
    print()


def cmd_cleanup(force: bool = False) -> None:
    """Clean up orphaned tunnel configuration files and logs."""
    print("\n  PortX Cleanup\n")

    tunnels = _state.list_tunnels()

    config_dir = _state.CONFIGS_DIR
    log_dir    = _state.LOGS_DIR

    cleaned_configs = 0
    cleaned_logs    = 0

    known_tunnels = set(tunnels.keys())

    if config_dir.exists():
        for config_file in config_dir.glob("*.toml"):
            tunnel_name = config_file.stem
            if tunnel_name not in known_tunnels or (
                force and tunnels.get(tunnel_name, {}).get("status") == "stopped"
            ):
                config_file.unlink()
                cleaned_configs += 1
                print(f"  → Removed orphaned config: {config_file.name}")

    if log_dir.exists():
        for log_file in log_dir.glob("*.log"):
            tunnel_name = log_file.stem
            if tunnel_name not in known_tunnels or (
                force and tunnels.get(tunnel_name, {}).get("status") == "stopped"
            ):
                log_file.unlink()
                cleaned_logs += 1
                print(f"  → Removed orphaned log: {log_file.name}")

    if force:
        removed = []
        for name, t in list(tunnels.items()):
            if t.get("status") in ("stopped", "failed"):
                _state.remove_tunnel(name)
                removed.append(name)

        if removed:
            print(f"\n  → Removed {len(removed)} stopped tunnel record(s)")

    if cleaned_configs == 0 and cleaned_logs == 0 and (not force):
        print("  ✓ No cleanup needed - everything is in sync.\n")
    else:
        print(f"\n  ✓ Cleanup complete:")
        print(f"    Configs removed: {cleaned_configs}")
        print(f"    Logs removed:    {cleaned_logs}")
        if force and removed:
            print(f"    Records removed: {len(removed)}")
        print()
