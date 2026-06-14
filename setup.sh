#!/bin/bash
# One-time setup for inky-stargazing-display on Pi Zero 2W.
# Run once as: sudo bash setup.sh <username>
set -e

USER="${1:-operations}"

echo "==> Installing system packages..."
apt-get install -y fonts-dejavu-core python3-spidev python3-rpi.gpio python3-pil python3-requests

echo "==> Adding sudoers rule for $USER..."
cat > /etc/sudoers.d/inky-stargazing <<EOF
$USER ALL=(ALL) NOPASSWD: /usr/bin/cp /tmp/inky-stargazing.service /etc/systemd/system/inky-stargazing.service
$USER ALL=(ALL) NOPASSWD: /usr/bin/cp /tmp/inky-stargazing.timer /etc/systemd/system/inky-stargazing.timer
$USER ALL=(ALL) NOPASSWD: /usr/bin/cp /tmp/inky-stargazing.service /tmp/inky-stargazing.timer /etc/systemd/system/
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl daemon-reload
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable inky-stargazing.timer
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart inky-stargazing.timer
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart inky-stargazing
EOF
chmod 440 /etc/sudoers.d/inky-stargazing

echo "==> Done. You can now run deploy.ps1 from Windows."
