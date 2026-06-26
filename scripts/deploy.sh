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

echo "==> Deploying landing page"
sudo mkdir -p /srv/rns-landing
sudo cp rns-landing/index.html /srv/rns-landing/index.html

echo "==> Restarting services"
sudo systemctl restart rnsd lxmd nomadnet

echo "Deploy done."
