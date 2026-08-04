param(
    [string]$User = "operations",
    [string]$PiHost = "astro-pi.local",
    [string]$KeyFile = "$env:USERPROFILE\.ssh\id_rsa"
)

# The Pi answers on wired or wireless depending on whether the Ethernet cable is
# in, so resolve it by mDNS name rather than pinning an IP. -4 keeps us on IPv4:
# mDNS also returns an IPv6 ULA, and which one wins varies by resolver order.
# Pass -PiHost to override with an explicit address if mDNS is unavailable.
$PI = "$User@$PiHost"
$REMOTE_DIR = "/home/$User/touch2-stargazing"
$UT_DIR = "/home/$User/uptonight"

function Invoke-Pi($cmd) {
    ssh -4 -i $KeyFile -o StrictHostKeyChecking=no $PI $cmd
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed: $cmd" }
}

function Copy-ToPi($local, $remote) {
    scp -4 -i $KeyFile -o StrictHostKeyChecking=no $local "${PI}:${remote}"
    if ($LASTEXITCODE -ne 0) { throw "scp failed: $local -> $remote" }
}

Write-Host "==> Deploying touch2-stargazing-display to $PI"

# Create remote directory
Invoke-Pi "mkdir -p $REMOTE_DIR"

# Copy files
Write-Host "--> Copying files..."
Copy-ToPi "display.py"    "$REMOTE_DIR/display.py"
Copy-ToPi "touch.py"      "$REMOTE_DIR/touch.py"
Copy-ToPi "requirements.txt" "$REMOTE_DIR/requirements.txt"
Copy-ToPi "render_uptonight_config.py" "$REMOTE_DIR/render_uptonight_config.py"
Copy-ToPi "uptonight\config.yaml.template" "$REMOTE_DIR/uptonight-config.yaml.template"

# Always deploy local config.toml (gitignored, contains real token)
if (Test-Path "config.toml") {
    Copy-ToPi "config.toml" "$REMOTE_DIR/config.toml"
} else {
    Write-Host "  WARNING: config.toml not found locally - skipping (Pi will use existing or example)"
}

# Install Python dependencies
Write-Host "--> Installing Python dependencies..."
Invoke-Pi "$REMOTE_DIR/.venv/bin/pip install -q -r $REMOTE_DIR/requirements.txt --prefer-binary"

# Render UpTonight's config from [location] in config.toml, so the site is only
# ever configured in one place. Skipped if setup.sh has not installed it yet.
Write-Host "--> Rendering UpTonight config..."
Invoke-Pi "test -d $UT_DIR && python3 $REMOTE_DIR/render_uptonight_config.py $REMOTE_DIR/config.toml $REMOTE_DIR/uptonight-config.yaml.template $UT_DIR/config.yaml || echo '  (UpTonight not installed - run setup.sh)'"

# Install systemd units (substitute the user into the service).
# fbcon-detach frees /dev/fb0 from the console so the display isn't overdrawn.
Write-Host "--> Installing systemd units..."
$svc = (Get-Content "systemd\touch2-stargazing.service" -Raw) -replace "__USER__", $User
$svc | ssh -4 -i $KeyFile -o StrictHostKeyChecking=no $PI "cat > /tmp/touch2-stargazing.service"
Copy-ToPi "systemd\fbcon-detach.service" "/tmp/fbcon-detach.service"
Invoke-Pi "sudo cp /tmp/touch2-stargazing.service /tmp/fbcon-detach.service /etc/systemd/system/"
# Retire the old 2-hourly timer if present (superseded by the always-on service).
Invoke-Pi "sudo systemctl disable --now touch2-stargazing.timer 2>/dev/null; sudo rm -f /etc/systemd/system/touch2-stargazing.timer"
Invoke-Pi "sudo systemctl daemon-reload"
Invoke-Pi "sudo systemctl enable fbcon-detach.service"
Invoke-Pi "sudo systemctl start fbcon-detach.service"
Invoke-Pi "sudo systemctl enable touch2-stargazing.service"
Invoke-Pi "sudo systemctl restart touch2-stargazing.service"

# UpTonight's daily timer. The service itself is oneshot and is only started
# here when there is no report yet, so a redeploy never triggers a needless run.
Write-Host "--> Installing UpTonight timer..."
$ut = (Get-Content "systemd\uptonight.service" -Raw) -replace "__USER__", $User
$ut | ssh -4 -i $KeyFile -o StrictHostKeyChecking=no $PI "cat > /tmp/uptonight.service"
Copy-ToPi "systemd\uptonight.timer" "/tmp/uptonight.timer"
Invoke-Pi "sudo cp /tmp/uptonight.service /tmp/uptonight.timer /etc/systemd/system/"
Invoke-Pi "sudo systemctl daemon-reload"
Invoke-Pi "sudo systemctl enable uptonight.timer"
Invoke-Pi "sudo systemctl start uptonight.timer"
Invoke-Pi "test -f $UT_DIR/out/uptonight-report.json || sudo systemctl start uptonight.service"

Write-Host ""
Write-Host "==> Done."
Write-Host "    Always-on animated display service running. Logs: journalctl -u touch2-stargazing -f"
Write-Host "    Targets recomputed daily at midday.        Logs: journalctl -u uptonight -f"
