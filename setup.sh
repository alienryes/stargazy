#!/bin/bash
# One-time setup for touch2-stargazing-display on Pi Zero 2W.
# Run once as: sudo bash setup.sh <username>
set -e

USER="${1:-operations}"

echo "==> Installing system packages..."
apt-get install -y fonts-dejavu-core python3-spidev python3-rpi.gpio python3-pil python3-requests python3-pip

echo "==> Adding sudoers rule for $USER..."
cat > /etc/sudoers.d/touch2-stargazing <<EOF
$USER ALL=(ALL) NOPASSWD: /usr/bin/cp /tmp/touch2-stargazing.service /etc/systemd/system/touch2-stargazing.service
$USER ALL=(ALL) NOPASSWD: /usr/bin/cp /tmp/touch2-stargazing.timer /etc/systemd/system/touch2-stargazing.timer
$USER ALL=(ALL) NOPASSWD: /usr/bin/cp /tmp/touch2-stargazing.service /tmp/touch2-stargazing.timer /etc/systemd/system/
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl daemon-reload
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable touch2-stargazing.timer
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart touch2-stargazing.timer
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart touch2-stargazing
EOF
chmod 440 /etc/sudoers.d/touch2-stargazing

echo "==> Done. You can now run deploy.ps1 from Windows."
