#!/bin/bash
# One-time setup for touch2-stargazing-display on a Raspberry Pi driving the
# Touch Display 2 via the framebuffer (/dev/fb0). Run once as: sudo bash setup.sh <username>
set -e

USER="${1:-operations}"

# UpTonight is not published to PyPI and its repo carries no package metadata
# (pyproject.toml holds lint settings only), so it is installed as a source tree
# at a pinned commit rather than with pip.
UT_REF="3ae62e23d020ef067672cae9b48e961a4a1030df"
UT_DIR="/home/$USER/uptonight"

echo "==> Installing system packages..."
apt-get install -y fonts-dejavu-core fonts-ibm-plex python3-pil python3-numpy \
    python3-requests python3-pip python3-venv

echo "==> Ensuring $USER can write the framebuffer and read the touchscreen..."
# video also carries write access to /sys/class/backlight, which the touch
# controls use for brightness and for blanking the panel.
adduser "$USER" video || true
adduser "$USER" input || true

echo "==> Freeing the framebuffer console (fbcon=map:2)..."
# Keep the text console off /dev/fb0 so it never overdraws the dashboard.
# The runtime fbcon-detach.service unbinds it at deploy time; this makes it
# stick across reboots regardless of KMS init ordering. Takes effect on reboot.
CMDLINE=/boot/firmware/cmdline.txt
if [ -f "$CMDLINE" ] && ! grep -q "fbcon=map:2" "$CMDLINE"; then
    sed -i '1 s/[[:space:]]*$//; 1 s/$/ fbcon=map:2/' "$CMDLINE"
    echo "    added fbcon=map:2 to $CMDLINE (reboot required)"
fi

echo "==> Installing UpTonight at $UT_REF..."
# git is not installed on a default Raspberry Pi OS image, so fetch the tarball.
rm -rf /tmp/uptonight-src && mkdir -p /tmp/uptonight-src "$UT_DIR"
curl -fsSL "https://codeload.github.com/mawinkler/uptonight/tar.gz/$UT_REF" \
    | tar xz -C /tmp/uptonight-src
# Copy in rather than replace, so an existing out/ and config.yaml survive.
cp -r "/tmp/uptonight-src/uptonight-$UT_REF/." "$UT_DIR/"
mkdir -p "$UT_DIR/out"
chown -R "$USER:$USER" "$UT_DIR"

echo "==> Building UpTonight's virtualenv (a couple of minutes)..."
# Its requirements.txt pins versions that have no wheels for Python 3.13
# (numpy 1.26.4, astropy 6.0.1), so install the same libraries unpinned; the
# current releases run it unmodified. --only-binary keeps this from silently
# dropping into an hours-long source build on the Pi.
if [ ! -d "$UT_DIR/.venv" ]; then
    sudo -u "$USER" python3 -m venv "$UT_DIR/.venv"
fi
sudo -u "$USER" "$UT_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u "$USER" "$UT_DIR/.venv/bin/pip" install -q --only-binary=:all: \
    astroplan astropy skyfield numpy pandas matplotlib pillow h5py \
    PyYAML pytz requests paho-mqtt

echo "==> Building the display's virtualenv..."
# The display gets its own venv for the same reason UpTonight does: the direct
# weather source pulls in pandas, which brings its own numpy, and dropping that
# into the system Python alongside apt's python3-numpy risks shadowing the very
# package the framebuffer path depends on. --system-site-packages keeps apt's
# pillow/numpy/requests visible, so only the new libraries are downloaded.
DISPLAY_DIR="/home/$USER/touch2-stargazing"
mkdir -p "$DISPLAY_DIR"
chown "$USER:$USER" "$DISPLAY_DIR"
if [ ! -d "$DISPLAY_DIR/.venv" ]; then
    sudo -u "$USER" python3 -m venv --system-site-packages "$DISPLAY_DIR/.venv"
fi
sudo -u "$USER" "$DISPLAY_DIR/.venv/bin/pip" install -q --upgrade pip

echo "==> Adding sudoers rule for $USER..."
cat > /etc/sudoers.d/touch2-stargazing <<EOF
$USER ALL=(ALL) NOPASSWD: /usr/bin/cp /tmp/touch2-stargazing.service /tmp/fbcon-detach.service /etc/systemd/system/
$USER ALL=(ALL) NOPASSWD: /usr/bin/cp /tmp/uptonight.service /tmp/uptonight.timer /etc/systemd/system/
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl daemon-reload
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable touch2-stargazing.service
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart touch2-stargazing.service
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable fbcon-detach.service
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start fbcon-detach.service
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable uptonight.timer
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start uptonight.timer
$USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start uptonight.service
EOF
chmod 440 /etc/sudoers.d/touch2-stargazing

echo "==> Done. You can now run deploy.ps1 from Windows."
