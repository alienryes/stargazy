#!/bin/bash
# One-time setup for touch2-stargazing-display on a Raspberry Pi driving the
# Touch Display 2 via the framebuffer (/dev/fb0). Run once as: sudo bash setup.sh <username>
set -e

USER="${1:-operations}"

echo "==> Installing system packages..."
apt-get install -y fonts-dejavu-core python3-pil python3-numpy python3-requests python3-pip

echo "==> Ensuring $USER can write the framebuffer..."
adduser "$USER" video || true

echo "==> Freeing the framebuffer console (fbcon=map:2)..."
# Keep the text console off /dev/fb0 so it never overdraws the dashboard.
# The runtime fbcon-detach.service unbinds it at deploy time; this makes it
# stick across reboots regardless of KMS init ordering. Takes effect on reboot.
CMDLINE=/boot/firmware/cmdline.txt
if [ -f "$CMDLINE" ] && ! grep -q "fbcon=map:2" "$CMDLINE"; then
    sed -i '1 s/[[:space:]]*$//; 1 s/$/ fbcon=map:2/' "$CMDLINE"
    echo "    added fbcon=map:2 to $CMDLINE (reboot required)"
fi

echo "==> Adding sudoers rule for $USER..."
cat > /etc/sudoers.d/touch2-stargazing <<EOF
$USER ALL=(ALL) NOPASSWD: /usr/bin/cp /tmp/touch2-stargazing.service /tmp/fbcon-detach.service /etc/systemd/system/
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl daemon-reload
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable touch2-stargazing.service
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart touch2-stargazing.service
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable fbcon-detach.service
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start fbcon-detach.service
EOF
chmod 440 /etc/sudoers.d/touch2-stargazing

echo "==> Done. You can now run deploy.ps1 from Windows."
