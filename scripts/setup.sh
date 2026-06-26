#!/bin/bash
# chioff-rns initial server setup
# Run once as ubuntu after first boot.
set -e

echo "==> Installing system deps"
sudo apt-get update -q
sudo apt-get install -y python3 python3-pip python3-venv tmux git

echo "==> Creating rns user"
sudo useradd -m -s /bin/bash rns || true

echo "==> Installing RNS, LXMF, NomadNet as rns user"
sudo -u rns pip3 install --user rns lxmf nomadnet

echo "==> Deploying reticulum config"
sudo mkdir -p /etc/reticulum
sudo cp reticulum/config/reticulum.config /etc/reticulum/config
sudo cp reticulum/config/nomadnet.config /etc/reticulum/nomadnetconfig
sudo chown -R rns:rns /etc/reticulum

echo "==> Installing systemd units"
sudo cp systemd/rnsd.service /etc/systemd/system/
sudo cp systemd/lxmd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rnsd lxmd nomadnet
sudo systemctl start rnsd lxmd nomadnet

echo "==> Opening firewall port 4242"
sudo ufw allow 4242/tcp comment "Reticulum TCP"
sudo ufw allow OpenSSH
sudo ufw --force enable

echo "Done. Run: sudo -u rns bash scripts/tmux-session.sh attach"
