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
