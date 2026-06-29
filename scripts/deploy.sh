#!/bin/bash
# CI deploy script — runs on the server via GitHub Actions
set -e

REPO_DIR="/opt/chioff-rns"

echo "==> Pulling latest"
cd "$REPO_DIR"
git fetch origin main
git reset --hard origin/main

echo "==> Updating RNS config"
sudo cp reticulum/config/reticulum.config /etc/reticulum/config
sudo cp reticulum/config/nomadnet.config /etc/reticulum/nomadnetconfig
sudo chown -R rns:rns /etc/reticulum

echo "==> Updating lxmd config"
sudo mkdir -p /home/rns/.lxmd
sudo cp lxmd/config /home/rns/.lxmd/config
sudo chown -R rns:rns /home/rns/.lxmd

echo "==> Updating status generator"
sudo -u rns python3 -m pip install --user -q --break-system-packages -r requirements.txt
sudo cp systemd/chioff-status.service /etc/systemd/system/
sudo cp systemd/chioff-status.timer /etc/systemd/system/
sudo mkdir -p /var/lib/chicagooffline-rns
sudo chown -R rns:rns /var/lib/chicagooffline-rns
if [ ! -f /etc/chioff-status.config ]; then
  sudo cp status.config.example /etc/chioff-status.config
fi
# Consent allowlist is repo-managed (edit consented-nodes.config) so deploy
# always refreshes it. Nodes here are shown un-anonymized on the public page.
sudo cp consented-nodes.config /etc/chioff-consent.config
sudo systemctl daemon-reload
sudo systemctl enable --now chioff-status.timer

echo "==> Deploying landing page"
sudo mkdir -p /srv/rns-landing
sudo cp rns-landing/index.html /srv/rns-landing/index.html
sudo cp rns-landing/visualizer.html /srv/rns-landing/visualizer.html
# Serve the live status snapshot to the Network Visualizer (read-only symlink).
sudo ln -sf /var/lib/chicagooffline-rns/status.json /srv/rns-landing/status.json
sudo cp reticulum/pages/*.mu /home/rns/.nomadnetwork/storage/pages/
sudo chown -R rns:rns /home/rns/.nomadnetwork/storage/pages

echo "==> Restarting services"
sudo systemctl restart rnsd lxmd nomadnet

echo "==> Regenerating status page"
sudo systemctl start chioff-status.service || true

echo "Deploy done."
