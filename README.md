# 🌌 touch2-stargazing-display

A stargazing conditions display for the [Raspberry Pi Touch Display 2 (5")](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html), driven by a Raspberry Pi 4. It fetches live [AstroWeather](https://github.com/mawinkler/astroweather) forecast data — on the Pi itself, or from Home Assistant if you run it — and renders a colour-coded overnight forecast over a live, data-reactive animated night sky — no interaction required.

Rendered with Pillow at 1280×720 landscape and written straight to the Linux framebuffer (`/dev/fb0`, RGB565) — no X, no display server, no `inky` library.

**Highlights**

- Tonight's deep-sky verdict (EXCELLENT → NONE) in bold colour
- Condition bars: cloudless %, seeing, transparency, calm
- **A real image of the Moon** for the current hour — true phase, libration and terminator — with constellation and next new/full moon dates
- Footer grouped by type — astronomical (moon dates, dusk/dawn) on the right under the moon; meteorological (lifted index, weather) on the left
- Handles the no-astronomical-darkness case for midsummer at high latitudes
- **Live animated night sky** behind the dashboard: twinkling starfield, drifting clouds and occasional meteors, all **reactive to the actual conditions**
- **Touch controls** hidden until you tap: night mode, page rotation, brightness, and a true blank that drops the display to 0% CPU

---

## 📸 Display layout

```
┌───────────────────────────────────────────────────────────────┐
│ STARGAZING                                     Fri 24 Jul 21:58 │
│───────────────────────────────────────────────────────────────│
│ EXCELLENT                                                       │
│ Deep sky: 94%  -  Clear sky night                               │
│───────────────────────────────────────────────────────────────│
│ Cloudless    [█░░░░░░░]  0%   │      (photo of the Moon)        │
│ Seeing       [███░░░░░] 34%   │         Waxing Gibbous          │
│ Transparency [██░░░░░░] 12%   │           in Scorpius           │
│ Calm         [███████░] 89%   │                                 │
│───────────────────────────────────────────────────────────────│
│ Tomorrow: Cloudy (5%)               New 12 Aug  -  Full 29 Jul  │
│ LI: Over 6, very stable             Dusk 21:50  -  Dawn 04:39   │
│ Temp 24.7°C  -  Dew 12.0°C  -  RH 45%  -  Wind W 4.0 mph        │
└───────────────────────────────────────────────────────────────┘
        ...behind everything: a living sky — stars, clouds, meteors
        ...and on a tap, a control strip along the bottom edge
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

The moon card shows **a real image of the Moon** (set `display.moon_ring = true` to outline the full disc), fetched hourly from NASA SVS's Dial-a-Moon and cached on disk — actual phase, libration and terminator rather than a drawn approximation. If it can't be reached the display falls back to drawing the phase geometrically, so it degrades rather than breaks. It deliberately will not reuse an older cached frame: the phase moves about 12° a day, so yesterday's picture is simply wrong, and a correct drawing beats a beautiful lie.

Meteors streak occasionally through the night sky (rarer when cloudy). Star and cloud brightness always keep a visible floor, so the sky stays alive even on poor nights.

---

## 👆 Touch controls

The panel is a touchscreen, and the display reads it directly from `/dev/input/eventN` — no X, no Wayland, no extra packages.

Nothing is drawn until you touch the screen. **The first tap only reveals a control strip** along the bottom, which goes away again after six seconds; a second tap presses a button. That way an ambient display stays uncluttered, and a brush past the panel in the dark cannot change anything.

| Button | What it does |
|---|---|
| **Night** | Cycles the night filter off → dim → red, immediately, whatever the hour |
| **Pause** / **Resume** | Holds the current page instead of rotating |
| **Next** | Jumps to the next page straight away |
| **Dimmer** / **Brighter** | Backlight, via `/sys/class/backlight`. Never goes below the lowest visible step |
| **Blank** | Backlight off and compositing stopped — the display drops to **0% CPU** until you touch it again. The one setting that matters at the eyepiece |

A night mode picked by hand lapses the next time the sky crosses dusk or dawn: it is a change of mind about tonight, not a second schedule competing with the automatic one. Nothing else here is persisted either — `config.toml` is restored on restart, so the display always comes back to a known state.

Requires `display.mode = "animated"`, and an account in the `input` and `video` groups (`setup.sh` arranges both). Set `touch.enabled = false` to turn the whole thing off.

---

## 🛠️ Requirements

**Hardware** — the whole build, and roughly what it costs:

| Item | Qty | Notes |
|---|---|---|
| Raspberry Pi 4 Model B (2GB is plenty) | 1 | What this is built and proven on. See the Pi 5 note below |
| Raspberry Pi Touch Display 2, **5-inch** | 1 | 720×1280 DSI, ~£36. Ships with a Pi 4 DSI cable |
| Official Raspberry Pi USB-C PSU (5.1V/3A) | 1 | The printed stand is sized so this one's stiff cable clears the desk |
| microSD card, 16GB+ | 1 | Raspberry Pi OS Lite 64-bit |
| 3D-printed case and stands | 1 set | Optional — see [`case/`](case/README.md). ~150g of PETG |
| M2.5 screws and standoffs | 1 set | Only for the case; full list in [`case/README.md`](case/README.md) |

No soldering, no HAT, no GPIO wiring — the display is DSI and the case is all screws and standoffs.

> **A Pi 5 is untested for the software.** It needs a Display Adapter Cable for Pi 5 (22-way → 15-way, the one marked `DISPLAY`), and `display.py` assumes a 16-bit RGB565 `/dev/fb0` — a Pi 5 gets its framebuffer from DRM emulation, which commonly comes up 32bpp, so the packing code would need a format branch. There is no performance reason to move either: the render loop is single-threaded and uses about one core of four. The case *does* have a printable Pi 5 variant.

**Software**
- Raspberry Pi OS Lite 64-bit (Trixie / Bookworm), headless (`multi-user.target`)
- Python 3.11+
- **No Home Assistant required.** Weather comes from [pyastroweatherio](https://github.com/mawinkler/pyastroweatherio) — the library the Home Assistant [AstroWeather](https://github.com/mawinkler/astroweather) integration itself wraps — talking straight to MET Norway and Open-Meteo. If you do run Home Assistant with that integration, set `weather.source = "homeassistant"` and the display reads its sensors instead.
- **An internet connection**, but nothing else on your network. Three public services are used: the weather above, NASA SVS for the lunar image, and CDS Strasbourg for the deep-sky cutouts. No broker, no container, no server of your own. Each one degrades on its own if it's unreachable — the moon falls back to a drawn phase, the cutouts to drawn glyphs, and cached weather keeps the dashboard up.

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
- installs `fonts-ibm-plex` (the display's typeface), `fonts-dejavu-core` (fallback), `python3-pil`, `python3-numpy`, `python3-requests`, `python3-pip`, `python3-venv`
- builds the display's virtualenv (`--system-site-packages`, so apt's Pillow and NumPy are reused rather than rebuilt). The direct weather source brings pandas, which carries its own NumPy — keeping that out of the system Python is what stops it shadowing the one the framebuffer path uses
- adds the user to the `video` group (framebuffer + backlight) and `input` group (touchscreen)
- adds `fbcon=map:2` to `/boot/firmware/cmdline.txt` so the text console never draws over the display
- installs a deliberately narrow sudoers rule for the deploy script — see the security note below

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

The `[display]` section is optional; the values above are the defaults.

**Night mode** (`night_mode = "off" | "dim" | "red"`) applies between real dusk and dawn rather than on a clock schedule, because the point is to stop the panel ruining your dark adaptation and that starts when the sky does. `"dim"` keeps the colours at `night_dim`% brightness; `"red"` goes monochrome red, which is what observers use because long wavelengths leave scotopic vision alone. Nothing is lost by going red — no reading on this display is carried by colour alone, so the verdict word, the numbers and the bar lengths all still say what they said. It is applied to the finished frame, so it covers the animated sky and the sky photographs too, and it costs no measurable CPU. To read from Home Assistant instead, set `source = "homeassistant"` and add an `[ha]` section with your URL and a long-lived access token (HA → Profile → Security → Long-Lived Access Tokens).

Both sources are the same underlying model, so they agree — `display.py --compare` fetches from each back to back and prints a per-value diff if you want to confirm it on your own site.

### 3. Deploy

From Windows (the deploy resolves the Pi by mDNS as `astro-pi.local`, so it works on either the wired or the wireless interface — if mDNS is unavailable, pass an explicit address with `-PiHost`):

```powershell
.\deploy.ps1
```

This copies the files, installs the Python dependencies, stages the systemd units, and restarts the always-on animated display. **The very first deploy (and any later one that changes a unit file) will print one extra command to run** — installing a systemd unit is done under interactive sudo on the Pi, not automatically.

### A note on security

- **The NOPASSWD sudoers rules cover exactly two commands**: restarting the display service and kicking a first UpTonight run. In particular the deploy account **cannot** install unit files unattended — a unit executes as root, so `systemd/install-units.sh` asks for a password instead. If you widen these rules for convenience, understand that you are handing root to anything that ever compromises the deploy account.
- **Check for `/etc/sudoers.d/90-cloud-init-users`.** A Pi provisioned with Raspberry Pi Imager gets its first user `NOPASSWD:ALL` from cloud-init, which silently defeats the scoped rules above — `sudo -l` will show it. If your account has a usable password (`passwd -S <user>` says `P` — confirm this first, or you lose easy root), remove that file and sudo goes back to asking.
- **`deploy.ps1` uses `StrictHostKeyChecking=accept-new`**: first contact trusts the key it sees, after which a changed host key aborts the deploy. If you reflash the Pi, clear the stale key with `ssh-keygen -R astro-pi.local`.
- `config.toml` is deployed with mode 600, since it can carry a Home Assistant token.
- Python dependencies install **unpinned** (current Pi OS ships Python versions the upstream pins predate). That is a supply-chain trade-off: you get current wheels, not vetted ones. Pin them if your threat model minds.

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

The project originally ran on a **Pimoroni Inky Impression 4"** with a bespoke stand (CadQuery frame + riser + WS2812B LED bezel ring). After moving to the self-lit Touch Display 2 that design was retired and archived, with its full history, to a separate private repository.

---

## 🔧 Troubleshooting

| Symptom | Fix |
|---|---|
| Blank panel, or console/login text over the dashboard | The text console is still bound to `/dev/fb0`. Ensure `fbcon=map:2` is in `/boot/firmware/cmdline.txt` and reboot; `fbcon-detach.service` also unbinds it at start |
| `PermissionError` writing `/dev/fb0` | The user isn't in the `video` group — rerun `setup.sh`, or `sudo adduser <user> video` and re-login |
| Sky looks static / no visible animation | Heavy cloud legitimately calms the sky. Confirm with `python3 display.py --demo`; check the computed mood with `python3 -c "import tomllib,display; c=tomllib.load(open('config.toml','rb')); print(display.sky_params(display.make_fetcher(c)()))"` |
| Dashboard upside down / mirrored | Flip `ROTATE` in `display.py` between `Image.ROTATE_90` and `Image.ROTATE_270` |
| `ModuleNotFoundError: numpy` | `sudo apt install python3-numpy` (or rerun `setup.sh`) |
| Tapping the panel does nothing | The log will say `No touchscreen found` if the account isn't in the `input` group — rerun `setup.sh`, or `sudo adduser <user> input` and reboot. Also check `touch.enabled` is true and `display.mode` is `animated`; touch is not wired into static mode |
| Taps land a quarter-turn away from your finger | The touch mapping follows `ROTATE`, so if you flipped that, flip it here too. Check it directly with `python3 touch.py`, which prints raw and mapped coordinates for each tap |
| Buttons fire when you meant to wake the strip | They shouldn't — the first tap only reveals it. If the strip was already up (it stays for `touch.strip_seconds`), the tap counts as a press; raise or lower that value to taste |
| Drawn moon instead of a photograph | The Dial-a-Moon fetch failed — the log says why. It will not substitute an older cached frame, because the phase moves ~12°/day and yesterday's picture would be wrong |
| `KeyError: 'ha'` in config | Only applies with `weather.source = "homeassistant"`: `config.toml` is missing the `[ha]` section header |
| 401 Unauthorized from HA | Likewise — the token in `config.toml` is wrong or expired |

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
touch.py                Touchscreen reader (evdev; run alone to check mapping)
config.toml             Local config (gitignored)
config.example.toml     Template ([weather] + [location] + [display] + [touch])
deploy.ps1              Windows → Pi deploy script
setup.sh                One-time Pi setup (run with sudo)
systemd/
  touch2-stargazing.service   Always-on animated display daemon
  fbcon-detach.service        Frees /dev/fb0 from the text console
  install-units.sh            Installs the units - interactive sudo, by design
case/
  README.md               Print settings, hardware, assembly
  shell.py                Display shell (front frame + back plate)
  pi_models.py            Measured Pi 4 / Pi 5 connector tables
  case_bottom.py          Pi clamshell base (bay, walls, port sill, lid spigots)
  case_top.py             Ventilated lid (ports, fan grille + mounting)
  stand.py                Bolt-on desk stand — print 2
```

---

## 🙏 Acknowledgements

This project is a thin dashboard over other people's hard work.

- **[AstroWeather](https://github.com/mawinkler/astroweather) and [pyastroweatherio](https://github.com/mawinkler/pyastroweatherio)** by Markus Winkler (MIT). The seeing, transparency, calm and deep-sky figures are its model, not a reimplementation of it — the display calls the same library the Home Assistant integration wraps.
- **[UpTonight](https://github.com/mawinkler/uptonight)**, also by Markus Winkler, computes the target lists on the Pi.
- **Weather data** from [MET Norway](https://www.met.no/) and [Open-Meteo](https://open-meteo.com/), via the above.
- **Sky imagery** from the [`hips2fits` service](https://alasky.cds.unistra.fr/hips-image-services/hips2fits) at **CDS, Strasbourg Observatory, France**, rendering the **DSS2 colour** HiPS survey. The Digitized Sky Survey was produced at the Space Telescope Science Institute under U.S. Government grant NAG W-2166, from photographic data of the Oschin Schmidt Telescope on Palomar Mountain and the UK Schmidt Telescope.
- **Lunar imagery** from **[Dial-a-Moon](https://svs.gsfc.nasa.gov/4442)**, by **Ernie Wright** at **NASA's Scientific Visualization Studio**, rendered from Lunar Reconnaissance Orbiter data. SVS content is public domain. Each frame shows the Moon's real phase, libration and terminator for that hour — the display is compositing an actual render, not drawing an approximation.
- **The case** is a remix of **"Raspberry Pi Touch Display 2 Case" by RonnyS** ([Printables 1377047](https://www.printables.com/model/1377047-raspberry-pi-touch-display-2-case)), used under CC BY.

## 📄 Licence

**GPL-3.0** — see [LICENSE](LICENSE). Chosen to match [pilomar](https://github.com/Short-bus/pilomar), the Pi miniature-observatory project this one keeps company with.

**Except `case/`**, which is **CC BY** rather than GPL, because it is a remix of RonnyS's CC-BY model and that licence carries forward. Credit RonnyS and this project if you remix it further.
