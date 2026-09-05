#!/usr/bin/env python3
"""
Unit tests for custom public port support (--p / --port) and --s subdomain flag.
"""

import sys
import unittest
from pathlib import Path

# Add cli and server to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "cli"))
sys.path.insert(0, str(REPO_ROOT / "server"))

import frp_config
import portx_server


class TestCustomPortParsing(unittest.TestCase):
    def setUp(self):
        import argparse
        # Configure identical to portx.py subparsers
        self.parser = argparse.ArgumentParser(prog="portx")
        subparsers = self.parser.add_subparsers(dest="command")

        p_http = subparsers.add_parser("http")
        p_http.add_argument("local_address")
        p_http.add_argument("name", nargs="?")
        p_http.add_argument("-s", "--s", "--subdomain", dest="subdomain")

        p_https = subparsers.add_parser("https")
        p_https.add_argument("local_address")
        p_https.add_argument("name", nargs="?")
        p_https.add_argument("-s", "--s", "--subdomain", dest="subdomain")

        p_tcp = subparsers.add_parser("tcp")
        p_tcp.add_argument("local_address")
        p_tcp.add_argument("name", nargs="?")
        p_tcp.add_argument("-p", "--p", "--port", dest="public_port", type=int)

        p_udp = subparsers.add_parser("udp")
        p_udp.add_argument("local_address")
        p_udp.add_argument("name", nargs="?")
        p_udp.add_argument("-p", "--p", "--port", dest="public_port", type=int)

    def test_tcp_double_dash_p(self):
        args = self.parser.parse_args(["tcp", "192.168.0.9:25565", "--p", "25565"])
        self.assertEqual(args.command, "tcp")
        self.assertEqual(args.local_address, "192.168.0.9:25565")
        self.assertEqual(args.public_port, 25565)

    def test_tcp_double_dash_port(self):
        args = self.parser.parse_args(["tcp", "25565", "--port", "25565"])
        self.assertEqual(args.public_port, 25565)

    def test_tcp_single_dash_p(self):
        args = self.parser.parse_args(["tcp", "25565", "-p", "25565"])
        self.assertEqual(args.public_port, 25565)

    def test_udp_double_dash_p(self):
        args = self.parser.parse_args(["udp", "192.168.0.9:19132", "--p", "19132"])
        self.assertEqual(args.command, "udp")
        self.assertEqual(args.local_address, "192.168.0.9:19132")
        self.assertEqual(args.public_port, 19132)

    def test_http_double_dash_s(self):
        args = self.parser.parse_args(["http", "8080", "--s", "mycustomsub"])
        self.assertEqual(args.command, "http")
        self.assertEqual(args.subdomain, "mycustomsub")

    def test_https_double_dash_s(self):
        args = self.parser.parse_args(["https", "8080", "--s", "securesub"])
        self.assertEqual(args.command, "https")
        self.assertEqual(args.subdomain, "securesub")

    def test_tcp_no_custom_port(self):
        args = self.parser.parse_args(["tcp", "8080"])
        self.assertIsNone(args.public_port)


class TestServerAllocator(unittest.TestCase):
    def setUp(self):
        self.allocator = portx_server.TunnelAllocator()
        with self.allocator._lock:
            self.allocator._tunnels.clear()
            self.allocator._used_subdomains.clear()
            self.allocator._used_tcp_ports.clear()
            self.allocator._used_udp_ports.clear()

    def test_custom_tcp_port_allocation(self):
        info = self.allocator.allocate_tcp("192.168.0.9", 25565, req_port=25565)
        self.assertEqual(info["remote_port"], 25565)
        self.assertIn("25565", info["public_url"])
        self.assertIn(25565, self.allocator._used_tcp_ports)

        # Boundary ports 1 and 65000
        info_min = self.allocator.allocate_tcp("127.0.0.1", 1001, req_port=1)
        self.assertEqual(info_min["remote_port"], 1)
        info_max = self.allocator.allocate_tcp("127.0.0.1", 1002, req_port=65000)
        self.assertEqual(info_max["remote_port"], 65000)

    def test_custom_udp_port_allocation(self):
        info = self.allocator.allocate_udp("192.168.0.9", 19132, req_port=19132)
        self.assertEqual(info["remote_port"], 19132)
        self.assertIn("19132", info["public_url"])
        self.assertIn(19132, self.allocator._used_udp_ports)

    def test_protocol_independence(self):
        # TCP 25565 + UDP 25565 must both succeed simultaneously!
        tcp_info = self.allocator.allocate_tcp("192.168.0.9", 25565, req_port=25565)
        udp_info = self.allocator.allocate_udp("192.168.0.9", 25565, req_port=25565)
        self.assertEqual(tcp_info["remote_port"], 25565)
        self.assertEqual(udp_info["remote_port"], 25565)
        self.assertIn(25565, self.allocator._used_tcp_ports)
        self.assertIn(25565, self.allocator._used_udp_ports)

    def test_duplicate_tcp_port_rejected(self):
        self.allocator.allocate_tcp("192.168.0.9", 25565, req_port=25565)
        with self.assertRaises(RuntimeError) as ctx:
            self.allocator.allocate_tcp("127.0.0.1", 8080, req_port=25565)
        self.assertIn("already in use", str(ctx.exception))

    def test_duplicate_udp_port_rejected(self):
        self.allocator.allocate_udp("192.168.0.9", 19132, req_port=19132)
        with self.assertRaises(RuntimeError) as ctx:
            self.allocator.allocate_udp("127.0.0.1", 8080, req_port=19132)
        self.assertIn("already in use", str(ctx.exception))

    def test_invalid_port_range(self):
        # Ports below 1 or above 65000 must be rejected
        with self.assertRaises(RuntimeError):
            self.allocator.allocate_tcp("127.0.0.1", 8080, req_port=0)
        with self.assertRaises(RuntimeError):
            self.allocator.allocate_tcp("127.0.0.1", 8080, req_port=-1)
        with self.assertRaises(RuntimeError):
            self.allocator.allocate_tcp("127.0.0.1", 8080, req_port=65001)
        with self.assertRaises(RuntimeError):
            self.allocator.allocate_tcp("127.0.0.1", 8080, req_port=70000)

    def test_reserved_tcp_ports_rejected(self):
        # Critical system ports must be rejected for TCP
        for port in (22, 80, 443, 7000, 8765):
            with self.assertRaises(RuntimeError) as ctx:
                self.allocator.allocate_tcp("127.0.0.1", 8080, req_port=port)
            self.assertIn("reserved", str(ctx.exception))


class TestFrpConfigGeneration(unittest.TestCase):
    def test_tcp_config_remote_port(self):
        toml = frp_config.generate_tcp_config(
            local_host="192.168.0.9",
            local_port=25565,
            remote_port=25565,
            proxy_name="portx-tcp-25565",
            frps_host="portx.infinitynoob.lol",
            frps_port=7000,
        )
        self.assertIn("remotePort = 25565", toml)
        self.assertIn('type       = "tcp"', toml)
        self.assertIn('localIP    = "192.168.0.9"', toml)
        self.assertIn("localPort  = 25565", toml)

    def test_udp_config_remote_port(self):
        toml = frp_config.generate_udp_config(
            local_host="192.168.0.9",
            local_port=19132,
            remote_port=19132,
            proxy_name="portx-udp-19132",
            frps_host="portx.infinitynoob.lol",
            frps_port=7000,
        )
        self.assertIn("remotePort = 19132", toml)
        self.assertIn('type       = "udp"', toml)
        self.assertIn('localIP    = "192.168.0.9"', toml)
        self.assertIn("localPort  = 19132", toml)


class TestEditParsing(unittest.TestCase):
    def test_parse_remote_port_camel_and_snake(self):
        def parse_config(content: str):
            res = {}
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("=", 1)
                if len(parts) == 2:
                    k = parts[0].strip()
                    v = parts[1].split("#")[0].strip(' "\'')
                    if k in ("remotePort", "remote_port") and v.isdigit():
                        res["remote_port"] = int(v)
            return res

        # remotePort (camelCase as requested)
        res1 = parse_config('name = "mc"\ntype = "tcp"\nremotePort = 25565')
        self.assertEqual(res1.get("remote_port"), 25565)

        # remote_port (snake_case backwards-compatible)
        res2 = parse_config('name = "mc"\ntype = "tcp"\nremote_port = 19132')
        self.assertEqual(res2.get("remote_port"), 19132)


if __name__ == "__main__":
    unittest.main()
