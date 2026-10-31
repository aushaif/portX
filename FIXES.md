# PortX repair and verification — 31 October 2026

The Desktop checkout, installed macOS CLI, and live Ubuntu deployment at
`ubuntu@140.245.224.53:/opt/frp` were inspected and updated.

## Root causes and repairs

- The live API loaded old `.lol` defaults, while local tunnel records already
  showed `.space`. Updated the deployed central config and migration of legacy
  client defaults/overrides. The API now advertises `server.infinitynoob.space`.
- FRP's HTTPS listener performs passthrough, not TLS termination. HTTP proxies
  therefore could not answer Cloudflare's origin TLS handshake. Caddy now owns
  ports 80/443, obtains and renews public certificates, and forwards to FRP HTTP
  on 8080. Its certificate authorization endpoint allows allocated HTTP names
  only. HTTP-01 challenges work through the existing Cloudflare proxy.
- A standalone API process held port 8765 while the systemd API service repeatedly
  crashed trying to bind it. Removed that conflicting process and restored the
  systemd service. The separate FRP instance serving other ports was preserved.
- Startup treated an alive frpc process as success, even without a functioning
  proxy; two competing stdout readers could also lose errors. Startup now waits
  for explicit proxy confirmation using a single reader, and reports failures.
- Missing server allocations produced endless 404 heartbeats without repair.
  Workers reclaim metadata at startup and after a 404, preserving the allocation
  where possible. Network errors no longer trigger replacement allocations.
- Added a macOS user LaunchAgent and installed it for the existing user. It runs
  independently of Terminal and restarts dead auto-start workers. Explicit stops
  disable recovery. New tunnels retain auto-start by default; opt out with
  `--no-auto-start`.
- Fixed stop/restart races with the watchdog, PID publication before worker lock
  acquisition, and stale PID status updates overwriting newer workers.
- Config sync now compares the complete generated configuration, including local
  target and subdomain. Uses unique atomic replacement files, owner-only secret
  file permissions, and properly escaped FRP string values.
- Backend edits retain existing allocations; renames cannot overwrite another
  tunnel. Reject unsafe tunnel names, malformed API bodies, invalid DNS labels,
  and reserved reclaim ports. API mutations require the configured relay token.
- TCP/UDP default to the DNS-only `server.infinitynoob.space` record rather than
  a Cloudflare-proxied hostname. API traffic now uses HTTPS.
- Added a local-checkout installer with backups, updated deployment scripts and
  documentation, and added regression tests.

## Verification

- 15 regression tests passed: API auth/validation, certificate authorization,
  restart grace period, stale reaping, config sync/escaping, name safety, backend
  edits/rename collisions, auto-start flags, startup failures, stdout handoff,
  and a real detached worker surviving process-group and direct SIGHUP.
- Live public `https://n8n.infinitynoob.space`: HTTP 200.
- Direct origin request with SNI and certificate verification: HTTP 200.
- Local n8n backend at `192.168.0.8:5678`: HTTP 200.
- Live TCP and UDP echo round trips through the VPS passed; temporary allocations
  were released. Final API health showed only the original n8n allocation.
- Deliberately terminated the n8n worker; launchd watchdog restored it with a new
  PID automatically. Watchdog and n8n were running after verification.
- Python compilation, shell syntax validation, FRP/Caddy config validation, and
  `git diff --check` passed.

## Backups and operation

- Original server files/state: `/opt/frp/backups/20261031T113912Z`.
- Original installed client/settings: `~/.portx/backups/20261031-171053`.
- macOS service: `~/Library/LaunchAgents/space.infinitynoob.portx.watchdog.plist`.
- Install this checkout again with `python3 scripts/install-local.py`.
- Run regression tests with `python3 -m unittest discover -s tests -v`.
- Tunnels require the client machine and backend to remain awake and reachable.
  User LaunchAgents start after login; recovery across an actual OS reboot was
  not exercised. Linux client service installation was not exercised.
- Port 80 and `/.well-known/acme-challenge/` must remain reachable for certificate
  renewal. New names can take several seconds to obtain their first certificate.
- Changes are local and deployed to this VPS, not published to GitHub. The remote
  GitHub installer will not contain them until the repository is updated.

References: [FRP HTTPS passthrough](https://gofrp.org/en/docs/examples/vhost-http/),
[Cloudflare 525](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-5xx-errors/error-525/),
[Caddy on-demand TLS](https://caddyserver.com/docs/automatic-https#on-demand-tls).
