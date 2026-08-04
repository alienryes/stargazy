#!/bin/bash
# Optional host hardening: key-only SSH and automatic security updates.
#
#   sudo bash harden-pi.sh [username]     # default: operations
#
# Neither change is required to run the display, and neither is done by
# setup.sh - they alter how you log into the machine, which is not something an
# application installer should decide for you. They are here because the README
# recommends both and advice you cannot act on is not much use.
#
# Safe by construction: it refuses to disable passwords unless a key is already
# installed, validates the sshd config before applying it, rolls back if that
# validation fails, and RELOADS rather than restarts sshd, so the session you
# are running this from survives either outcome.
#
# READ THIS FIRST: afterwards, root is reachable only via your SSH key plus
# your account password. If the Pi has no keyboard attached and you lose both,
# recovery means taking the SD card to another machine.
set -e

USER="${1:-operations}"
CONF=/etc/ssh/sshd_config.d/10-hardening.conf
KEYS="/home/$USER/.ssh/authorized_keys"

echo "==> Checking key-based login is viable before disabling passwords..."
if [ ! -s "$KEYS" ]; then
    echo "REFUSING: $KEYS is missing or empty - disabling passwords would lock you out." >&2
    echo "Copy your key over first (ssh-copy-id $USER@<host>) and rerun." >&2
    exit 1
fi
echo "    $(grep -c . "$KEYS") key(s) present in $KEYS"

echo "==> Disabling password authentication..."
cat > "$CONF" <<'EOF'
# Key-only SSH. Installed by harden-pi.sh.
# Named 10- so it is read before 50-cloud-init.conf: sshd keeps the FIRST value
# it obtains for each keyword, so the lowest-numbered file wins. A Pi imaged
# with Raspberry Pi Imager has a cloud-init file enabling passwords.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
chmod 644 "$CONF"

echo "==> Validating sshd configuration..."
if ! sshd -t; then
    echo "sshd -t FAILED - rolling back and leaving SSH exactly as it was." >&2
    rm -f "$CONF"
    exit 1
fi
echo "    config valid."

echo "==> Reloading sshd (existing sessions are unaffected)..."
systemctl reload ssh

echo "==> Refreshing package lists..."
apt-get update -qq

echo "==> Installing unattended-upgrades..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades
# Enabled explicitly rather than through the interactive dpkg-reconfigure, so
# this script never blocks waiting for a dialogue.
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

echo "==> Verifying..."
echo "--- effective sshd auth settings:"
sshd -T | grep -E "^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin)"
echo "--- unattended-upgrades dry run:"
unattended-upgrade --dry-run --debug 2>&1 | tail -3
echo "--- timers:"
systemctl is-enabled apt-daily.timer apt-daily-upgrade.timer 2>/dev/null || true

echo
echo "==> Done. SSH is key-only; security updates apply automatically."
echo "    Verify from another terminal before closing this one:"
echo "      ssh -o PubkeyAuthentication=no $USER@<host>   # must be refused"
echo "      ssh $USER@<host>                              # must still work"
