"""
FRP TOML configuration generator.

Generates temporary frpc TOML files for each tunnel type.
Users never interact with these files — they are created, used, and deleted
automatically by the PortX CLI.

Uses FRP v0.52+ TOML format.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _base(frps_host: str, frps_port: int) -> str:
    """Common [server] section shared by all tunnel types."""
    return (
        f'serverAddr = "{frps_host}"\n'
        f"serverPort = {frps_port}\n"
        'auth.method = "token"\n'
        'auth.token = "k3rnel-p4nic"\n'
        "\n"
        "[log]\n"
        'level = "warn"\n'
        "\n"
    )


# ---------------------------------------------------------------------------
# Public generators
# ---------------------------------------------------------------------------

def generate_http_config(
    *,
    local_host: str,
    local_port: int,
    subdomain: str,
    proxy_name: str,
    frps_host: str,
    frps_port: int,
) -> str:
    """
    Generate frpc TOML for an HTTP tunnel.
    """
    base_toml = (
        _base(frps_host, frps_port)
        + "[[proxies]]\n"
        + f'name      = "{proxy_name}"\n'
        + 'type      = "http"\n'
        + f'localIP   = "{local_host}"\n'
        + f"localPort = {local_port}\n"
        + f'subdomain = "{subdomain}"\n'
    )
        
    return base_toml


def generate_tcp_config(
    *,
    local_host: str,
    local_port: int,
    remote_port: int,
    proxy_name: str,
    frps_host: str,
    frps_port: int,
) -> str:
    """
    Generate frpc TOML for a TCP tunnel.

    Example output:
      [[proxies]]
      name       = "portx-tcp-30125"
      type       = "tcp"
      localIP    = "127.0.0.1"
      localPort  = 25565
      remotePort = 30125
    """
    return (
        _base(frps_host, frps_port)
        + "[[proxies]]\n"
        + f'name       = "{proxy_name}"\n'
        + 'type       = "tcp"\n'
        + f'localIP    = "{local_host}"\n'
        + f"localPort  = {local_port}\n"
        + f"remotePort = {remote_port}\n"
    )


def generate_udp_config(
    *,
    local_host: str,
    local_port: int,
    remote_port: int,
    proxy_name: str,
    frps_host: str,
    frps_port: int,
) -> str:
    """
    Generate frpc TOML for a UDP tunnel.

    Example output:
      [[proxies]]
      name       = "portx-udp-32001"
      type       = "udp"
      localIP    = "127.0.0.1"
      localPort  = 7777
      remotePort = 32001
    """
    return (
        _base(frps_host, frps_port)
        + "[[proxies]]\n"
        + f'name       = "{proxy_name}"\n'
        + 'type       = "udp"\n'
        + f'localIP    = "{local_host}"\n'
        + f"localPort  = {local_port}\n"
        + f"remotePort = {remote_port}\n"
    )
