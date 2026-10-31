"""
FRP TOML configuration generator.

Generates temporary frpc TOML files for each tunnel type.
Users never interact with these files — they are created, used, and deleted
automatically by the PortX CLI.

Uses FRP v0.52+ TOML format.
"""

from __future__ import annotations

from pathlib import Path
import json
import tempfile
import config as _cfg


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _base(frps_host: str | None = None, frps_port: int | None = None) -> str:
    """Common [server] section shared by all tunnel types.

    transport block ensures frpc actively probes the connection every
    30 s and gives up after 90 s of silence — so a silently-dead TCP
    connection (NAT timeout, ISP idle cutoff, VPS reboot) is detected
    and triggers an automatic reconnect instead of creating a zombie.
    tcpMuxKeepaliveInterval sends TCP-level keep-alives over the
    multiplexed connection to prevent NAT tables from expiring the
    underlying socket after a few minutes of idle traffic.
    """
    host = frps_host or _cfg.get_frps_host()
    port = frps_port or _cfg.get_frps_port()
    auth_token = _cfg.get_auth_token()
    return (
        f"serverAddr = {json.dumps(host)}\n"
        f"serverPort = {port}\n"
        'auth.method = "token"\n'
        f"auth.token = {json.dumps(auth_token)}\n"
        "\n"
        "[transport]\n"
        "heartbeatInterval = 30\n"          # probe server every 30 s
        "heartbeatTimeout  = 90\n"          # reconnect if no reply for 90 s
        "tcpMuxKeepaliveInterval = 30\n"    # TCP-level keepalive every 30 s
        "\n"
        "[log]\n"
        'level = "info"\n'
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
    frps_host: str | None = None,
    frps_port: int | None = None,
) -> str:
    """Generate frpc TOML for an HTTP tunnel."""
    host = frps_host or _cfg.get_frps_host()
    port = frps_port or _cfg.get_frps_port()
    return (
        _base(host, port)
        + "[[proxies]]\n"
        + f"name      = {json.dumps(proxy_name)}\n"
        + 'type      = "http"\n'
        + f"localIP   = {json.dumps(local_host)}\n"
        + f"localPort = {local_port}\n"
        + f"subdomain = {json.dumps(subdomain)}\n"
    )


def normalize_proxy_protocol(val: str | bool | None) -> str | None:
    """Normalize user input to 'v1', 'v2', or None."""
    if not val:
        return None
    if isinstance(val, bool):
        return "v2" if val else None
    s = str(val).strip().lower()
    if s in ("v2", "2", "true", "yes", "on"):
        return "v2"
    if s in ("v1", "1"):
        return "v1"
    return None


def generate_tcp_config(
    *,
    local_host: str,
    local_port: int,
    remote_port: int,
    proxy_name: str,
    frps_host: str | None = None,
    frps_port: int | None = None,
    proxy_protocol: str | bool | None = None,
) -> str:
    """Generate frpc TOML for a TCP tunnel.

    proxy_protocol: None (disabled), 'v1', or 'v2'.
      When set, frpc injects a PROXY protocol header into each new connection
      so the backend server can read the real client IP instead of 127.0.0.1.
      The backend (e.g. Minecraft + Paper proxy-protocol or plugin) must support it.
    """
    host = frps_host or _cfg.get_frps_host()
    port = frps_port or _cfg.get_frps_port()
    pp = normalize_proxy_protocol(proxy_protocol)
    toml = (
        _base(host, port)
        + "[[proxies]]\n"
        + f"name       = {json.dumps(proxy_name)}\n"
        + 'type       = "tcp"\n'
        + f"localIP    = {json.dumps(local_host)}\n"
        + f"localPort  = {local_port}\n"
        + f"remotePort = {remote_port}\n"
    )
    if pp:
        toml += f'transport.proxyProtocolVersion = "{pp}"\n'
    return toml


def generate_udp_config(
    *,
    local_host: str,
    local_port: int,
    remote_port: int,
    proxy_name: str,
    frps_host: str | None = None,
    frps_port: int | None = None,
    proxy_protocol: str | bool | None = None,
) -> str:
    """Generate frpc TOML for a UDP tunnel.

    proxy_protocol: None (disabled), 'v1', or 'v2'.
      When set, frpc injects a PROXY protocol header (v2) into incoming UDP datagrams
      so the backend (e.g. GeyserMC with enable-proxy-protocol: true) receives
      the real client IP instead of 127.0.0.1 or the local proxy IP.
    """
    host = frps_host or _cfg.get_frps_host()
    port = frps_port or _cfg.get_frps_port()
    pp = normalize_proxy_protocol(proxy_protocol)
    toml = (
        _base(host, port)
        + "[[proxies]]\n"
        + f"name       = {json.dumps(proxy_name)}\n"
        + 'type       = "udp"\n'
        + f"localIP    = {json.dumps(local_host)}\n"
        + f"localPort  = {local_port}\n"
        + f"remotePort = {remote_port}\n"
    )
    if pp:
        toml += f'transport.proxyProtocolVersion = "{pp}"\n'
    return toml


def generate_config_for_tunnel(
    tunnel_name: str,
    tunnel_data: dict,
    frps_host: str | None = None,
    frps_port: int | None = None,
) -> str:
    """Generate the full frpc TOML config for any saved tunnel dict.

    Reads the optional 'proxy_protocol' field from tunnel_data so that
    tunnels configured with real-IP forwarding persist it across restarts.
    """
    t_type        = tunnel_data.get("type", "http")
    local_host    = tunnel_data.get("local_host", "127.0.0.1")
    local_port    = int(tunnel_data.get("local_port", 0))
    proxy_name    = tunnel_data.get("proxy_name") or f"portx-{t_type}-{tunnel_name}"
    host          = frps_host or _cfg.get_frps_host()
    port          = frps_port or _cfg.get_frps_port()
    proxy_protocol = tunnel_data.get("proxy_protocol") or None  # None | 'v1' | 'v2'

    if t_type == "http":
        subdomain = tunnel_data.get("subdomain", "")
        return generate_http_config(
            local_host=local_host,
            local_port=local_port,
            subdomain=subdomain,
            proxy_name=proxy_name,
            frps_host=host,
            frps_port=port,
        )
    elif t_type == "tcp":
        remote_port = int(tunnel_data.get("remote_port", 0))
        return generate_tcp_config(
            local_host=local_host,
            local_port=local_port,
            remote_port=remote_port,
            proxy_name=proxy_name,
            frps_host=host,
            frps_port=port,
            proxy_protocol=proxy_protocol,
        )
    elif t_type == "udp":
        remote_port = int(tunnel_data.get("remote_port", 0))
        return generate_udp_config(
            local_host=local_host,
            local_port=local_port,
            remote_port=remote_port,
            proxy_name=proxy_name,
            frps_host=host,
            frps_port=port,
            proxy_protocol=proxy_protocol,
        )

    raise ValueError(f"Unknown tunnel type: {t_type}")


def sync_tunnel_config_file(
    config_path: Path | str,
    tunnel_name: str,
    tunnel_data: dict,
    force: bool = False,
) -> bool:
    """
    Ensure config_path exists and matches current frps_host, frps_port, auth_token,
    proxy_protocol setting, and tunnel proxy configuration.
    Returns True if the file was created or rewritten, False if already up-to-date.
    """
    p = Path(config_path)
    toml = generate_config_for_tunnel(tunnel_name, tunnel_data)
    if not force and p.is_file() and p.read_text("utf-8") == toml:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=p.parent,
                                     prefix=p.name + ".", delete=False) as fd:
        tmp = Path(fd.name)
        fd.write(toml)
    try:
        tmp.replace(p)
    finally:
        tmp.unlink(missing_ok=True)
    return True
