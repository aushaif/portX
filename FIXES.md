# PortX repairs and current verification

The Desktop checkout, installed macOS CLI, and Ubuntu relay at
`ubuntu@140.245.224.53:/opt/frp` were inspected.

## Built-in recovery

A follow-up exposed a gap in the original hangup test: worker process survival
alone did not prove LAN connectivity after recovery. The old user LaunchAgent
restored Zima/Nextcloud workers, but those workers reported “no route to host”
for `192.168.0.8`. Interactive access to the same backend worked. Apple's Local
Network Privacy documentation explains the execution-context distinction.

At the user's request, the OS watchdog system has been removed entirely:

- `cli/supervisor.py` ships inside PortX and starts automatically with the CLI.
- One supervisor per user manages all tunnels; file locks prevent duplicates.
- The process double-forks into a detached session, closes terminal streams,
  and ignores terminal hangup, interrupt and termination signals.
- Recovery preserves URLs/allocations and respects explicit stops and recovery
  opt-out. Shutdown for upgrades/uninstall uses an explicit control file.
- No LaunchAgent, LaunchDaemon, separate download, sudo, or service installation
  is required. The obsolete watchdog commands/modules are removed.
- After an actual reboot, a normal PortX command resumes eligible saved tunnels.
  Nothing can run across a reboot without some startup mechanism.
- Backend health is reported separately from relay connectivity. Local service
  failures no longer cause unnecessary FRP reconnections.

## Other repairs retained

- Updated the deployed API's stale `.lol` defaults and client domain migration.
- Added Caddy TLS termination and certificate renewal in front of FRP's HTTP
  listener. Certificate authorization is restricted to allocated HTTP names.
- Removed the standalone API process conflicting with systemd on port 8765.
- Require explicit FRP proxy startup confirmation and use a single startup reader.
- Reclaim missing server allocations on startup and after 404 heartbeats.
- Synchronize complete tunnel configs with atomic writes and escaped secrets.
- Preserve allocations during backend edits and prevent rename collisions.
- Validate names, API bodies, subdomains, and reserved ports; authenticate API
  mutations. TCP/UDP use the DNS-only server hostname; API traffic uses HTTPS.

## Verification

- 18 regression tests passed, including shared supervisor singleton behavior,
  signal survival, automatic recovery, explicit stop and opt-out behavior,
  backend health, API/config/allocation checks, and edit safety.
- Live supervisor received SIGHUP and SIGTERM and retained the same PID.
- Terminated n8n, Zima and Nextcloud workers together. The supervisor restored
  all three with new PIDs and working LAN access.
- Public requests after that recovery returned HTTP 200 for n8n, Zima, and the
  Nextcloud login page (following its HTTPS redirect).
- Downtify's backend refuses connections; the user confirmed it is deliberately
  offline. Its configuration remains intact and it is shown as BACKEND DOWN.
- The old user-agent job/plist and installed watchdog modules are absent. No
  system PortX LaunchDaemon was installed.
- Python compilation, shell syntax checks, and `git diff --check` passed.
- Original server repair also passed live TCP/UDP echo and direct origin TLS
  certificate validation. This follow-up did not change the server configuration.

An ordinary Python HTTP probe received 403 during the live check; curl requests
consistently returned 200 for all three sites. That probe was not counted as a
successful browser/HTTP check.

## Operation and backups

- `portx status`: built-in supervisor and tunnel health.
- `portx stop <name>`: stop and suppress recovery until explicitly started again.
- `python3 scripts/install-local.py`: install this checkout without downloading
  the GitHub version. It preserves backups under `~/.portx/backups/`.
- Original VPS backup: `/opt/frp/backups/20261031T113912Z`.
- Follow-up client backup: `~/.portx/backups/20261101-000619`.
- Disabled old agent is retained only as a backup under
  `~/.portx/backups/legacy-watchdog.plist.disabled`.
- Regression command: `python3 -m unittest discover -s tests -v`.
- Client/backend must remain awake and connected. Actual OS reboot and Terminal
  GUI quit were not exercised; signal handling and live post-recovery LAN/HTTPS
  behavior were exercised. Linux client runtime was not exercised.
- Changes are installed locally; this follow-up has not been pushed to GitHub.

References: [Apple Local Network Privacy](https://developer.apple.com/documentation/technotes/tn3179-understanding-local-network-privacy),
[FRP HTTPS passthrough](https://gofrp.org/en/docs/examples/vhost-http/),
[Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).
