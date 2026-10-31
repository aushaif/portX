import os
import sys
import tempfile
import unittest
import time
import threading
import subprocess
import signal
import json
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TEMP = tempfile.TemporaryDirectory(prefix='portx-tests-')
os.environ['HOME'] = TEMP.name
os.environ['PORTX_STATE_FILE'] = str(Path(TEMP.name) / 'server-state.json')
os.environ['PORTX_AUTH_TOKEN'] = 'test-secret'
sys.path[:0] = [str(ROOT / 'cli'), str(ROOT / 'server')]
import config
import state
import frp_config
import frp_runner
import portx_server as server
import commands
import portx as client
import io
from contextlib import redirect_stdout


def tearDownModule():
    TEMP.cleanup()


class ConfigTests(unittest.TestCase):
    def test_retired_domain_only(self):
        self.assertEqual(config._migrate_legacy_value('http://server.infinitynoob.lol:8765'),
                         'http://server.infinitynoob.space:8765')
        self.assertEqual(config._migrate_legacy_value('https://infinitynoob.lol.evil.test'),
                         'https://infinitynoob.lol.evil.test')

    def test_complete_config_sync_and_secret_escaping(self):
        path = Path(TEMP.name) / 'sync.toml'
        tunnel = dict(type='http', local_host='127.0.0.1', local_port=8080, subdomain='first')
        with patch.object(config, 'get_auth_token', return_value='token"\\value'):
            self.assertTrue(frp_config.sync_tunnel_config_file(path, 'example', tunnel))
            self.assertFalse(frp_config.sync_tunnel_config_file(path, 'example', tunnel))
            tunnel.update(local_port=9090, subdomain='second')
            self.assertTrue(frp_config.sync_tunnel_config_file(path, 'example', tunnel))
            import tomllib
            data = tomllib.loads(path.read_text())
            self.assertEqual(data['proxies'][0]['localPort'], 9090)
            self.assertEqual(data['proxies'][0]['subdomain'], 'second')
            self.assertEqual(data['auth']['token'], 'token"\\value')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_name_cannot_escape_state_directory(self):
        with self.assertRaises(ValueError):
            state.update_tunnel('../escape', status='starting')


class CLITests(unittest.TestCase):
    def test_auto_start_default_and_explicit_opt_out(self):
        for kind in ('http', 'https', 'tcp', 'udp'):
            for flags, enabled in [([], True), (['--auto-start'], True), (['--no-auto-start'], False)]:
                with self.subTest(kind=kind, flags=flags), \
                     patch.object(sys, 'argv', ['portx', kind, '8080'] + flags), \
                     patch.object(client, '_start_tunnel') as start:
                    client.main()
                    self.assertEqual(start.call_args.kwargs['auto_start'], enabled)


class EditTests(unittest.TestCase):
    def test_local_backend_edit_preserves_allocation(self):
        name = 'edit-backend'
        cfg = state.CONFIGS_DIR / (name + '.toml')
        state.update_tunnel(name, type='http', local_host='127.0.0.1', local_port=8080,
                            subdomain='unchanged', proxy_name='portx-http-unchanged',
                            public_url='https://unchanged.infinitynoob.space', tunnel_id='stable',
                            frp_config_path=str(cfg), log_path=str(state.LOGS_DIR / (name+'.log')),
                            status='stopped', auto_start=1)
        def edit(args):
            p = Path(args[-1])
            p.write_text(p.read_text().replace('local_port = 8080', 'local_port = 9090'))
        with patch.object(commands.subprocess, 'run', side_effect=edit), \
             patch.object(commands._api, 'request_tunnel') as request, redirect_stdout(io.StringIO()):
            commands.cmd_edit(name)
        request.assert_not_called()
        record = state.get_tunnel(name)
        self.assertEqual(record['local_port'], 9090)
        self.assertEqual(record['tunnel_id'], 'stable')
        self.assertEqual(record['auto_start'], 1)

    def test_rename_cannot_overwrite_another_tunnel(self):
        name = 'edit-rename'
        state.update_tunnel(name, type='http', local_port=8080, subdomain='rename', status='stopped')
        state.update_tunnel('existing', type='tcp', local_port=9000, status='stopped')
        def edit(args):
            p = Path(args[-1])
            p.write_text(p.read_text().replace('name = "edit-rename"', 'name = "existing"'))
        with patch.object(commands.subprocess, 'run', side_effect=edit), redirect_stdout(io.StringIO()):
            commands.cmd_edit(name)
        self.assertEqual(state.get_tunnel('existing')['local_port'], 9000)
        self.assertEqual(state.get_tunnel(name)['local_port'], 8080)


class RunnerTests(unittest.TestCase):
    def fake(self, code):
        path = Path(TEMP.name) / 'fake-frpc'
        path.write_text('#!' + sys.executable + '\n' + code)
        path.chmod(0o700)
        return path

    def test_requires_proxy_confirmation(self):
        binary = self.fake("import time\nprint('login to server success', flush=True)\ntime.sleep(5)\n")
        with self.assertRaisesRegex(frp_runner.FRPError, 'Timed out'):
            frp_runner.start_frpc(Path('unused'), binary, timeout=0.15)

    def test_conflict_after_login_is_failure(self):
        binary = self.fake("import time\nprint('login to server success', flush=True)\nprint('start error: proxy name conflict', flush=True)\ntime.sleep(5)\n")
        with self.assertRaisesRegex(frp_runner.FRPError, 'conflict'):
            frp_runner.start_frpc(Path('unused'), binary, timeout=1)

    def test_success_and_reader_handoff(self):
        binary = self.fake("import time\nprint('start proxy success', flush=True)\ntime.sleep(0.2)\nprint('after-start', flush=True)\ntime.sleep(5)\n")
        proc = frp_runner.start_frpc(Path('unused'), binary, timeout=1)
        try:
            self.assertEqual(proc.stdout.readline().strip(), 'after-start')
        finally:
            frp_runner.stop_frpc(proc)
            proc.stdout.close()


class WorkerLifecycleTests(unittest.TestCase):
    def test_worker_survives_terminal_group_hangup(self):
        fake = Path(TEMP.name) / 'worker-frpc'
        fake.write_text('#!' + sys.executable + "\nimport time\nprint('start proxy success', flush=True)\ntime.sleep(60)\n")
        fake.chmod(0o700)
        name = 'lifecycle'
        state.update_tunnel(name, type='http', local_port=8080, subdomain='lifecycle',
                            frp_config_path=str(state.CONFIGS_DIR / 'lifecycle.toml'),
                            log_path=str(state.LOGS_DIR / 'lifecycle.log'),
                            status='starting', admin_stopped=0)
        pidfile = Path(TEMP.name) / 'worker.pid'
        parent_code = (
            'import subprocess,sys,time; from pathlib import Path; '
            'p=subprocess.Popen([sys.executable,sys.argv[1],"lifecycle"],'
            'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True); '
            'Path(sys.argv[2]).write_text(str(p.pid)); time.sleep(60)'
        )
        env = dict(os.environ, PORTX_FRP_BINARY=str(fake))
        parent = subprocess.Popen([sys.executable, '-c', parent_code, str(ROOT/'cli/worker.py'), str(pidfile)],
                                  env=env, start_new_session=True)
        worker_pid = 0
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if pidfile.exists():
                    worker_pid = int(pidfile.read_text())
                if state.load_tunnels().get(name, {}).get('status') == 'running':
                    break
                time.sleep(0.05)
            self.assertEqual(state.load_tunnels()[name]['status'], 'running')
            os.killpg(parent.pid, signal.SIGHUP)
            parent.wait(timeout=3)
            os.kill(worker_pid, signal.SIGHUP)
            time.sleep(0.2)
            self.assertTrue(state.is_pid_alive(worker_pid))
            self.assertTrue(state.is_worker_locked(name))
        finally:
            if parent.poll() is None:
                parent.terminate()
                parent.wait(timeout=3)
            if worker_pid and state.is_pid_alive(worker_pid):
                os.kill(worker_pid, signal.SIGTERM)
                deadline = time.monotonic() + 6
                while time.monotonic() < deadline and state.is_worker_locked(name):
                    time.sleep(0.05)
            self.assertFalse(state.is_worker_locked(name))


class AllocatorTests(unittest.TestCase):
    def setUp(self):
        server.STATE_FILE = Path(TEMP.name) / f'{self.id()}.json'
        self.allocator = server.TunnelAllocator()

    def test_restart_preserves_domain_and_grace_period(self):
        info = self.allocator.allocate_http('127.0.0.1', 5678, 'n8n')
        self.allocator._tunnels[info['tunnel_id']]['last_seen'] = 0
        self.allocator._save_state()
        restored = server.TunnelAllocator()
        self.assertEqual(restored.release_stale(600), [])
        self.assertEqual(restored.get_info(info['tunnel_id'])['public_url'], 'https://n8n.infinitynoob.space')
        self.assertTrue(restored.permits_hostname('n8n.infinitynoob.space'))
        self.assertFalse(restored.permits_hostname('evil.example.com'))

    def test_reclaim_same_allocation_after_loss(self):
        req = dict(type='tcp', local_host='127.0.0.1', local_port=3000, remote_port=30010)
        info = self.allocator.reregister('dead-beef', req)
        self.assertEqual(info['remote_port'], 30010)
        self.assertEqual(self.allocator.reregister('dead-beef', req)['proxy_name'], info['proxy_name'])

    def test_reaper_frees_only_expired_allocations(self):
        old = self.allocator.allocate_http('127.0.0.1', 80, 'old')
        active = self.allocator.allocate_http('127.0.0.1', 80, 'active')
        self.allocator._tunnels[old['tunnel_id']]['last_seen'] = 0
        self.assertEqual(self.allocator.release_stale(600), [old['tunnel_id']])
        self.assertIsNotNone(self.allocator.get_info(active['tunnel_id']))

    def test_reclaim_validation(self):
        for req in [dict(type='http', local_port=80, subdomain='a.b'),
                    dict(type='http', local_port=80, subdomain='server'),
                    dict(type='tcp', local_port=80, remote_port=443),
                    dict(type='udp', local_port=80, remote_port=65536)]:
            with self.subTest(req=req), self.assertRaises(ValueError):
                server._validate_request(req, reclaim=True)


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.AUTH_TOKEN = 'test-secret'
        server.STATE_FILE = Path(TEMP.name) / 'http-state.json'
        server._allocator = server.TunnelAllocator()
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.PortXHandler)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    def request(self, path, body=None, token=None):
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, exc.read()

    def test_auth_invalid_bodies_and_tls_allow(self):
        self.assertEqual(self.request('/health')[0], 200)
        self.assertEqual(self.request('/api/v1/tunnel', {})[0], 401)
        for body in [[], {'type': ['http']}, {'type': 'http', 'local_port': True}]:
            self.assertEqual(self.request('/api/v1/tunnel', body, 'test-secret')[0], 400)
        code, raw = self.request('/api/v1/tunnel', dict(type='http', local_port=8080, subdomain='test'), 'test-secret')
        self.assertEqual(code, 200)
        self.assertEqual(self.request('/api/v1/tls/allow?domain=test.infinitynoob.space')[0], 200)
        self.assertEqual(self.request('/api/v1/tls/allow?domain=evil.example')[0], 403)


if __name__ == '__main__':
    unittest.main()
