"""Built-in, per-user tunnel supervisor. No OS service or separate install.

Started automatically by the CLI in a double-forked session. The lock is the
single-instance authority. Explicit shutdown uses a control file; terminal
SIGHUP, SIGINT and SIGTERM cannot shut down the shared supervisor.
"""
from __future__ import annotations

import fcntl
import json
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

import state

_ROOT = state.PORTX_DIR
_LOCK = _ROOT / '.supervisor.lock'
_START_LOCK = _ROOT / '.supervisor-start.lock'
_RECORD = _ROOT / 'supervisor.json'
_STOP = _ROOT / '.supervisor-stop'
_REQUESTS = _ROOT / 'supervisor-requests'
_LOG = state.LOGS_DIR / 'supervisor.log'
_CHILDREN: dict[str, subprocess.Popen] = {}
_WAKE = False


def is_running() -> bool:
    try:
        with _LOCK.open('a') as fd:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
    except BlockingIOError:
        return True


def _wake(signum=None, frame=None):
    global _WAKE
    _WAKE = True


def wake() -> None:
    if is_running():
        try:
            pid = json.loads(_RECORD.read_text())['pid']
            os.kill(int(pid), signal.SIGUSR1)
        except (OSError, ValueError, KeyError):
            pass


def retire_legacy_agent() -> None:
    """Remove the old user agent on upgrades; never install an OS service."""
    if platform.system() != 'Darwin':
        return
    agent = Path.home() / 'Library/LaunchAgents/space.infinitynoob.portx.watchdog.plist'
    if agent.exists():
        result = subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/space.infinitynoob.portx.watchdog'],
                                capture_output=True, text=True)
        # A missing/unloaded job is safe to remove too; preserve its plist.
        if result.returncode and 'Could not find' not in result.stderr and 'No such process' not in result.stderr:
            check = subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/space.infinitynoob.portx.watchdog'],
                                   capture_output=True)
            if check.returncode == 0:
                raise RuntimeError('Could not unload the legacy PortX agent: ' + result.stderr.strip())
        archive = _ROOT / 'backups' / 'legacy-watchdog.plist.disabled'
        archive.parent.mkdir(parents=True, exist_ok=True)
        agent.replace(archive)


def ensure_running() -> None:
    _ROOT.mkdir(parents=True, exist_ok=True)
    with _START_LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        retire_legacy_agent()
        if is_running():
            return
        _STOP.unlink(missing_ok=True)
        launcher = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--daemonize'],
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        launcher.wait(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if is_running():
                return
            time.sleep(0.05)
        raise RuntimeError(f'PortX supervisor failed to start. Check {_LOG}')


def request_start(name: str) -> None:
    if not state.get_tunnel(name):
        raise ValueError(f'Tunnel {name!r} does not exist')
    ensure_running()
    _REQUESTS.mkdir(parents=True, exist_ok=True)
    (_REQUESTS / name).touch()
    wake()


def shutdown(timeout: float = 5) -> None:
    """Explicit shutdown for upgrades/uninstall; terminal signals are ignored."""
    with _START_LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not is_running():
            return
        _STOP.touch()
        wake()
        deadline = time.monotonic() + timeout
        while is_running() and time.monotonic() < deadline:
            time.sleep(0.05)
        if is_running():
            raise RuntimeError('PortX supervisor has not shut down yet')


def _log(message: str) -> None:
    print(f'[{time.strftime("%Y-%m-%d %H:%M:%S")}] {message}', flush=True)


def _check_and_restore() -> None:
    requested = set()
    _REQUESTS.mkdir(parents=True, exist_ok=True)
    for path in _REQUESTS.iterdir():
        if path.is_file():
            requested.add(path.name)
            path.unlink(missing_ok=True)
    for name, child in list(_CHILDREN.items()):
        if child.poll() is not None:
            del _CHILDREN[name]
    for name, tunnel in state.load_tunnels().items():
        if tunnel.get('admin_stopped'):
            continue
        if name not in requested and not tunnel.get('auto_start', 1):
            continue
        if state.is_worker_locked(name) or name in _CHILDREN:
            continue
        _log(f'Restoring tunnel {name}')
        _CHILDREN[name] = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name('worker.py')), name],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)


def main() -> None:
    global _WAKE
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal.SIG_IGN)
    signal.signal(signal.SIGUSR1, _wake)
    if '--daemonize' in sys.argv:
        if os.fork():
            os._exit(0)
        os.setsid()
        if os.fork():
            os._exit(0)
        os.chdir('/')
    with _LOCK.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        state.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with _LOG.open('a', buffering=1) as log:
            sys.stdout = sys.stderr = log
            _RECORD.write_text(json.dumps({'pid': os.getpid()}))
            _log(f'PortX built-in supervisor started (PID={os.getpid()})')
            try:
                while not _STOP.exists():
                    try:
                        _check_and_restore()
                    except Exception as exc:
                        _log(f'Recovery error: {exc}')
                    for _ in range(20):
                        if _WAKE or _STOP.exists():
                            break
                        time.sleep(0.1)
                    _WAKE = False
            finally:
                _log('PortX supervisor stopped explicitly')
                _RECORD.unlink(missing_ok=True)
                _STOP.unlink(missing_ok=True)
                # Workers retain their detached sessions; upgrades do not drop
                # existing tunnels. Explicit stop/remove controls each worker.


if __name__ == '__main__':
    main()
