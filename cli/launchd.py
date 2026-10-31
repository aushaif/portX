"""
PortX system service installer.

Without sudo on macOS, installs a user LaunchAgent that starts at login.
With sudo, installs/removes a system-level boot daemon:
  - macOS : /Library/LaunchDaemons/<label>.plist  (runs at boot, before login)
  - Linux : /etc/systemd/system/portx-watchdog.service

This requires root privileges (sudo) but configures the daemon to run as the
original user, ensuring it accesses their ~/.portx directory correctly.
"""

from __future__ import annotations

import os
import platform
import plistlib
import pwd
import subprocess
import sys
from pathlib import Path

# ── Constants ─────────────────────────────────────────────────────────────
_LAUNCHD_LABEL   = "lol.infinitynoob.portx.watchdog"
_LAUNCHD_PLIST   = Path("/Library/LaunchDaemons") / f"{_LAUNCHD_LABEL}.plist"
_USER_LABEL = "space.infinitynoob.portx.watchdog"
_USER_PLIST = Path.home() / "Library/LaunchAgents" / f"{_USER_LABEL}.plist"
_SYSTEMD_SERVICE = Path("/etc/systemd/system/portx-watchdog.service")


def _get_target_user() -> tuple[str, str]:
    """Return (username, home_dir) of the user who invoked sudo, or the current user."""
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        user_info = pwd.getpwnam(sudo_user)
        return user_info.pw_name, user_info.pw_dir
    else:
        # If not running under sudo, just get the current user
        user_info = pwd.getpwuid(os.getuid())
        return user_info.pw_name, user_info.pw_dir


def _python_exe() -> str:
    """Return the path to the current Python interpreter."""
    return sys.executable


def _watchdog_script(home_dir: str) -> str:
    """Return the absolute path to watchdog.py."""
    here      = Path(__file__).resolve().parent
    candidate = here / "watchdog.py"
    if candidate.exists():
        return str(candidate)
    # Installed location
    installed = Path(home_dir) / ".local" / "lib" / "portx" / "watchdog.py"
    if installed.exists():
        return str(installed)
    return str(candidate)


# ── Public API ────────────────────────────────────────────────────────────

def install() -> str:
    """
    Install the watchdog as a system boot daemon.
    Raises RuntimeError on failure (e.g., no sudo).
    """
    if platform.system() == "Darwin" and os.geteuid() != 0:
        return _install_user_macos()
    if os.geteuid() != 0:
        raise RuntimeError("Installing the boot daemon requires root privileges. Please run with sudo.")

    system = platform.system()
    if system == "Darwin":
        return _install_macos()
    elif system == "Linux":
        return _install_linux()
    else:
        raise RuntimeError(
            f"Auto-start is not supported on {system}.\n"
            "  Manually run 'python3 ~/.local/lib/portx/watchdog.py &' at login."
        )


def uninstall() -> str:
    """
    Remove the watchdog boot daemon.
    Raises RuntimeError on failure (e.g., no sudo).
    """
    if platform.system() == "Darwin" and os.geteuid() != 0:
        return _uninstall_user_macos()
    if os.geteuid() != 0:
        raise RuntimeError("Removing the boot daemon requires root privileges. Please run with sudo.")

    system = platform.system()
    if system == "Darwin":
        return _uninstall_macos()
    elif system == "Linux":
        return _uninstall_linux()
    else:
        return f"No auto-start service to remove on {system}."


def is_installed() -> bool:
    system = platform.system()
    if system == "Darwin":
        return _USER_PLIST.exists() or _LAUNCHD_PLIST.exists()
    elif system == "Linux":
        return _SYSTEMD_SERVICE.exists()
    return False


def is_running() -> bool:
    system = platform.system()
    if system == "Darwin":
        try:
            target = f"gui/{os.getuid()}/{_USER_LABEL}" if _USER_PLIST.exists() else f"system/{_LAUNCHD_LABEL}"
            r = subprocess.run(
                ["launchctl", "print", target],
                capture_output=True, text=True,
            )
            return r.returncode == 0 and "state = running" in r.stdout
        except Exception:
            return False
    elif system == "Linux":
        try:
            r = subprocess.run(
                ["systemctl", "is-active", "portx-watchdog"],
                capture_output=True, text=True,
            )
            return r.stdout.strip() == "active"
        except Exception:
            return False
    return False


# ── macOS launchd ─────────────────────────────────────────────────────────

def _install_macos() -> str:
    user, home = _get_target_user()
    python   = _python_exe()
    watchdog = _watchdog_script(home)
    log      = f"{home}/.portx/logs/watchdog.log"

    # Ensure log dir exists and belongs to the user
    log_dir = Path(home) / ".portx" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    os.chown(str(log_dir), pwd.getpwnam(user).pw_uid, pwd.getpwnam(user).pw_gid)
    os.chown(str(log_dir.parent), pwd.getpwnam(user).pw_uid, pwd.getpwnam(user).pw_gid)

    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LAUNCHD_LABEL}</string>

    <!-- Run as the user, not root -->
    <key>UserName</key>
    <string>{user}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>{home}</string>
        <key>USER</key>
        <string>{user}</string>
    </dict>

    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{watchdog}</string>
    </array>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>{log}</string>
    <key>StandardErrorPath</key>
    <string>{log}</string>
</dict>
</plist>
"""
    _LAUNCHD_PLIST.write_text(plist, "utf-8")
    # LaunchDaemons must be owned by root:wheel
    os.chown(str(_LAUNCHD_PLIST), 0, 0)
    os.chmod(str(_LAUNCHD_PLIST), 0o644)

    subprocess.run(["launchctl", "unload", str(_LAUNCHD_PLIST)], capture_output=True)
    result = subprocess.run(["launchctl", "load", "-w", str(_LAUNCHD_PLIST)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"launchctl load failed: {result.stderr.strip()}")

    return f"macOS System LaunchDaemon installed for user '{user}'\n  Path: {_LAUNCHD_PLIST}"


def _uninstall_macos() -> str:
    if _LAUNCHD_PLIST.exists():
        try:
            subprocess.run(["launchctl", "unload", "-w", str(_LAUNCHD_PLIST)], capture_output=True, timeout=4.0)
        except Exception:
            pass
        try:
            _LAUNCHD_PLIST.unlink()
        except OSError:
            pass
        return f"macOS System LaunchDaemon removed: {_LAUNCHD_PLIST}"
    return "macOS LaunchDaemon was not installed."


# ── Linux systemd ─────────────────────────────────────────────────────────

def _install_linux() -> str:
    user, home = _get_target_user()
    python   = _python_exe()
    watchdog = _watchdog_script(home)
    log      = f"{home}/.portx/logs/watchdog.log"

    log_dir = Path(home) / ".portx" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    os.chown(str(log_dir), pwd.getpwnam(user).pw_uid, pwd.getpwnam(user).pw_gid)
    os.chown(str(log_dir.parent), pwd.getpwnam(user).pw_uid, pwd.getpwnam(user).pw_gid)

    service = f"""[Unit]
Description=PortX Tunnel Watchdog for {user}
Documentation=https://github.com/aushaif/portX
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
Environment=HOME={home}
Environment=USER={user}
ExecStart={python} {watchdog}
Restart=always
RestartSec=10
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=multi-user.target
"""
    _SYSTEMD_SERVICE.write_text(service, "utf-8")
    os.chmod(str(_SYSTEMD_SERVICE), 0o644)

    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
    result = subprocess.run(["systemctl", "enable", "--now", "portx-watchdog"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"systemctl enable failed: {result.stderr.strip()}")

    return f"Linux systemd daemon installed for user '{user}'\n  Path: {_SYSTEMD_SERVICE}"


def _uninstall_linux() -> str:
    if _SYSTEMD_SERVICE.exists():
        try:
            subprocess.run(["systemctl", "disable", "--now", "portx-watchdog"], capture_output=True, timeout=4.0)
        except Exception:
            pass
        try:
            _SYSTEMD_SERVICE.unlink()
        except OSError:
            pass
        try:
            subprocess.run(["systemctl", "daemon-reload"], capture_output=True, timeout=4.0)
        except Exception:
            pass
        return f"Linux systemd daemon removed: {_SYSTEMD_SERVICE}"
    return "Linux systemd daemon was not installed."


def _install_user_macos() -> str:
    """Run outside Terminal's process tree, without requiring a root daemon."""
    if _LAUNCHD_PLIST.exists():
        raise RuntimeError("A system watchdog already exists. Use sudo portx watchdog install to update it.")
    home = str(Path.home())
    log_dir = Path(home) / ".portx/logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _USER_PLIST.parent.mkdir(parents=True, exist_ok=True)
    job = {
        "Label": _USER_LABEL,
        "ProgramArguments": [_python_exe(), _watchdog_script(home)],
        "EnvironmentVariables": {"HOME": home, "USER": pwd.getpwuid(os.getuid()).pw_name},
        "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10,
        "StandardOutPath": str(log_dir / "watchdog.log"),
        "StandardErrorPath": str(log_dir / "watchdog.log"),
    }
    _USER_PLIST.write_bytes(plistlib.dumps(job))
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{_USER_LABEL}"], capture_output=True)
    result = subprocess.run(["launchctl", "bootstrap", domain, str(_USER_PLIST)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"launchctl bootstrap failed: {result.stderr.strip()}")
    return f"macOS LaunchAgent installed (starts at login): {_USER_PLIST}"


def _uninstall_user_macos() -> str:
    if not _USER_PLIST.exists():
        if _LAUNCHD_PLIST.exists():
            raise RuntimeError("System watchdog removal requires sudo portx watchdog uninstall")
        return "No user watchdog installed."
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{_USER_LABEL}"], capture_output=True)
    _USER_PLIST.unlink()
    return "macOS user watchdog removed."
