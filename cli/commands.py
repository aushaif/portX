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

    stopped = 0
    for name, t in list(tunnels.items()):
        if _state.is_worker_locked(name) or t.get("status") in ("starting", "running", "reconnecting"):
            _stop_tunnel(name, t)
            stopped += 1

    print(f"\n  ✓ All {stopped} active tunnels stopped.\n")

def cmd_start(name: str) -> None:
    t = _state.get_tunnel(name)
    if not t:
        print(f"\n  ✗ Tunnel '{name}' not found.\n")
        sys.exit(1)

    # Check if worker is already running (via lock or status)
    if _state.is_worker_locked(name) or t.get("status") in ("starting", "running", "reconnecting"):
        print(f"\n  ✓ Tunnel '{name}' is already running.\n")
        return

    print(f"\n  → Starting tunnel '{name}'...")
    _state.update_tunnel(name, status="starting", admin_stopped=0)
    _spawn_worker(name)

    t = _state.get_tunnel(name)
    print(f"  ✓ Tunnel '{name}' started.")
    print(f"  Public: {t.get('public_url')}\n")

def cmd_start_all() -> None:
    tunnels = _state.list_tunnels()
    if not tunnels:
        print("\n  No saved tunnels found.\n")
        return

    print("\n  Starting all stopped tunnels...\n")
    started = 0
    skipped = 0

    for name, t in tunnels.items():
        if _state.is_worker_locked(name) or t.get("status") in ("starting", "running", "reconnecting"):
            print(f"  → Skipped '{name}' (already running)")
            skipped += 1
            continue
            
        print(f"  → Starting '{name}'...")
        _state.update_tunnel(name, status="starting", admin_stopped=0)
        _spawn_worker(name)
        started += 1

    print()
    print(f"  ✓ Started: {started}")
    print(f"  ✓ Skipped: {skipped}\n")


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


def _prompt(label: str, current: str | int | None, cast=str) -> str | int:
    """Show a prompt with the current value; return new value or keep current."""
    disp = str(current) if current is not None else ""
    try:
        raw = input(f"  {label} [{disp}]: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)
    if not raw:
        return current  # type: ignore[return-value]
    if cast == int:
        try:
            return int(raw)
        except ValueError:
            print(f"  ✗ Invalid integer '{raw}', keeping current value.")
            return current  # type: ignore[return-value]
    return raw


def cmd_edit(name: str) -> None:
    """
    Interactively edit a tunnel's configuration via a step-by-step prompt UI.

    Editable fields:
      • Tunnel name (renames all saved state and config files)
      • Tunnel type  (http / tcp / udp)
      • Local IP
      • Local port
      • For HTTP:   subdomain
      • For TCP/UDP: remote port (server-side port)

    After editing:
      • Re-generates the frpc TOML config on disk.
      • If the name changed, moves files and updates state references.
      • If the tunnel is running, triggers an instant graceful reload.
    """
    import frp_config as _toml

    t = _state.get_tunnel(name)
    if not t:
        print(f"\n  ✗ Tunnel '{name}' not found.\n")
        sys.exit(1)

    tunnel_type  = t.get("type", "http")
    local_host   = t.get("local_host", "127.0.0.1")
    local_port   = t.get("local_port", 8080)
    subdomain    = t.get("subdomain", "")
    remote_port  = t.get("remote_port")
    proxy_name   = t.get("proxy_name", "")
    tunnel_id    = t.get("tunnel_id", "")
    public_url   = t.get("public_url", "")
    frps_host    = t.get("frps_host") or _cfg.FRPS_HOST
    frps_port    = t.get("frps_port") or _cfg.FRPS_PORT
    config_path  = Path(t.get("frp_config_path", ""))
    log_path     = Path(t.get("log_path", ""))

    print(f"\n  ╔══════════════════════════════════════════╗")
    print(f"  ║  Editing tunnel: {name:<25}║")
    print(f"  ╚══════════════════════════════════════════╝")
    print(f"  Press ENTER to keep the current value shown in [ ].\n")

    # ── Tunnel name ───────────────────────────────────────────────────────
    new_name = _prompt("Tunnel name", name)

    # ── Tunnel type ───────────────────────────────────────────────────────
    print()
    print(f"  Tunnel type options: http, tcp, udp")
    while True:
        new_type = _prompt("Tunnel type", tunnel_type)
        if new_type in ("http", "tcp", "udp"):
            break
        print(f"  ✗ Invalid type '{new_type}'. Choose: http, tcp, udp")

    # ── Local IP ──────────────────────────────────────────────────────────
    new_local_host = _prompt("Local IP", local_host)

    # ── Local port ────────────────────────────────────────────────────────
    new_local_port = _prompt("Local port", local_port, cast=int)

    # ── Type-specific fields ──────────────────────────────────────────────
    new_subdomain   = subdomain
    new_remote_port = remote_port

    if new_type == "http":
        print()
        print(f"  Subdomain → https://<subdomain>.{_cfg.HTTP_TUNNEL_DOMAIN}")
        new_subdomain = _prompt("Subdomain", subdomain)
        new_remote_port = None
    else:
        domain = _cfg.TCP_TUNNEL_DOMAIN if new_type == "tcp" else _cfg.UDP_TUNNEL_DOMAIN
        print()
        print(f"  Remote port → {domain}:<remote_port>")
        new_remote_port = _prompt("Remote port", remote_port, cast=int)
        new_subdomain = None

    # ── Summary & confirm ─────────────────────────────────────────────────
    print()
    print("  ─────────────────────────────────────────────")
    print("  Proposed changes:")
    print(f"    Name:        {name} → {new_name}" if new_name != name else f"    Name:        {name}")
    print(f"    Type:        {tunnel_type} → {new_type}" if new_type != tunnel_type else f"    Type:        {tunnel_type}")
    print(f"    Local:       {local_host}:{local_port} → {new_local_host}:{new_local_port}")
    if new_type == "http":
        print(f"    Subdomain:   {subdomain} → {new_subdomain}" if new_subdomain != subdomain else f"    Subdomain:   {subdomain}")
    else:
        print(f"    Remote port: {remote_port} → {new_remote_port}" if new_remote_port != remote_port else f"    Remote port: {remote_port}")
    print("  ─────────────────────────────────────────────")
    try:
        confirm = input("  Apply these changes? [Y/n]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\n  ✗ Cancelled.\n")
        sys.exit(0)
    if confirm and confirm not in ("y", "yes"):
        print("  ✗ Cancelled — no changes made.\n")
        return

    # ── Stop worker if running ────────────────────────────────────────────
    was_running = _state.is_worker_locked(name) or t.get("status") in ("starting", "running", "reconnecting")
    if was_running:
        print("\n  → Stopping tunnel to apply changes...")
        _stop_tunnel(name, t)
        time.sleep(0.5)

    # ── Recalculate proxy_name if type or key identifiers changed ─────────
    if new_type == "http" and new_subdomain:
        new_proxy_name = f"portx-http-{new_subdomain}"
        new_public_url = f"https://{new_subdomain}.{_cfg.HTTP_TUNNEL_DOMAIN}"
    elif new_type == "tcp" and new_remote_port:
        new_proxy_name = f"portx-tcp-{new_remote_port}"
        new_public_url = f"{_cfg.TCP_TUNNEL_DOMAIN}:{new_remote_port}"
    elif new_type == "udp" and new_remote_port:
        new_proxy_name = f"portx-udp-{new_remote_port}"
        new_public_url = f"{_cfg.UDP_TUNNEL_DOMAIN}:{new_remote_port}"
    else:
        new_proxy_name = proxy_name
        new_public_url = public_url

    # ── Re-generate frpc TOML config ──────────────────────────────────────
    new_config_path = config_path
    new_log_path    = log_path

    if new_name != name:
        # Rename config / log paths
        new_config_path = _state.CONFIGS_DIR / f"{new_name}.toml"
        new_log_path    = _state.LOGS_DIR / f"{new_name}.log"
        # Remove old files (new worker will create fresh log)
        if config_path.exists():
            config_path.unlink()
        if log_path.exists():
            log_path.rename(new_log_path)

    if new_type == "http":
        toml = _toml.generate_http_config(
            local_host=new_local_host, local_port=int(new_local_port),
            subdomain=new_subdomain, proxy_name=new_proxy_name,
            frps_host=frps_host, frps_port=int(frps_port),
        )
    elif new_type == "tcp":
        toml = _toml.generate_tcp_config(
            local_host=new_local_host, local_port=int(new_local_port),
            remote_port=int(new_remote_port), proxy_name=new_proxy_name,
            frps_host=frps_host, frps_port=int(frps_port),
        )
    else:  # udp
        toml = _toml.generate_udp_config(
            local_host=new_local_host, local_port=int(new_local_port),
            remote_port=int(new_remote_port), proxy_name=new_proxy_name,
            frps_host=frps_host, frps_port=int(frps_port),
        )

    new_config_path.write_text(toml, "utf-8")

    # ── Update state ──────────────────────────────────────────────────────
    # If renamed, remove the old record first, then create the new one
    if new_name != name:
        _state.remove_tunnel(name)

    _state.update_tunnel(
        new_name,
        type=new_type,
        local_host=new_local_host,
        local_port=int(new_local_port),
        public_url=new_public_url,
        proxy_name=new_proxy_name,
        subdomain=new_subdomain if new_type == "http" else None,
        remote_port=int(new_remote_port) if new_type in ("tcp", "udp") else None,
        frp_config_path=str(new_config_path),
        log_path=str(new_log_path),
        tunnel_id=tunnel_id,
        status="stopped",
        admin_stopped=0,
    )

    print(f"\n  ✓ Configuration updated.")
    if new_name != name:
        print(f"  ✓ Tunnel renamed: '{name}' → '{new_name}'")

    # ── Restart if was running ────────────────────────────────────────────
    if was_running:
        print(f"  → Restarting tunnel '{new_name}'...")
        _state.update_tunnel(new_name, status="starting")
        _spawn_worker(new_name)
        t2 = _state.get_tunnel(new_name)
        print(f"  ✓ Tunnel '{new_name}' restarted.")
        print(f"  Public: {t2.get('public_url')}\n")
    else:
        print(f"  ✓ Run 'portx start {new_name}' to activate with the new settings.\n")


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
