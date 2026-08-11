param(
    [string]$User = "operations",
    [string]$PiHost = "astro-pi.local",
    [string]$KeyFile = "$env:USERPROFILE\.ssh\id_rsa"
)

# The Pi answers on wired or wireless depending on whether the Ethernet cable is
# in, so resolve it by mDNS name rather than pinning an IP. -4 keeps us on IPv4:
# mDNS also returns an IPv6 ULA, and which one wins varies by resolver order.
# Pass -PiHost to override with an explicit address if mDNS is unavailable.
#
# accept-new, not no: the first connect trusts the key it sees (as before), but
# after that a changed key aborts instead of silently connecting - this script
# ships config.toml, the one file carrying a real credential, so it should not
# be talkable-to by an impostor. After reflashing the Pi, clear the stale key
# with: ssh-keygen -R <host>.
$PI = "$User@$PiHost"
$REMOTE_DIR = "/home/$User/stargazy"
$UT_DIR = "/home/$User/uptonight"

# Paths are resolved against this script rather than the caller's location, so
# deploy works from anywhere in the repo. The shared engine in core/ sits beside
# the build folders here, and lands beside display.py on the Pi - the install
# layout stays flat, so the systemd units do not change.
$BUILD = $PSScriptRoot
$CORE = Join-Path (Split-Path $PSScriptRoot -Parent) "core"

function Invoke-Pi($cmd) {
    ssh -4 -i $KeyFile -o StrictHostKeyChecking=accept-new $PI $cmd
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed: $cmd" }
}

function Copy-ToPi($local, $remote) {
    scp -4 -i $KeyFile -o StrictHostKeyChecking=accept-new $local "${PI}:${remote}"
    if ($LASTEXITCODE -ne 0) { throw "scp failed: $local -> $remote" }
}

Write-Host "==> Deploying stargazy to $PI"

# Create remote directory
Invoke-Pi "mkdir -p $REMOTE_DIR"

# Copy files
Write-Host "--> Copying files..."
Copy-ToPi "$BUILD\display.py"    "$REMOTE_DIR/display.py"

# The shared engine sits beside display.py, so the install layout stays flat and
# the systemd units keep working unchanged.
Invoke-Pi "mkdir -p $REMOTE_DIR/core/data"
foreach ($f in Get-ChildItem "$CORE\*.py") {
    Copy-ToPi $f.FullName "$REMOTE_DIR/core/$($f.Name)"
}
# The star catalogue ships with the code so the sky needs no network. Without
# it the real starfield raises on first refresh.
foreach ($f in Get-ChildItem "$CORE\data\*") {
    Copy-ToPi $f.FullName "$REMOTE_DIR/core/data/$($f.Name)"
}

# grab_panel.py reads /dev/fb0, so it is only useful ON the Pi. The other tools
# are development checks and stay in the repo.
Copy-ToPi (Join-Path (Split-Path $PSScriptRoot -Parent) "tools\grab_panel.py") `
          "$REMOTE_DIR/grab_panel.py"

Copy-ToPi "$BUILD\requirements.txt" "$REMOTE_DIR/requirements.txt"
Copy-ToPi "$BUILD\render_uptonight_config.py" "$REMOTE_DIR/render_uptonight_config.py"
Copy-ToPi "$BUILD\uptonight\config.yaml.template" "$REMOTE_DIR/uptonight-config.yaml.template"

# Always deploy local config.toml (gitignored, contains real token), and keep
# it readable by its owner only - it can carry a Home Assistant token.
if (Test-Path "$BUILD\config.toml") {
    Copy-ToPi "$BUILD\config.toml" "$REMOTE_DIR/config.toml"
    Invoke-Pi "chmod 600 $REMOTE_DIR/config.toml"
} else {
    Write-Host "  WARNING: config.toml not found locally - skipping (Pi will use existing or example)"
}

# Install Python dependencies
Write-Host "--> Installing Python dependencies..."
# `python -m pip`, not `.venv/bin/pip`: the console script carries an absolute
# shebang naming the path the venv was created at, so it breaks the moment the
# install directory is renamed or moved. The interpreter itself is a symlink to
# the system python and relocates cleanly, so going through it does not.
Invoke-Pi "$REMOTE_DIR/.venv/bin/python -m pip install -q -r $REMOTE_DIR/requirements.txt --prefer-binary"

# Render UpTonight's config from [location] in config.toml, so the site is only
# ever configured in one place. Skipped if setup.sh has not installed it yet.
Write-Host "--> Rendering UpTonight config..."
Invoke-Pi "test -d $UT_DIR && python3 $REMOTE_DIR/render_uptonight_config.py $REMOTE_DIR/config.toml $REMOTE_DIR/uptonight-config.yaml.template $UT_DIR/config.yaml || echo '  (UpTonight not installed - run setup.sh)'"

# Stage the systemd units (rendered, user-owned, no privilege needed) and
# compare with what is installed. Deploy itself can only RESTART services: unit
# files execute as root, so INSTALLING one deliberately costs an interactive
# sudo password via install-units.sh rather than a NOPASSWD rule - the old
# unattended cp-from-/tmp rule was a root escalation for anything that
# compromised the deploy account.
Write-Host "--> Staging systemd units..."
Invoke-Pi "mkdir -p $REMOTE_DIR/systemd"
foreach ($u in @("stargazy.service", "uptonight.service")) {
    $txt = (Get-Content "$BUILD\systemd\$u" -Raw) -replace "__USER__", $User
    $txt | ssh -4 -i $KeyFile -o StrictHostKeyChecking=accept-new $PI "cat > $REMOTE_DIR/systemd/$u"
    if ($LASTEXITCODE -ne 0) { throw "staging failed: $u" }
}
Copy-ToPi "$BUILD\systemd\fbcon-detach.service" "$REMOTE_DIR/systemd/fbcon-detach.service"
Copy-ToPi "$BUILD\systemd\uptonight.timer"      "$REMOTE_DIR/systemd/uptonight.timer"
Copy-ToPi "$BUILD\systemd\install-units.sh"     "$REMOTE_DIR/systemd/install-units.sh"

$check = 'for f in stargazy.service fbcon-detach.service uptonight.service uptonight.timer; do cmp -s ' + $REMOTE_DIR + '/systemd/$f /etc/systemd/system/$f || echo $f; done; true'
$changed = ssh -4 -i $KeyFile -o StrictHostKeyChecking=accept-new $PI $check

if ($changed) {
    Write-Host ""
    Write-Host "==> UNIT FILES CHANGED OR NOT YET INSTALLED: $($changed -join ', ')"
    Write-Host "    Installing a unit needs real sudo (see systemd/install-units.sh). Run:"
    Write-Host ""
    Write-Host "      ssh -4 -t ${PI} `"sudo bash $REMOTE_DIR/systemd/install-units.sh`""
    Write-Host ""
    Write-Host "    The display keeps running on the old units until then."
} else {
    Write-Host "--> Units unchanged; restarting display..."
    Invoke-Pi "sudo -n systemctl restart stargazy.service"
}

# First-run convenience: kick a targets computation if there is no report yet,
# so the targets page appears without waiting for the midday timer. Skipped
# when the unit is not installed, which is the state on a very first deploy -
# the units are staged just above and installed separately, so starting one
# here would fail the whole deploy after all its real work had succeeded.
Invoke-Pi "test -f $UT_DIR/out/uptonight-report.json || ! test -f /etc/systemd/system/uptonight.service || sudo -n systemctl start uptonight.service"

Write-Host ""
Write-Host "==> Done."
Write-Host "    Always-on animated display service running. Logs: journalctl -u stargazy -f"
Write-Host "    Targets recomputed daily at midday.        Logs: journalctl -u uptonight -f"
