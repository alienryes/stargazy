param(
    [string]$User = "operations",
    [string]$PiHost = "192.168.1.82",
    [string]$KeyFile = "$env:USERPROFILE\.ssh\id_rsa"
)

$PI = "$User@$PiHost"
$REMOTE_DIR = "/home/$User/inky-stargazing"

function Invoke-Pi($cmd) {
    ssh -i $KeyFile -o StrictHostKeyChecking=no $PI $cmd
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed: $cmd" }
}

function Copy-ToPi($local, $remote) {
    scp -i $KeyFile -o StrictHostKeyChecking=no $local "${PI}:${remote}"
    if ($LASTEXITCODE -ne 0) { throw "scp failed: $local -> $remote" }
}

Write-Host "==> Deploying inky-stargazing-display to $PI"

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
    Write-Host "  WARNING: config.toml not found locally — skipping (Pi will use existing or example)"
}

# Install Python dependencies
Write-Host "--> Installing Python dependencies..."
Invoke-Pi "pip3 install -r $REMOTE_DIR/requirements.txt --break-system-packages --prefer-binary"

# Install and substitute user into systemd units
Write-Host "--> Installing systemd units..."
$svc = (Get-Content "systemd\inky-stargazing.service" -Raw) -replace "__USER__", $User
$svc | ssh -i $KeyFile -o StrictHostKeyChecking=no $PI "cat > /tmp/inky-stargazing.service"
Copy-ToPi "systemd\inky-stargazing.timer" "/tmp/inky-stargazing.timer"
Invoke-Pi "sudo cp /tmp/inky-stargazing.service /tmp/inky-stargazing.timer /etc/systemd/system/"
Invoke-Pi "sudo systemctl daemon-reload"
Invoke-Pi "sudo systemctl enable inky-stargazing.timer"
Invoke-Pi "sudo systemctl restart inky-stargazing.timer"

# Run once immediately
Write-Host "--> Running display now..."
Invoke-Pi "python3 $REMOTE_DIR/display.py"

Write-Host ""
Write-Host "==> Done."
Write-Host "    Timer fires every 2 h at :30 past. Check logs: journalctl -u inky-stargazing"
