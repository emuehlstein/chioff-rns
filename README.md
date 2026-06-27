# chioff-rns

Reticulum Network Stack node for Chicago Offline.

- **rnsd** — transport node, TCP server on port 4242
- **lxmd** — LXMF propagation daemon
- **nomadnet** — NomadNet node (headless, managed via tmux)

## Server

`rns.chicagooffline.com` / `rns.chioff.com`

## Connect

```
rnsd --config /etc/reticulum
# or via TCP client:
# target: rns.chicagooffline.com:4242
```

## Tmux session

```bash
sudo -u rns bash scripts/tmux-session.sh attach
```

Windows: `rnsd` logs | `lxmd` logs | `nomadnet` TUI | `shell`

## Initial setup

```bash
git clone git@github.com:emuehlstein/chioff-rns.git /opt/chioff-rns
cd /opt/chioff-rns
bash scripts/setup.sh
```

## Deploy

Push to `main` → GitHub Actions SSHes in and runs `scripts/deploy.sh`.

Secrets needed in repo: `RNS_SSH_HOST`, `RNS_SSH_KEY`.

## Status page

A periodically generated NomadNet page reports live node health at
`/page/status.mu` (linked from the home page).

- **Collector** — `status/collectors.py` gathers data from `rnstatus`,
  `rnpath --table`, `journalctl -u rnsd`, `systemctl`, `ss` (TCP port 4242),
  and `/proc`. Output is a plain JSON-serializable snapshot, so the same
  collection layer can later feed FastAPI, Prometheus, or Grafana.
- **History** — optional SQLite store (`status/history.py`) tracks path
  first-seen times ("new paths in the last hour"), recent events, and a raw
  snapshot archive.
- **Renderer** — `status/render.py` + `status/templates/status.mu.j2` produce
  the micron `.mu` page with Jinja2.
- **Outputs** —
  - page: `/home/rns/.nomadnetwork/storage/pages/status.mu`
  - JSON: `/var/lib/chicagooffline-rns/status.json`
- **Schedule** — `chioff-status.timer` runs the generator every minute.

### Configuration

Settings live in `/etc/chioff-status.config` (copied from
[status.config.example](status.config.example) on first setup). Key option:

```
[general]
public_mode = true   # truncate peer IPs (203.0.x.x) and hashes on the public page
```

Set `public_mode = false` only for a locally served operator view that shows
full IPs and destination hashes.

### Run manually

```bash
cd /opt/chioff-rns
python3 -m status.generate --config /etc/chioff-status.config        # write JSON + page
python3 -m status.generate --dry-run --print                        # render to stdout, no writes
python3 -m status.generate --json                                   # dump snapshot JSON
```

### Limitations

- **Peer attribution** (which transport peer imported which destinations) is
  **not yet instrumented** — Reticulum does not expose this through
  `rnstatus`/`rnpath`. The page says so explicitly. Future work: hook Reticulum
  path learning to attribute imported destinations per peer.
- **Announce counts** depend on `rnsd` log verbosity; if `journalctl` has no
  announce lines the page shows "not instrumented" rather than a wrong number.

