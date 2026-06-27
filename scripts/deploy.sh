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

echo "==> Updating status generator"
sudo -u rns pip3 install --user -q -r requirements.txt
sudo cp systemd/chioff-status.service /etc/systemd/system/
sudo cp systemd/chioff-status.timer /etc/systemd/system/
sudo mkdir -p /var/lib/chicagooffline-rns
sudo chown -R rns:rns /var/lib/chicagooffline-rns
if [ ! -f /etc/chioff-status.config ]; then
  sudo cp status.config.example /etc/chioff-status.config
fi
sudo systemctl daemon-reload
sudo systemctl enable --now chioff-status.timer

echo "==> Deploying landing page"
sudo mkdir -p /srv/rns-landing
sudo cp rns-landing/index.html /srv/rns-landing/index.html
sudo cp reticulum/pages/*.mu /home/rns/.nomadnetwork/storage/pages/
sudo chown -R rns:rns /home/rns/.nomadnetwork/storage/pages

echo "==> Restarting services"
sudo systemctl restart rnsd lxmd nomadnet

echo "==> Regenerating status page"
sudo systemctl start chioff-status.service || true

echo "Deploy done."
