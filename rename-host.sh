#!/bin/bash
# Rename a Raspberry Pi, and disarm what would otherwise silently undo it.
#
#   sudo bash rename-host.sh <newname>
#
# WHY A SCRIPT RATHER THAN hostnamectl. On a Pi provisioned with Raspberry Pi
# Imager, cloud-init owns the hostname. /etc/cloud/cloud.cfg carries
# preserve_hostname: false and /boot/firmware/user-data carries the name, so
# `hostnamectl set-hostname` succeeds, tests clean, and is undone at the next
# boot - which may be weeks later, far enough from the change that the two are
# not obviously connected.
#
# Three things about that are easy to get wrong, and all three are handled here:
#
#   1. manage_etc_hosts is set in the SEED (/boot/firmware/user-data), not in
#      /etc/cloud/cloud.cfg. Searching /etc/cloud for it returns only the
#      hosts.*.tmpl templates, whose own comment text explains the option and
#      reads exactly like a setting.
#   2. The seed OUTRANKS /etc/cloud/cloud.cfg.d/*. A preserve_hostname drop-in
#      works because the seed does not set that key; a manage_etc_hosts drop-in
#      would be overridden silently.
#   3. cloud-init caches the datasource per instance-id, so editing the seed
#      changes nothing until the instance-id changes or the cache is cleared.
#      The seed is corrected here for consistency, but disable-cloud-init.sh is
#      what makes the /etc/hosts line stick on an already-provisioned box.
#
# A wrong 127.0.1.1 entry makes sudo HANG rather than fail, because it waits on
# a name lookup - so a rename that stops halfway presents as an unrelated fault
# on a machine that may have no keyboard attached. Every precondition is
# therefore asserted before anything is written.
#
# Only a REBOOT proves a rename. Nothing checked before one is evidence.
set -euo pipefail

NEW="${1:-}"
DROPIN=/etc/cloud/cloud.cfg.d/99-hostname.cfg
SEED=/boot/firmware/user-data
STAMP="$(date +%Y%m%d-%H%M%S)"

fail() { echo "REFUSED: $*" >&2; exit 1; }

# ---- preconditions, all of them, before anything is written ----------------
# Argument checks first, because they need no privilege: ordered the other way
# round, an invalid name is reported as a permissions problem and the validation
# cannot be exercised without root.
[ -n "$NEW" ] || fail "no new hostname given (usage: sudo bash $0 <newname>)"
echo "$NEW" | grep -qE '^[a-z0-9][a-z0-9-]{0,62}$' \
    || fail "'$NEW' is not a valid hostname label"
[ "$(id -u)" -eq 0 ] || fail "must run as root (use sudo)"
[ -w /etc/hosts ] || fail "/etc/hosts is not writable"
grep -q '^127\.0\.1\.1' /etc/hosts || fail "/etc/hosts has no 127.0.1.1 line to fix"
command -v hostnamectl >/dev/null || fail "hostnamectl is not present"

OLD="$(hostnamectl --static)"
[ "$OLD" = "$NEW" ] && echo "Already named $NEW; re-applying the guards only."

echo "Renaming '$OLD' -> '$NEW'"

# ---- backups ---------------------------------------------------------------
cp -a /etc/hosts "/etc/hosts.pre-rename-$STAMP"
echo "  backup: /etc/hosts.pre-rename-$STAMP"
if [ -f "$SEED" ]; then
    cp -a "$SEED" "$SEED.pre-rename-$STAMP"
    echo "  backup: $SEED.pre-rename-$STAMP"
fi

# ---- 1. stop cloud-init owning the hostname --------------------------------
if [ -d /etc/cloud/cloud.cfg.d ]; then
    cat > "$DROPIN" <<EOF
# Added $(date +%F) by rename-host.sh.
#
# Without this, cloud-init reapplies the hostname from its datasource on every
# boot and a rename reverts. preserve_hostname makes set_hostname and
# update_hostname no-ops, leaving the hostname under hostnamectl's control.
preserve_hostname: true
EOF
    echo "  wrote $DROPIN"
else
    echo "  no /etc/cloud/cloud.cfg.d; cloud-init is not managing this host"
fi

# ---- 2. correct the seed, where there is one -------------------------------
if [ -f "$SEED" ]; then
    if grep -qE '^[[:space:]]*hostname:' "$SEED"; then
        sed -i -E "s/^([[:space:]]*hostname:[[:space:]]*).*/\1$NEW/" "$SEED"
        echo "  seed hostname set to $NEW"
    fi
    # manage_etc_hosts makes cloud-init regenerate the 127.0.1.1 line from
    # hosts.debian.tmpl at boot, which reinstates the old name as an alias.
    # Corrected in the seed rather than the drop-in because the seed outranks it.
    if grep -qE '^[[:space:]]*manage_etc_hosts:' "$SEED"; then
        sed -i -E "s/^([[:space:]]*manage_etc_hosts:[[:space:]]*).*/\1false/" "$SEED"
        echo "  seed manage_etc_hosts set to false"
    fi
fi

# ---- 3. the hostname itself -------------------------------------------------
hostnamectl set-hostname "$NEW"
echo "  hostnamectl set-hostname $NEW"

# ---- 4. /etc/hosts, which is what stops sudo hanging ------------------------
# The whole line is replaced rather than the old name substituted: the entry
# cloud-init writes carries the name twice, and a substitution would faithfully
# duplicate the new one.
sed -i -E "s/^127\.0\.1\.1[[:space:]].*/127.0.1.1\t$NEW/" /etc/hosts
echo "  /etc/hosts: $(grep '^127\.0\.1\.1' /etc/hosts)"

# ---- 5. avahi follows the hostname, but only after a restart ----------------
# The .local name changes with it, and the OLD one stops resolving at that
# moment - which breaks anything still defaulting to it.
if systemctl is-active --quiet avahi-daemon; then
    systemctl restart avahi-daemon
    echo "  avahi-daemon restarted; $NEW.local should now resolve"
else
    echo "  avahi-daemon is not active; no .local name to re-advertise"
fi

# ---- verification -----------------------------------------------------------
echo
echo "--- verify ---"
echo "hostnamectl --static : $(hostnamectl --static)"
echo "hostname -f          : $(hostname -f 2>&1 || echo '(unresolved)')"
echo "127.0.1.1 line       : $(grep '^127\.0\.1\.1' /etc/hosts)"
[ -f "$DROPIN" ] && echo "drop-in              : $(grep -h preserve_hostname "$DROPIN")"
if [ -f "$SEED" ]; then
    echo "seed hostname        : $(grep -E '^[[:space:]]*hostname:' "$SEED" || echo '(none)')"
    echo "seed manage_etc_hosts: $(grep -E '^[[:space:]]*manage_etc_hosts:' "$SEED" || echo '(none)')"
fi
echo
echo "THE RENAME IS NOT PROVEN UNTIL A REBOOT. On an already-provisioned box the"
echo "seed edit above has no effect until the datasource cache is cleared, so if"
echo "the 127.0.1.1 line comes back with the old name as an alias, run"
echo "'sudo bash disable-cloud-init.sh' and reboot again."
echo
echo "To roll back:"
[ -f "$DROPIN" ] && echo "  rm $DROPIN"
echo "  cp /etc/hosts.pre-rename-$STAMP /etc/hosts"
[ -f "$SEED" ] && echo "  cp $SEED.pre-rename-$STAMP $SEED"
echo "  hostnamectl set-hostname $OLD && systemctl restart avahi-daemon"
