# 🌌 touch2-stargazing-display

A stargazing conditions display for the [Pimoroni Inky Impression 4"](https://shop.pimoroni.com/products/inky-impression-4) 7-colour ePaper display, running on a Raspberry Pi Zero 2W. Fetches live [AstroWeather](https://github.com/mawinkler/astroweather) data from Home Assistant and renders a colour-coded overnight forecast — no interaction required.

**Highlights**

- Tonight's deep-sky verdict (EXCELLENT → NONE) in bold colour
- Condition bars: cloudless %, seeing, transparency, calm
- Moon phase geometry with next new/full moon dates
- Tomorrow's forecast, sun times, weather (temp, dew, humidity, wind)
- Handles the no-astronomical-darkness case for midsummer at high latitudes
- Live, data-reactive animated night sky behind the dashboard; always-on systemd service

---

## 📸 Display layout

```
┌─────────────────────────────────────────────────────────────────┐
│ STARGAZING                              Mon 14 Jun  22:30       │
│─────────────────────────────────────────────────────────────────│
│ NO DARK SKY                                MOON                 │
│ Next dark night: 21 Jul               New Moon                  │
│                                       In Taurus                 │
│ Cloudless    [██░░░░░░░░]  30%        ◐ (phase graphic)        │
│ Seeing       [███████░░░]  72%                                  │
│ Transparency [████░░░░░░]  40%        New:  15 Jun              │
│ Calm         [█████████░]  85%        Full: 29 Jun              │
│─────────────────────────────────────────────────────────────────│
│ Tomorrow: Cloudy (31%)    4 to 6, very stable                   │
│ Sunset 22:13  ·  Sunrise 04:03                                  │
│ 17.8°C  ·  Dew 10.9°  ·  64% RH  ·  E 8.6 m/s          v1.0.0│
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Requirements

**Hardware**
- Raspberry Pi Zero 2W
- Pimoroni Inky Impression 4" (640×400, 7-colour, UC8159 driver)

**Software**
- Raspberry Pi OS Lite 64-bit (Trixie / Bookworm)
- Python 3.11+
- Home Assistant with [AstroWeather](https://github.com/mawinkler/astroweather) integration (backyard location configured)
- HA long-lived access token

---

## 🚀 Setup

### 1. Pi one-time setup

Enable SPI and configure the device tree, then run the setup script:

```bash
sudo raspi-config nonint do_spi 0

# Release the SPI CS pin so the inky library can claim it via gpiod
echo "dtoverlay=spi0-0cs" | sudo tee -a /boot/firmware/config.txt
sudo reboot
```

After reboot:

```bash
# Copy setup.sh to the Pi, then:
sudo bash setup.sh operations
```

`setup.sh` installs `fonts-dejavu-core`, `python3-pil`, `python3-spidev`, `python3-rpi.gpio`, and a scoped sudoers rule for the deploy script.

### 2. Create config

```bash
cp config.example.toml config.toml
```

Edit `config.toml` with your HA URL and a long-lived access token (HA → Profile → Security → Long-Lived Access Tokens):

```toml
[ha]
url = "http://192.168.1.x:8123"
token = "your-token-here"
```

### 3. Deploy

From Windows:

```powershell
.\deploy.ps1
```

This copies files, installs the Python dependencies, installs the `fbcon-detach` and display services, and starts the always-on animated display.

---

## 🖥️ Development preview

Generate a PNG without a connected display:

```bash
python3 display.py --save preview.png
```

---

## 🧰 Case

This project no longer ships a case. It originally ran on a **Pimoroni Inky
Impression 4"** with a bespoke 3D-printed desktop stand (CadQuery frame + riser +
WS2812B LED bezel ring). After moving to the self-lit **5" Raspberry Pi Touch
Display 2** — which has off-the-shelf cases and needs no LED backlight — that
design was retired and archived, with full history, at
[`adminfor/inky-impression-case`](https://forgejo.home.neilsayer.co.uk/adminfor/inky-impression-case).

---

## 🔧 Troubleshooting

| Symptom | Fix |
|---|---|
| `No EEPROM detected` | Don't use `auto()` — the code uses explicit `Inky(resolution=(640, 400))` already |
| `Resolution 600x400 not supported` | The 4" display is 640×400 in the driver, not 600×400 |
| `Chip Select: currently claimed by spi0` | Add `dtoverlay=spi0-0cs` to `/boot/firmware/config.txt` and reboot |
| Long busy-wait (~32 s) during `show()` | Normal — 7-colour ePaper full refresh takes ~30 seconds |
| `KeyError: 'ha'` in config | `config.toml` is missing the `[ha]` section header |
| 401 Unauthorized from HA | Token in `config.toml` is wrong or expired |

**Check logs:**

```bash
journalctl -u touch2-stargazing
```

---

## 📁 File structure

```
display.py              Main script
config.toml             Local config (gitignored)
config.example.toml     Template
deploy.ps1              Windows → Pi deploy script
setup.sh                One-time Pi setup (run with sudo)
systemd/
  touch2-stargazing.service   (always-on animated display daemon)
  fbcon-detach.service
```
