#!/usr/bin/env bash
# Run on the VPS to terminate TLS and obtain/renew certificates automatically.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run with sudo.' >&2; exit 1; }
PORTX_DIR="${PORTX_DIR:-/opt/portx}"
FRPS_BINARY="${FRPS_BINARY:-/usr/local/bin/frps}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v caddy >/dev/null || { apt-get update -qq; apt-get install -y caddy; }
mkdir -p /etc/caddy
cp -p "$PORTX_DIR/frps.toml" "$PORTX_DIR/frps.toml.before-tls"
[ ! -f /etc/caddy/Caddyfile ] || cp -p /etc/caddy/Caddyfile /etc/caddy/Caddyfile.before-portx
python3 - "$PORTX_DIR" "$SCRIPT_DIR" <<'PY'
import json, re, sys
from pathlib import Path
root, source = map(Path, sys.argv[1:])
config = json.loads((root/'portx.config.json').read_text())
host = config['server']['frps_host']
if not re.fullmatch(r'[a-z0-9.-]+', host):
    raise SystemExit('Invalid server hostname')
Path('/etc/caddy/Caddyfile').write_text((source/'Caddyfile').read_text().replace('server.infinitynoob.space', host))
p = root/'frps.toml'
s = re.sub(r'^vhostHTTPPort\s*=.*$', 'vhostHTTPPort = 8080', p.read_text(), flags=re.M)
s = re.sub(r'^vhostHTTPSPort\s*=.*\n?', '', s, flags=re.M)
s = re.sub(r'^subDomainHost\s*=.*$', 'subDomainHost = ' + json.dumps(config['domains']['http']), s, flags=re.M)
p.write_text(s)
PY
"$FRPS_BINARY" verify -c "$PORTX_DIR/frps.toml"
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl restart frps
systemctl enable caddy
systemctl restart caddy
printf '%s\n' 'Origin TLS configured. Keep ports 80/443 reachable for certificate issuance. Cloudflare Full (strict) is supported.'
