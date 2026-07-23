param(
    [string]$User = "operations",
    [string]$PiHost = "192.168.1.61",
    [string]$KeyFile = "$env:USERPROFILE\.ssh\id_rsa"
)

$PI = "$User@$PiHost"
$REMOTE_DIR = "/home/$User/touch2-stargazing"

function Invoke-Pi($cmd) {
    ssh -i $KeyFile -o StrictHostKeyChecking=no $PI $cmd
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed: $cmd" }
}

function Copy-ToPi($local, $remote) {
    scp -i $KeyFile -o StrictHostKeyChecking=no $local "${PI}:${remote}"
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

# Run once immediately — do this BEFORE the timer is live. The timer has
# OnBootSec=30s + Persistent=true, so starting it soon after a boot fires an
# immediate catch-up service run; if we ran display.py manually at the same time
# the two inky processes would collide on the GPIO lines.
Write-Host "--> Running display now..."
Invoke-Pi "python3 $REMOTE_DIR/display.py"

# Install and substitute user into systemd units
Write-Host "--> Installing systemd units..."
$svc = (Get-Content "systemd\touch2-stargazing.service" -Raw) -replace "__USER__", $User
$svc | ssh -i $KeyFile -o StrictHostKeyChecking=no $PI "cat > /tmp/touch2-stargazing.service"
Copy-ToPi "systemd\touch2-stargazing.timer" "/tmp/touch2-stargazing.timer"
Invoke-Pi "sudo cp /tmp/touch2-stargazing.service /tmp/touch2-stargazing.timer /etc/systemd/system/"
Invoke-Pi "sudo systemctl daemon-reload"
Invoke-Pi "sudo systemctl enable touch2-stargazing.timer"
Invoke-Pi "sudo systemctl restart touch2-stargazing.timer"

Write-Host ""
Write-Host "==> Done."
Write-Host "    Timer fires every 2 h at :30 past. Check logs: journalctl -u touch2-stargazing"
