#!/bin/bash
# Install or update the systemd units from the staged copies in this directory
# (deploy.ps1 renders and scps them here; they arrive with __USER__ already
# substituted). Run as: sudo bash install-units.sh
#
# This is deliberately NOT covered by the NOPASSWD sudoers rules. A unit file
# executes as root, so a rule that let the unprivileged account install one
# would hand root to anything that compromised that account - which is exactly
# what the pre-v3.7.1 rules did. Installing a unit now costs a password, typed
# by a human who can see what is being installed. Routine deploys never need
# this; only a changed unit file does.
set -e
cd "$(dirname "$0")"
install -m 644 touch2-stargazing.service fbcon-detach.service \
               uptonight.service uptonight.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable fbcon-detach.service touch2-stargazing.service uptonight.timer
systemctl start fbcon-detach.service uptonight.timer
systemctl restart touch2-stargazing.service
echo "Units installed and services (re)started."
