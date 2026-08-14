#!/bin/bash
# Stop cloud-init running at boot, and normalise /etc/hosts once it cannot.
#
#   sudo bash disable-cloud-init.sh
#
# WHEN THIS IS THE RIGHT TOOL. On a Pi that was provisioned once and has since
# been configured by hand, cloud-init still runs at every boot and its remaining
# effects are to reapply the provisioning: the hostname from its datasource, the
# 127.0.1.1 line from hosts.debian.tmpl, and ssh_pwauth against whatever sshd
# configuration has been installed since. After a rename that reinstates the old
# name as an alias on the loopback entry.
#
# WHY NOT FIX THE DATASOURCE INSTEAD. cloud-init caches the datasource per
# instance-id. While the instance-id is unchanged, /boot/firmware/user-data is
# never re-read, so correcting it has no effect until the cache is cleared.
# `cloud-init clean` clears it but re-runs the per-instance modules - users,
# packages, runcmd - on the next boot. Disabling is one file against a cache
# that a clean would otherwise have to churn.
#
# /etc/cloud/cloud-init.disabled is cloud-init's own documented switch, read by
# its systemd generator. Removing the file restores the previous behaviour.
#
# ⚠ This is a decision about the whole machine, not about one setting. On a box
# that still needs to be re-provisioned from its seed, do not run it.
set -euo pipefail

FLAG=/etc/cloud/cloud-init.disabled
STAMP="$(date +%Y%m%d-%H%M%S)"

fail() { echo "REFUSED: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "must run as root (use sudo)"
[ -d /etc/cloud ] || fail "/etc/cloud is not present - cloud-init is not installed"
grep -q '^127\.0\.1\.1' /etc/hosts || fail "/etc/hosts has no 127.0.1.1 line"

NAME="$(hostnamectl --static)"
[ -n "$NAME" ] || fail "hostnamectl returned no static hostname"

echo "Disabling cloud-init on '$NAME'"

# ---- 1. the switch ----------------------------------------------------------
if [ -e "$FLAG" ]; then
    echo "  $FLAG is already present"
else
    touch "$FLAG"
    echo "  created $FLAG"
fi

# ---- 2. /etc/hosts, now that nothing will overwrite it ----------------------
# Only meaningful after step 1. Normalising the line while cloud-init still runs
# is what produces the appearance of a fix that reverts at the next boot.
cp -a /etc/hosts "/etc/hosts.pre-disable-$STAMP"
BEFORE="$(grep '^127\.0\.1\.1' /etc/hosts)"
sed -i -E "s/^127\.0\.1\.1[[:space:]].*/127.0.1.1\t$NAME/" /etc/hosts
echo "  backup: /etc/hosts.pre-disable-$STAMP"
echo "  before: $BEFORE"
echo "  after : $(grep '^127\.0\.1\.1' /etc/hosts)"

# ---- verification -----------------------------------------------------------
echo
echo "--- verify ---"
echo "hostname    : $(hostnamectl --static)"
echo "hostname -f : $(hostname -f 2>&1 || echo '(unresolved)')"
echo "127.0.1.1   : $(grep '^127\.0\.1\.1' /etc/hosts)"
echo "switch      : $([ -e "$FLAG" ] && echo present || echo MISSING)"
echo
echo "NOT PROVEN UNTIL A REBOOT: the behaviour being stopped only happens at"
echo "boot, and the presence of the file above proves only that the file exists."
echo "After rebooting, the mtime of /etc/hosts must PREDATE the boot:"
echo
echo "    stat -c %y /etc/hosts   # must be earlier than"
echo "    uptime -s"
echo
echo "To roll back:"
echo "  rm $FLAG"
echo "  cp /etc/hosts.pre-disable-$STAMP /etc/hosts"
