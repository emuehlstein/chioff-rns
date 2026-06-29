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
# Consider pinning these to known-good versions for reproducible nodes, e.g.
# rns==x.y.z lxmf==x.y.z nomadnet==x.y.z (jinja2 is pinned in requirements.txt).
sudo -u rns pip3 install --user rns lxmf nomadnet jinja2==3.1.6

echo "==> Allowing rns to read service logs (journalctl)"
sudo usermod -aG systemd-journal rns || true

echo "==> Deploying reticulum config"
sudo mkdir -p /etc/reticulum
sudo cp reticulum/config/reticulum.config /etc/reticulum/config
sudo cp reticulum/config/nomadnet.config /etc/reticulum/nomadnetconfig
sudo chown -R rns:rns /etc/reticulum

echo "==> Deploying lxmd config"
sudo mkdir -p /home/rns/.lxmd
sudo cp lxmd/config /home/rns/.lxmd/config
sudo chown -R rns:rns /home/rns/.lxmd

echo "==> Setting up status generator"
sudo mkdir -p /var/lib/chicagooffline-rns
sudo chown -R rns:rns /var/lib/chicagooffline-rns
sudo mkdir -p /home/rns/.nomadnetwork/storage/pages
sudo chown -R rns:rns /home/rns/.nomadnetwork
if [ ! -f /etc/chioff-status.config ]; then
  sudo cp status.config.example /etc/chioff-status.config
fi

echo "==> Installing systemd units"
sudo cp systemd/rnsd.service /etc/systemd/system/
sudo cp systemd/lxmd.service /etc/systemd/system/
sudo cp systemd/nomadnet.service /etc/systemd/system/
sudo cp systemd/chioff-status.service /etc/systemd/system/
sudo cp systemd/chioff-status.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rnsd lxmd nomadnet
sudo systemctl enable --now chioff-status.timer
sudo systemctl start rnsd lxmd nomadnet

echo "==> Opening firewall port 4242"
sudo ufw allow 4242/tcp comment "Reticulum TCP"
sudo ufw allow OpenSSH
sudo ufw --force enable

echo "Done. Run: sudo -u rns bash scripts/tmux-session.sh attach"
