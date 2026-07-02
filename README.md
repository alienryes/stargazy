# 🌌 inky-stargazing-display

A stargazing conditions display for the [Pimoroni Inky Impression 4"](https://shop.pimoroni.com/products/inky-impression-4) 7-colour ePaper display, running on a Raspberry Pi Zero 2W. Fetches live [AstroWeather](https://github.com/mawinkler/astroweather) data from Home Assistant and renders a colour-coded overnight forecast — no interaction required.

**Highlights**

- Tonight's deep-sky verdict (EXCELLENT → NONE) in bold colour
- Condition bars: cloudless %, seeing, transparency, calm
- Moon phase geometry with next new/full moon dates
- Tomorrow's forecast, sun times, weather (temp, dew, humidity, wind)
- Handles the no-astronomical-darkness case for midsummer at high latitudes
- Refreshes every 2 hours via systemd timer; holds image without power between updates

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

This copies files, installs `inky` via pip, installs the systemd timer, and runs the display immediately. The timer refreshes the display every 2 hours at :30 past.

---

## 🖥️ Development preview

Generate a PNG without a connected display:

```bash
python3 display.py --save preview.png
```

---

## 🧰 Case — 3D-printed desktop stand

A two-part parametric stand (CadQuery) lives in [`case/`](./case). The **frame** holds the Inky PCB behind its bezel; the **riser** is a tilting back panel with an integrated foot that leans the display back by 15°. No front-face fasteners are used — retention posts on the riser press the PCB forward against the window.

The frame also carries an optional **addressable LED bezel ring** — 20 WS2812B LEDs (6 top, 6 bottom, 4 each side) behind a continuous slot per side, with a **translucent diffuser window ring printed into the frame** (2-material MMU) for an even glow; the LEDs sit 3 mm back so there are no hotspots, and the ring's filleted corners are a decorative inlay. The riser has a **ventilation grid** over the Pi. See [`case/leds.md`](./case/leds.md) for the strip, cut plan, and wiring to the Pi.

![Frame preview](./case/case_frame_v2_preview.png)
![Riser preview](./case/case_riser_v2_preview.png)

**Parts**

| File | Part | Print orientation |
|---|---|---|
| `case/case_frame_v2.py` / `.stl` | Front frame + PCB pocket + LED ring | Bezel (show face) **down** on the bed, pocket up — smooth face, no supports |
| `case/case_frame_v2_windows.stl` | Diffuser window ring (co-print) | Add as a part of the frame; assign to the **translucent** MMU extruder |
| `case/case_riser_v2.py` / `.stl` / `.3mf` | Tilting back panel + foot + vents | Flat **on its back**, posts/screw holes up — no supports despite the 15° lean |

**Key dimensions**

- Outer frame: 125.6 × 97.5 × 16 mm, 2 mm bezel, 14 mm walls (the wall grew from 10 mm to host the LED strip channel)
- Display window: 86 × 54 mm (active area), centred X, +2.15 mm Y
- PCB pocket: 97.6 × 69.5 mm (fits the 96.8 × 68.7 × **2.5 mm** Inky PCB with 0.4 mm/side clearance)
- LED bezel ring: 10.6 mm channel in the front bezel band, a 7 mm light slot per side under a continuous MMU-printed 0.8 mm translucent diffuser window ring (filleted corners, decorative); LEDs seat 3 mm back; see [`case/leds.md`](./case/leds.md)
- Ventilation: 45-hole (Ø4 mm) grid in the riser back panel over the Pi
- Cable slot through the bottom edge of both frame and riser for the USB/power lead (and the LED strip tail)

**Hardware:** 4 × M2.5 × 8 mm self-tapping screws (riser Ø2.9 mm clearance → frame Ø2.0 mm pilots). PLA/PETG, no supports.

**Assembly**

1. *(Optional LED ring)* Drop each LED strip segment into its bezel channel from the back (it seats 3 mm behind the printed-in diffuser window ring) and link the segments at the corners — see [`case/leds.md`](./case/leds.md).
2. Slide the Inky PCB into the frame pocket from the back; the active area shows through the window.
3. Route the USB/power cable (and LED tail, if fitted) out through the bottom cable slot.
4. Fit the riser over the back — its four posts press the PCB against the bezel.
5. Drive the four M2.5 screws through the riser corners into the frame pilots.

**Regenerate the STLs** (only if you change parameters — edit the `PARAMETERS` block at the top of each script):

```bash
cd case
python case_frame_v2.py   # writes case_frame_v2.stl + case_frame_v2_windows.stl
python case_riser_v2.py   # writes case_riser_v2.stl
```

Requires `cadquery` (a local `case/.cadvenv` is used on the dev machine; see [cad-skill](https://github.com/flowful-ai/cad-skill)).

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
journalctl -u inky-stargazing
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
  inky-stargazing.service
  inky-stargazing.timer
case/                   3D-printed desktop stand (CadQuery)
  case_frame_v2.py      Front frame + PCB pocket + LED ring (source)
  case_frame_v2.stl     Frame mesh
  case_frame_v2_windows.stl  Diffuser window ring, MMU translucent co-print
  case_frame_v2_preview.png
  case_riser_v2.py      Tilting back panel + foot + vent grid (source)
  case_riser_v2.stl     Riser mesh
  case_riser_v2.3mf     Riser, sliced project
  case_riser_v2_preview.png
  leds.md               LED bezel ring — strip, cut plan, wiring
```
