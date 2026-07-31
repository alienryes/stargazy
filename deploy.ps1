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
Copy-ToPi "requirements.txt" "$REMOTE_DIR/requirements.txt"

# Always deploy local config.toml (gitignored, contains real token)
if (Test-Path "config.toml") {
    Copy-ToPi "config.toml" "$REMOTE_DIR/config.toml"
} else {
    Write-Host "  WARNING: config.toml not found locally - skipping (Pi will use existing or example)"
}

# Install Python dependencies
Write-Host "--> Installing Python dependencies..."
Invoke-Pi "pip3 install -r $REMOTE_DIR/requirements.txt --break-system-packages --prefer-binary"

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

Write-Host ""
Write-Host "==> Done."
Write-Host "    Always-on animated display service running. Logs: journalctl -u touch2-stargazing -f"
