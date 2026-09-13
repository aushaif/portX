"""
FRP TOML configuration generator.

Generates temporary frpc TOML files for each tunnel type.
Users never interact with these files — they are created, used, and deleted
automatically by the PortX CLI.

Uses FRP v0.52+ TOML format.
"""

from __future__ import annotations

from pathlib import Path
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
        f'serverAddr = "{host}"\n'
        f"serverPort = {port}\n"
        'auth.method = "token"\n'
        f'auth.token = "{auth_token}"\n'
        "\n"
        "[transport]\n"
        "heartbeatInterval = 30\n"          # probe server every 30 s
        "heartbeatTimeout  = 90\n"          # reconnect if no reply for 90 s
        "tcpMuxKeepaliveInterval = 30\n"    # TCP-level keepalive every 30 s
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
    frps_host: str | None = None,
    frps_port: int | None = None,
) -> str:
    """Generate frpc TOML for an HTTP tunnel."""
    host = frps_host or _cfg.get_frps_host()
    port = frps_port or _cfg.get_frps_port()
    return (
        _base(host, port)
        + "[[proxies]]\n"
        + f'name      = "{proxy_name}"\n'
        + 'type      = "http"\n'
        + f'localIP   = "{local_host}"\n'
        + f"localPort = {local_port}\n"
        + f'subdomain = "{subdomain}"\n'
    )


def generate_tcp_config(
    *,
    local_host: str,
    local_port: int,
    remote_port: int,
    proxy_name: str,
    frps_host: str | None = None,
    frps_port: int | None = None,
) -> str:
    """Generate frpc TOML for a TCP tunnel."""
    host = frps_host or _cfg.get_frps_host()
    port = frps_port or _cfg.get_frps_port()
    return (
        _base(host, port)
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
    frps_host: str | None = None,
    frps_port: int | None = None,
) -> str:
    """Generate frpc TOML for a UDP tunnel."""
    host = frps_host or _cfg.get_frps_host()
    port = frps_port or _cfg.get_frps_port()
    return (
        _base(host, port)
        + "[[proxies]]\n"
        + f'name       = "{proxy_name}"\n'
        + 'type       = "udp"\n'
        + f'localIP    = "{local_host}"\n'
        + f"localPort  = {local_port}\n"
        + f"remotePort = {remote_port}\n"
    )


def generate_config_for_tunnel(
    tunnel_name: str,
    tunnel_data: dict,
    frps_host: str | None = None,
    frps_port: int | None = None,
) -> str:
    """Generate the full frpc TOML config for any saved tunnel dict."""
    t_type     = tunnel_data.get("type", "http")
    local_host = tunnel_data.get("local_host", "127.0.0.1")
    local_port = int(tunnel_data.get("local_port", 0))
    proxy_name = tunnel_data.get("proxy_name") or f"portx-{t_type}-{tunnel_name}"
    host       = frps_host or _cfg.get_frps_host()
    port       = frps_port or _cfg.get_frps_port()

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
        )
    else:  # udp
        remote_port = int(tunnel_data.get("remote_port", 0))
        return generate_udp_config(
            local_host=local_host,
            local_port=local_port,
            remote_port=remote_port,
            proxy_name=proxy_name,
            frps_host=host,
            frps_port=port,
        )


def sync_tunnel_config_file(
    config_path: Path | str,
    tunnel_name: str,
    tunnel_data: dict,
    force: bool = False,
) -> bool:
    """
    Ensure config_path exists and matches current frps_host, frps_port, auth_token,
    and tunnel proxy configuration.
    Returns True if the file was created or rewritten, False if already up-to-date.
    """
    p = Path(config_path)
    expected_host = _cfg.get_frps_host()
    expected_port = _cfg.get_frps_port()
    expected_token = _cfg.get_auth_token()

    if not force and p.is_file():
        try:
            content = p.read_text("utf-8")
            has_host  = f'serverAddr = "{expected_host}"' in content
            has_port  = f'serverPort = {expected_port}' in content
            has_token = f'auth.token = "{expected_token}"' in content
            if has_host and has_port and has_token:
                return False
        except Exception:
            pass

    toml = generate_config_for_tunnel(
        tunnel_name, tunnel_data, frps_host=expected_host, frps_port=expected_port
    )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(toml, "utf-8")
    return True
