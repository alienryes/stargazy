# 🌌 touch2-stargazing-display

A stargazing conditions display for the [Raspberry Pi Touch Display 2 (5")](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html), driven by a Raspberry Pi 4. It fetches live [AstroWeather](https://github.com/mawinkler/astroweather) forecast data — on the Pi itself, or from Home Assistant if you run it — and renders a colour-coded overnight forecast over a live, data-reactive animated night sky — no interaction required.

Rendered with Pillow at 1280×720 landscape and written straight to the Linux framebuffer (`/dev/fb0`, RGB565) — no X, no display server, no `inky` library.

**Highlights**

- Tonight's deep-sky verdict (EXCELLENT → NONE) in bold colour
- Condition bars: cloudless %, seeing, transparency, calm
- Moon phase geometry with constellation and next new/full moon dates
- Footer grouped by type — astronomical (moon dates, dusk/dawn) on the right under the moon; meteorological (lifted index, weather) on the left
- Handles the no-astronomical-darkness case for midsummer at high latitudes
- **Live animated night sky** behind the dashboard: twinkling starfield, drifting clouds and occasional meteors, all **reactive to the actual conditions**

---

## 📸 Display layout

```
┌───────────────────────────────────────────────────────────────┐
│ STARGAZING                                     Fri 24 Jul 21:58 │
│───────────────────────────────────────────────────────────────│
│ EXCELLENT                                                       │
│ Deep sky: 94%  -  Clear sky night                               │
│───────────────────────────────────────────────────────────────│
│ Cloudless    [█░░░░░░░]  0%   │                                 │
│ Seeing       [███░░░░░] 34%   │        ◑  Waxing Gibbous        │
│ Transparency [██░░░░░░] 12%   │            in Scorpius          │
│ Calm         [███████░] 89%   │                                 │
│───────────────────────────────────────────────────────────────│
│ Tomorrow: Cloudy (5%)               New 12 Aug  -  Full 29 Jul  │
│ LI: Over 6, very stable             Dusk 21:50  -  Dawn 04:39   │
│ Temp 24.7°C  -  Dew 12.0°C  -  RH 45%  -  Wind W 6.5 m/s        │
└───────────────────────────────────────────────────────────────┘
        ...behind everything: a living sky — stars, clouds, meteors
```

> **Dusk / Dawn**, not sunrise/sunset: AstroWeather's sun rise/set entities report **civil twilight** bounds (sun 6° below the horizon), ~40 min off the geometric sun crossing. True darkness is tracked separately (`astronomical_night_duration`) and drives the "NO DARK SKY" state.

---

## ✨ The animated sky

The sky is a live layer composited behind the dashboard each frame (~20 fps); the dashboard itself is an RGBA overlay (transparent where the sky should show, opaque content on top). The animation **reflects the conditions** rather than just decorating:

| Condition | Effect |
|---|---|
| Seeing / transparency / calm | Star brightness and twinkle (crisper when clear) |
| Cloud cover | Number of soft drifting clouds (0 → 7), which dim the stars they pass |
| Wind speed | Drift speed of stars and clouds |
| No astronomical darkness | Sky washes to twilight blue; meteors suppressed |

Meteors streak occasionally through the night sky (rarer when cloudy). Star and cloud brightness always keep a visible floor, so the sky stays alive even on poor nights.

---

## 🛠️ Requirements

**Hardware**
- Raspberry Pi 4 — what this is built and proven on. A **Pi 5 is untested**: it needs a longer 22-pin DSI FFC plus a 22-to-15-pin adapter, and `display.py` assumes a 16-bit RGB565 `/dev/fb0`, which a Pi 5 may not provide. There is also no performance reason to move — the render loop is single-threaded and uses about one core of four.
- Raspberry Pi Touch Display 2, 5" variant (720×1280 DSI), connected via the DSI FFC

**Software**
- Raspberry Pi OS Lite 64-bit (Trixie / Bookworm), headless (`multi-user.target`)
- Python 3.11+
- **No Home Assistant required.** Weather comes from [pyastroweatherio](https://github.com/mawinkler/pyastroweatherio) — the library the Home Assistant [AstroWeather](https://github.com/mawinkler/astroweather) integration itself wraps — talking straight to MET Norway and Open-Meteo. If you do run Home Assistant with that integration, set `weather.source = "homeassistant"` and the display reads its sensors instead.

---

## 🚀 Setup

### 1. Pi one-time setup

The Touch Display 2 is auto-detected over DSI — no SPI or device-tree overlay needed. Just run the setup script:

```bash
# Copy setup.sh to the Pi, then:
sudo bash setup.sh operations
sudo reboot   # required: setup.sh adds fbcon=map:2 to the kernel cmdline
```

`setup.sh`:
- installs `fonts-dejavu-core`, `python3-pil`, `python3-numpy`, `python3-requests`, `python3-pip`, `python3-venv`
- builds the display's virtualenv (`--system-site-packages`, so apt's Pillow and NumPy are reused rather than rebuilt). The direct weather source brings pandas, which carries its own NumPy — keeping that out of the system Python is what stops it shadowing the one the framebuffer path uses
- adds the user to the `video` group so it can write `/dev/fb0` without sudo
- adds `fbcon=map:2` to `/boot/firmware/cmdline.txt` so the text console never draws over the display
- installs a scoped sudoers rule for the deploy script

### 2. Create config

```bash
cp config.example.toml config.toml
```

Set your observing site in `[location]`; that is the only thing you must edit. The default `weather.source = "direct"` fetches the forecast on the Pi itself and needs no credentials at all:

```toml
[weather]
source = "direct"

[location]
latitude = 51.4779
longitude = -0.0015
elevation = 47
timezone = "Europe/London"

[display]
mode = "animated"     # or "static" (redraw only when the data changes)
fps = 20
data_refresh_min = 15
```

The `[display]` section is optional; the values above are the defaults. To read from Home Assistant instead, set `source = "homeassistant"` and add an `[ha]` section with your URL and a long-lived access token (HA → Profile → Security → Long-Lived Access Tokens).

Both sources are the same underlying model, so they agree — `display.py --compare` fetches from each back to back and prints a per-value diff if you want to confirm it on your own site.

### 3. Deploy

From Windows (the deploy resolves the Pi by mDNS as `astro-pi.local`, so it works on either the wired or the wireless interface — if mDNS is unavailable, pass an explicit address with `-PiHost`):

```powershell
.\deploy.ps1
```

This copies the files, installs the Python dependencies, installs the `fbcon-detach` and display services, retires any legacy timer, and starts the always-on animated display.

---

## 🖥️ Running & preview

The always-on `touch2-stargazing.service` runs `display.py` as a daemon. For manual runs and development:

```bash
python3 display.py            # daemon (mode from config; default animated)
python3 display.py --once     # render one frame to the panel and exit
python3 display.py --save preview.png   # save a single composited frame (no panel needed)
python3 display.py --demo     # force a vivid clear-sky animation, ignoring the weather
python3 display.py --compare  # fetch from both weather sources and diff them
```

`--demo` is handy for checking the vivid end of the range without waiting for a clear night.

---

## 🧰 Case

A free 3D-printable case for the 5" Touch Display 2 + Pi 4 lives in [`case/`](case/README.md) — four parametric CadQuery parts (shell, Pi clamshell, twin bolt-on stands at a 20° lean, optional 40 mm fan). A Pi 5 variant of the two clamshell parts is also generated, though it has not been built on hardware and its display ribbon routes differently. It's a **CC BY remix of [RonnyS's Touch Display 2 case](https://www.printables.com/model/1377047-raspberry-pi-touch-display-2-case)**, which targets the 7" panel; this one is re-drawn for the 5". See [`case/README.md`](case/README.md) for print settings, hardware and assembly.

The project originally ran on a **Pimoroni Inky Impression 4"** with a bespoke stand (CadQuery frame + riser + WS2812B LED bezel ring). After moving to the self-lit Touch Display 2 that design was retired and archived, with full history, at [`adminfor/inky-impression-case`](https://forgejo.home.neilsayer.co.uk/adminfor/inky-impression-case).

---

## 🔧 Troubleshooting

| Symptom | Fix |
|---|---|
| Blank panel, or console/login text over the dashboard | The text console is still bound to `/dev/fb0`. Ensure `fbcon=map:2` is in `/boot/firmware/cmdline.txt` and reboot; `fbcon-detach.service` also unbinds it at start |
| `PermissionError` writing `/dev/fb0` | The user isn't in the `video` group — rerun `setup.sh`, or `sudo adduser <user> video` and re-login |
| Sky looks static / no visible animation | Heavy cloud legitimately calms the sky. Confirm with `python3 display.py --demo`; check the computed mood with `python3 -c "import tomllib,display; c=tomllib.load(open('config.toml','rb')); print(display.sky_params(display.make_fetcher(c)()))"` |
| Dashboard upside down / mirrored | Flip `ROTATE` in `display.py` between `Image.ROTATE_90` and `Image.ROTATE_270` |
| `ModuleNotFoundError: numpy` | `sudo apt install python3-numpy` (or rerun `setup.sh`) |
| `KeyError: 'ha'` in config | `config.toml` is missing the `[ha]` section header |
| 401 Unauthorized from HA | Token in `config.toml` is wrong or expired |

**Check logs / CPU:**

```bash
journalctl -u touch2-stargazing -f
systemctl status touch2-stargazing
```

The daemon uses roughly 80% of one Pi 4 core at 20 fps; lower `fps` in `config.toml` to reduce it.

---

## 📁 File structure

```
display.py              Main script (render + animation + framebuffer daemon)
config.toml             Local config (gitignored)
config.example.toml     Template ([ha] + [display])
deploy.ps1              Windows → Pi deploy script
setup.sh                One-time Pi setup (run with sudo)
systemd/
  touch2-stargazing.service   Always-on animated display daemon
  fbcon-detach.service        Frees /dev/fb0 from the text console
case/
  README.md               Print settings, hardware, assembly
  shell.py                Display shell (front frame + back plate)
  pi_models.py            Measured Pi 4 / Pi 5 connector tables
  case_bottom.py          Pi clamshell base (bay, walls, port sill, lid spigots)
  case_top.py             Ventilated lid (ports, fan grille + mounting)
  stand.py                Bolt-on desk stand — print 2
```
