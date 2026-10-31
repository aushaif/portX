#!/usr/bin/env python3
"""Install this checkout without downloading an older GitHub version."""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watchdog', action='store_true', help='Install the login/boot service')
    parser.add_argument('--api-url', help='Override the API URL after validating the server')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    home = Path.home()
    lib = home / '.local/lib/portx'
    runtime = home / '.portx'
    runtime.mkdir(parents=True, exist_ok=True)
    backup = runtime / 'backups' / time.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True)
    if lib.exists():
        shutil.copytree(lib, backup / 'cli', ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('config.toml', 'tunnels.toml', 'portx.config.json'):
        path = runtime / name
        if path.exists():
            shutil.copy2(path, backup / name)
    lib.mkdir(parents=True, exist_ok=True)
    for path in (root / 'cli').glob('*.py'):
        shutil.copy2(path, lib / path.name)
    shutil.copy2(root / 'portx.config.json', runtime / 'portx.config.json')
    wrapper = home / '.local/bin/portx'
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        '#!' + sys.executable + '\nimport sys\n'
        + f'sys.path.insert(0, {str(lib)!r})\n'
        + 'import portx\nportx.main()\n')
    wrapper.chmod(0o755)
    sys.path.insert(0, str(lib))
    import config
    if args.api_url:
        config.set_api_url(args.api_url)
    # Apply migration before restarting the workers.
    import commands
    commands._sync_all_existing_tunnels(restart_running=False)
    import state
    for name, tunnel in state.list_tunnels().items():
        if state.is_worker_locked(name) and not tunnel.get('admin_stopped'):
            commands._stop_tunnel(name, tunnel)
            state.update_tunnel(name, admin_stopped=0, status='starting')
            commands._spawn_worker(name)
    if args.watchdog:
        import launchd
        print(launchd.install())
    print(f'Installed {wrapper}. Backup: {backup}')


if __name__ == '__main__':
    main()
