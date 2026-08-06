# 🌌 touch2-stargazing-display

A stargazing conditions display for the [Raspberry Pi Touch Display 2](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html). It fetches live [AstroWeather](https://github.com/mawinkler/astroweather) forecast data — on the Pi itself, or from Home Assistant if available — and renders an overnight forecast over a live, data-reactive animated night sky — no interaction required.

Rendered with Pillow and written straight to the Linux framebuffer (`/dev/fb0`) — no X and no display server.

**There are two builds**, sharing one engine. Pick the one that matches the hardware:

| | [`build5/`](build5/) | [`build10/`](build10/) |
|---|---|---|
| Panel | Touch Display 2, **5"** | Touch Display 2, **10.1"** |
| Board | Pi 4 | **Pi 5 or CM** — four-lane DSI, a Pi 4 cannot drive it |
| Canvas | 1280×720 landscape, rotated to the panel | 1200×1920 portrait, no rotation |
| Pages | Conditions, targets | Conditions, targets, **meteors** |
| Status | **Proven in service** | **In development — not yet run on hardware** |

Everything that is not layout — both weather sources, the target reports, the imagery, the animated sky, night mode, touch, the framebuffer — lives in [`core/`](core/) and is shared. The rest of this README describes the 5" build unless it says otherwise; substitute `build10/` for `build5/` in the commands to install the other one.

**Highlights**

- Tonight's deep-sky verdict (EXCELLENT → NONE) spelled out in bold display type
- Condition bars: cloudless %, seeing, transparency, calm — a reading below its warning mark is drawn hollow instead of filled
- **A real image of the Moon** for the current hour — true phase, libration and terminator — with constellation and next new/full moon dates
- Footer grouped by type — astronomical (moon dates, dusk/dawn) on the right under the moon; meteorological (lifted index, weather) on the left
- Handles the no-astronomical-darkness case for midsummer at high latitudes
- **Live animated night sky** behind the dashboard: **the actual stars overhead**, plotted from a catalogue at their real positions for the site and the moment, plus drifting clouds and meteors from tonight's active showers — all **reactive to the actual conditions**
- **Touch controls** hidden until the screen is tapped: night mode, page rotation, brightness and a true blank that drops the display to 0% CPU

---

## 📸 Display layout

### The 5-inch build

Two pages rotate over the same continuous animated sky. Both shots are real frames from the panel's own Pi 4, rendered from live data:

**Page 1 — tonight's conditions**

![The conditions page: a large EXCELLENT verdict in pale blue-white, four labelled condition bars with percentages, and a photographic last-quarter Moon captioned Last Quarter in Aries. The Seeing bar reads 36% and is drawn as a hollow outline rather than filled, because it falls below its warning mark; the other three are filled. A footer gives tomorrow's forecast, lifted index, temperature, dew point, humidity and wind.](screenshots/conditions.png)

> **Dusk / Dawn** is used in that footer, not sunrise/sunset: AstroWeather's sun rise/set entities report **civil twilight** bounds (sun 6° below the horizon), ~40 min off the geometric sun crossing. True darkness is tracked separately (`astronomical_night_duration`) and drives the "NO DARK SKY" state.

**Page 2 — tonight's targets**

![The targets page: a dusk-to-dawn timeline with the astronomical dark window highlighted and a moon-up strip above it; an altitude-versus-bearing plot of the Moon and planets; and four deep-sky cards, each with a real sky photograph, object type, constellation, peak altitude and time.](screenshots/targets.png)

The page-2 timeline only appears once UpTonight has run, and the page leaves the rotation entirely if it has produced nothing, so an empty page is never shown.

**Night mode — the same page after dark**

![The conditions page in red night mode: the identical layout rendered entirely in shades of red on black, including the photograph of the Moon. The verdict, the condition bars, the percentages and the footer are all still legible, and the hollow Seeing bar still reads as hollow; only hue has gone.](screenshots/night-red.png)

Between real dusk and dawn — not on a clock schedule — the finished frame is put through a red filter, because long wavelengths leave dark-adapted vision alone. The whole frame is filtered rather than the palette swapped, which keeps the lunar photograph and the deep-sky cutouts from glowing white.

Nothing is lost to it, because no state on this display is encoded in hue at all. The verdict is a word, every bar has a number and a length, and a reading below its threshold is hollow rather than a different colour. `night_mode = "dim"` keeps full colour at reduced brightness instead.

### Colour marks real objects; state is neutral

If something here is coloured it is a thing that is actually up there — the Moon, a planet, a comet, a photograph of a nebula. If it is a judgement about tonight it is the same neutral blue-white as everything else, and it says what it means by size, length, position, or the word itself.

### The 10.1-inch build

Portrait, 2.5× the pixels at slightly lower density, so the space goes on content rather than on scale. These are real frames rendered from live data, but **on a development Pi, not yet on the panel itself**:

**Page 1 — conditions.** The Moon takes the middle band at 600px across; the source frame is 730px, so this is close to native rather than an enlargement. Under it are the numbers that come with the frame and used to be discarded — age, distance, apparent diameter, and libration as the direction the near side is tipped.

![The 10.1-inch conditions page in portrait: a large EXCELLENT verdict, a 600-pixel photograph of a last-quarter Moon captioned Last Quarter in Aries with its age, distance, diameter and libration, four condition bars with the below-threshold Seeing bar drawn hollow, and a footer of forecast, dusk and dawn times and weather.](screenshots/10in-conditions.png)

**Page 2 — targets.** One altitude-versus-bearing plot carries the planets *and* the deep-sky objects on a full 0–90° axis. The 5" build keeps the two apart because it has far less vertical room: UpTonight selects deep-sky targets for high altitude, while the planets stay near the ecliptic and so occupy a lower band, and a short axis holding both compresses whichever band is lower. How far apart those bands sit depends on latitude — from the reference site at 51°N the objects peak around 70–85° and the planets stay below about 35°, but nearer the equator the ecliptic rides much higher and the two overlap. Every position on the plot is for the single instant named above it.

![The 10.1-inch targets page: a dusk-to-dawn timeline, then an altitude-versus-bearing plot showing six deep-sky objects between 60 and 77 degrees and four planets below 30, each labelled with its bearing, above six deep-sky cards with real sky photographs.](screenshots/10in-targets.png)

**Page 3 — meteors.** Which showers are actually running, from a table of orbital constants indexed by solar longitude, with the rate an observer would really count once radiant altitude, cloud and moonlight are accounted for.

![The 10.1-inch meteor page: solar longitude 133.2 degrees, with Southern Delta Aquariids 6 degrees past peak and Perseids peaking in 7 days, each showing radiant altitude and bearing and an estimated rate of one to two per hour against its zenithal hourly rate at peak, plus a sporadic background of about two per hour.](screenshots/10in-meteors.png)

---

## ✨ The animated sky

The sky is a live layer composited behind the dashboard each frame (about 14 fps on a Pi 4 - see the note under Running); the dashboard itself is an RGBA overlay (transparent where the sky should show, opaque content on top). The animation **reflects the conditions** rather than just decorating:

| Condition | Effect |
|---|---|
| Seeing / transparency / calm | Star brightness and twinkle (crisper when clear) |
| Cloud cover | Number of soft drifting clouds (0 → 7), which dim the stars they pass |
| Wind speed | Drift speed of stars and clouds |
| No astronomical darkness | Sky washes to twilight blue; meteors suppressed |

The moon card shows **a real image of the Moon** (set `display.moon_ring = true` to outline the full disc), fetched hourly from NASA SVS's Dial-a-Moon and cached on disk — actual phase, libration and terminator rather than a drawn approximation. If it can't be reached the display falls back to drawing the phase geometrically, so it degrades rather than breaks. It deliberately will not reuse an older cached frame: the phase moves about 12° a day, so yesterday's picture is simply wrong and the correct drawing is better than an attractive inaccuracy.

Star and cloud brightness always keep a visible floor, so the sky stays alive even on poor nights.

### The starfield is the real sky

The stars behind the dashboard are not decoration. They are plotted from the Yale Bright Star Catalogue down to magnitude 6.5 — about 8,400 stars — at their true altitude and azimuth for the configured site and the current moment, recomputed every minute. Constellations are therefore recognisable, and they move because the Earth turns rather than because a drift constant says so. The catalogue ships in the repository, so this needs no network.

**A panel cannot know which way it is facing, so the direction it looks is configuration rather than something inferred:**

```toml
[sky]
real_stars = true
camera_azimuth = 180    # degrees: 0 = north, 90 = east, 180 = south
camera_altitude = 45    # degrees above the horizon at the centre of the view
field_of_view = 70      # degrees, vertical (build10 defaults to 90)
```

The default view faces **due south at 45° up**, which is where objects transit and therefore the most useful direction at northern latitudes. Point it wherever the window actually faces, or wherever the view is best. The horizontal field is derived from the panel's aspect ratio so the scale stays even in both directions — which means the landscape 5" build sees considerably more sky than the portrait 10.1-inch one at the same vertical setting.

Brightness and star size are mapped for legibility at a distance rather than photometrically: the ordering is faithful, so Sirius still dominates, but a magnitude 6.5 star is drawn at a visible floor rather than at its true relative brightness. Set `real_stars = false` for the earlier randomised starfield.

### The meteors follow tonight's real showers

**They are representative, not observations.** No meteor on the panel corresponds to a meteor in the sky, and nothing here is a live feed. What is real is everything governing them — when they fall, how often, and which way they go.

**The cadence** comes from the same computation that fills the 10.1-inch meteor page: which showers are running, how high each radiant sits, and how much of the rate cloud and moonlight remove. So a quiet night in March shows almost nothing and a clear Perseid peak is busy, and if nothing is falling, nothing falls here either. The rate is deliberately time-compressed (`meteor_compression`, default 20), because a truthful three-an-hour makes an animated sky look broken; it scales what is there and does not invent what is not.

**The direction** is the true radiant. A meteor is drawn from one of tonight's active showers in proportion to that shower's rate, and travels away from where that shower's radiant actually is in the projected sky, so it converges on a point that agrees with the stars around it. Trails shorten towards the radiant, because a path pointing at the observer is seen end-on. The radiant is often off the edge of the panel, which is not a fault: the view faces one direction and the shower is somewhere else, so its meteors sweep in near-parallel from that side. Meteors belonging to no shower — the sporadic background, which is most of them on an ordinary night — keep an arbitrary direction, because they genuinely have none. Setting `sky.real_stars = false` returns the meteors to arbitrary directions along with the starfield.

---

## 👆 Touch controls

As the panel is a touchscreen, there are touch controls. The display reads them directly from `/dev/input/eventN`, so neither X nor Wayland is required.

No controls are drawn until the screen is touched. **The first tap only reveals a control strip** along the bottom, which disappears after six seconds; a second tap presses a button. That way the ambient display stays uncluttered and brushing past the panel in the dark can't change anything.

| Button | What it does |
|---|---|
| **Night** | Cycles the night filter off → dim → red, immediately, whatever the hour |
| **Pause** / **Resume** | Holds the current page instead of rotating |
| **Next** | Jumps to the next page straight away |
| **Dimmer** / **Brighter** | Backlight, via `/sys/class/backlight`. Never goes below the lowest visible step |
| **Blank** | Backlight off and compositing stopped — the display drops to **0% CPU** until it is touched again. |

A night mode picked by hand lapses the next time the sky crosses dusk or dawn: it is a change of state for that night, not a second schedule competing with the automatic one. Nothing else in the touch controls is persisted — `config.toml` is restored on restart, so the display always comes back to a known state.

This functionality requires `display.mode = "animated"`, and an account in the `input` and `video` groups (`setup.sh` arranges both). Set `touch.enabled = false` to turn the touch controls off.

---

## 🛠️ Requirements

**Hardware** — the whole build, and roughly what it costs:

| Item | Qty | Notes |
|---|---|---|
| Raspberry Pi 4 Model B (2GB is plenty) | 1 | What this is built and proven on. See the Pi 5 note below |
| Raspberry Pi Touch Display 2, **5-inch** | 1 | 720×1280 DSI. Ships with a Pi 4 DSI cable |
| Official Raspberry Pi USB-C PSU (5.1V/3A) | 1 | The printed stand is sized so this one's stiff cable clears the desk |
| microSD card, 16GB+ | 1 | Raspberry Pi OS Lite 64-bit |
| 3D-printed case and stands | 1 set | Optional — see [`case/`](case/README.md). ~150g of PETG |
| M2.5 screws and standoffs | 1 set | Only for the case; full list in [`case/README.md`](case/README.md) |

No soldering, no HAT, no GPIO wiring — the display is DSI and the case is all screws and standoffs. If a 5v GPIO pin is required then the 0 v pin of the display connector can be shifted to the middle pin and the connector moved right by one pin. This frees up Pin 2. Normally the connector connects via Pin 2 and Pin 6, which blocks pin 4.

> **Using a Pi 5 for the 5" build gains nothing.** It needs a Display Adapter Cable for Pi 5 (22-way → 15-way, the one marked `DISPLAY`), and there is no performance reason to move: the render loop is single-threaded and uses about one core of four. The case *does* have a printable Pi 5 variant.
>
> The framebuffer format differs between the two panels and is **detected at runtime**, so neither build needs configuring for it: the 5" reports 16bpp RGB565, the 10.1" on a Pi 5 reports 32bpp XRGB8888. To see what a board presents:
> ```bash
> cat /sys/class/graphics/fb0/bits_per_pixel /sys/class/graphics/fb0/virtual_size
> ```
> A padded framebuffer — one whose `stride` exceeds width × bytes-per-pixel — is not supported, and is refused at startup rather than rendered as a diagonal smear. Neither panel pads.

**For the 10.1" build**, the table changes: a **Raspberry Pi 5** (its DSI is four-lane, which the panel requires), the **10.1-inch** Touch Display 2, a 27W USB-C PSU, and the official **Pi 5 Active Cooler**, which is required rather than optional on a continuous render loop.

**The 10.1" build deliberately has no case, and does not need one.** The Pi bolts to the standard 58 × 49 mm hole pattern in the middle of the panel's back, which mounts it properly on its own — unlike the 5", where the case and the Pi share one screw chain. Leaving the board open also suits the active cooler, which wants free air rather than a grille. The panel is 247 mm tall in its native portrait with the Pi centred, so there is roughly 80–95 mm below the board for the display ribbon and the power cable to turn and drop; the 5" needs a stand partly because rotating it to landscape leaves only about 18 mm there. A stand is still wanted for the 10", but that is a question of how it sits on a desk, not of enclosing anything.

**Software**
- Raspberry Pi OS Lite 64-bit (Trixie / Bookworm), headless (`multi-user.target`)
- Python 3.11+
- **No Home Assistant required.** Weather comes from [pyastroweatherio](https://github.com/mawinkler/pyastroweatherio) — the library the Home Assistant [AstroWeather](https://github.com/mawinkler/astroweather) integration itself wraps — talking straight to MET Norway and Open-Meteo. If Home Assistant is available with that integration, then set `weather.source = "homeassistant"` and the display reads its sensors instead.
- **An internet connection**, but nothing else on the local network. Three public services are used: the weather above, NASA SVS for the lunar image, and CDS Strasbourg for the deep-sky cutouts. No broker, no container, no local servers. Each one degrades on its own if it's unreachable — the moon falls back to a drawn phase, the cutouts to drawn glyphs, and cached weather keeps the dashboard up.

---

## 🚀 Setup

### 1. Pi one-time setup

The 5" Touch Display 2 is auto-detected over DSI and needs no device-tree overlay. **The 10.1" is not**: `display_auto_detect=1` is firmware-side probing, so firmware older than the panel does not recognise it, and the symptom is no output *and* no DSI connector at all in `/sys/class/drm`. For that panel, add the overlay to `/boot/firmware/config.txt` and reboot before running setup:

```
dtoverlay=vc4-kms-dsi-ili79600-10-1inch
```

Append `,dsi0` only if the ribbon is in CAM/DISP 0 — the overlay defaults to DSI1, which is CAM/DISP 1. Then run the setup script:

```bash
# Copy the build's setup.sh to the Pi, then:
sudo bash setup.sh          # or: sudo bash setup.sh <username>
sudo reboot                 # required: setup.sh adds fbcon=map:2 to the kernel cmdline
```

With no argument it sets everything up for the account that invoked `sudo`, which is almost always what is required. Pass a username only if installing on behalf of a different account.

`setup.sh`:
- installs `fonts-ibm-plex` (the display's typeface), `fonts-dejavu-core` (fallback), `python3-pil`, `python3-numpy`, `python3-requests`, `python3-pip`, `python3-venv`
- builds the display's virtualenv, reusing apt's Pillow and NumPy rather than rebuilding them
- adds the user to the `video` group (framebuffer + backlight) and `input` group (touchscreen)
- adds `fbcon=map:2` to `/boot/firmware/cmdline.txt` so the text console never draws over the display
- installs a deliberately narrow sudoers rule for the deploy script — see the security note below

### 2. Create config

```bash
cp build5/config.example.toml build5/config.toml
```

Set the desired observing site in `[location]`; that is the only thing that MUST be edited (unless the site is Greenwich, London, UK, which is the default). The default `weather.source = "direct"` fetches the forecast on the Pi itself and needs no credentials at all:

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

**Night mode** (`night_mode = "off" | "dim" | "red"`) applies between real dusk and dawn rather than on a clock schedule, because the point is to stop the panel ruining dark adaptation and that starts when the dark sky does. `"dim"` keeps the colours at `night_dim`% brightness; `"red"` goes monochrome red because long wavelengths leave low-light vision alone. Nothing is lost by going red — no reading is carried by colour alone, so the verdict word, the numbers and the bar lengths all still say what they said. It applies to the finished frame, so it covers the animated sky and the sky photographs too.

To read from Home Assistant instead, set `source = "homeassistant"` and add an `[ha]` section with the HA URL and a long-lived access token (HA → Profile → Security → Long-Lived Access Tokens).

Both sources are the same underlying model, so they agree — `display.py --compare` fetches from each back to back and prints a per-value diff if local confirmation is required.

### 3. Deploy

From Windows:

```powershell
.\build5\deploy.ps1 -User <pi-username> -PiHost <hostname-or-ip>
```

Both default to the reference build's values (username `operations` and hostname `astro-pi.local`), so `.\build5\deploy.ps1` alone works once the local ones match — otherwise pass them. Unlike `setup.sh`, this runs on a PC and talks to the Pi over SSH, so it cannot infer the remote account name. The host is resolved by mDNS, which works on either the wired or the wireless interface; use an explicit address if mDNS is unavailable.

This copies the files, installs the Python dependencies, stages the systemd units, and restarts the always-on animated display. **The very first deploy (and any later one that changes a unit file) will print one extra command to run** — installing a systemd unit is done under interactive sudo on the Pi, not automatically.

### A note on security

- **The NOPASSWD sudoers rules cover exactly two commands**: restarting the display service and kicking a first UpTonight run. In particular the deploy account **cannot** install unit files unattended — a unit executes as root, so `build5/systemd/install-units.sh` asks for a password instead. If these rules are widened for convenience, understand that root is being handed to anything that ever compromised the deploy account.
- **Check for `/etc/sudoers.d/90-cloud-init-users`.** A Pi provisioned with Raspberry Pi Imager gets its first user `NOPASSWD:ALL` from cloud-init, which silently defeats the scoped rules above — `sudo -l` will show it. If the account has a usable password (`passwd -S <user>` says `P` — confirm this first, or lose easy root), remove that file and sudo goes back to asking.
- **`deploy.ps1` uses `StrictHostKeyChecking=accept-new`**: first contact trusts the key it sees, after which a changed host key aborts the deploy. If the Pi is reflashed, clear the stale key with `ssh-keygen -R astro-pi.local`.
- `config.toml` is deployed with mode 600, since it can carry a Home Assistant token.
- Python dependencies install **unpinned** (current Pi OS ships Python versions the upstream pins predate). That is a supply-chain trade-off: current wheels are used, not vetted ones. Pin them if that suits the threat model. The riskiest parsers — Pillow, requests, urllib3, NumPy — deliberately come from **apt**, not pip, so Debian's security team patches them; keep that working by running `apt upgrade` occasionally or installing `unattended-upgrades`.
- **Both services run sandboxed** (`NoNewPrivileges`, `ProtectSystem=full` and friends): they parse data fetched from the internet, so the units assume compromise and bound it — code inside the service cannot invoke sudo at all, whatever the sudoers file says. The unit comments record which protections are deliberately absent and why.
- **`sudo bash harden-pi.sh` does the last two**, and neither is completed by `setup.sh` — they change the machine logon mode, which an application installer should not affect. It switches SSH to key-only (once passwordless sudo is off, the account password is the box's root gate and shouldn't be guessable over the network) and installs `unattended-upgrades`. It refuses to run unless the key is already installed, validates the config, rolls back on failure, and reloads rather than restarts sshd so it cannot strand the access mid-session. **Afterwards root needs the key *and* the password — on a Pi with no keyboard, losing both means pulling the SD card.**

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

**This is for the 5" build only.** The 10.1" panel mounts and cools its Pi perfectly well with the board left open — see the note under Requirements.

The project originally ran on a **Pimoroni Inky Impression 4"** with a bespoke stand (CadQuery frame + riser + WS2812B LED bezel ring). After moving to the self-lit Touch Display 2 that design was retired and archived, with its full history, to a separate private repository.

---

## 🔧 Troubleshooting

| Symptom | Fix |
|---|---|
| Blank panel, or console/login text over the dashboard | The text console is still bound to `/dev/fb0`. Ensure `fbcon=map:2` is in `/boot/firmware/cmdline.txt` and reboot; `fbcon-detach.service` also unbinds it at start |
| Dark panel while the service is healthy and logging normally | The display was never woken: `fbcon=map:2` means no console performs a modeset, and a Pi 5 with `disable_fw_kms_setup=1` has no firmware-set mode either, so the CRTC stays off while frames render into a buffer nobody scans out. The daemon now issues an unblank when it opens the framebuffer, so this should not recur — confirm with `cat /sys/class/drm/card*-DSI-*/enabled` (want `enabled`) and `cat /sys/class/backlight/*/bl_power` (want `0`, not `4`) |
| `PermissionError` writing `/dev/fb0` | The user isn't in the `video` group — rerun `setup.sh`, or `sudo adduser <user> video` and re-login |
| Sky looks static / no visible animation | Heavy cloud legitimately calms the sky. Confirm with `python3 display.py --demo`; check the computed mood with `python3 -c "import tomllib,display; c=tomllib.load(open('config.toml','rb')); print(display.sky_params(display.make_fetcher(c)()))"` |
| Dashboard upside down / mirrored | Flip `ROTATE` in `display.py` between `Image.ROTATE_90` and `Image.ROTATE_270` |
| `ModuleNotFoundError: numpy` | `sudo apt install python3-numpy` (or rerun `setup.sh`) |
| Tapping the panel does nothing | The log will say `No touchscreen found` if the account isn't in the `input` group — rerun `setup.sh`, or `sudo adduser <user> input` and reboot. Also check `touch.enabled` is true and `display.mode` is `animated`; touch is not wired into static mode |
| Taps land a quarter-turn away from a finger | The touch mapping follows `ROTATE`, so if that is flipped, flip it here too. Check it directly with `python3 touch.py`, which prints raw and mapped coordinates for each tap |
| A button fires when the tap was only meant to wake the strip | The first tap only reveals it. If the strip was already up (it stays for `touch.strip_seconds`), the tap counts as a press; raise or lower that value to suit |
| Drawn moon instead of a photograph | The Dial-a-Moon fetch failed — the log says why. It will not substitute an older cached frame, because the phase moves ~12°/day and yesterday's picture would be wrong |
| `KeyError: 'ha'` in config | Only applies with `weather.source = "homeassistant"`: `config.toml` is missing the `[ha]` section header |
| 401 Unauthorized from HA | Likewise — the token in `config.toml` is wrong or expired |

**Check logs / CPU:**

```bash
journalctl -u touch2-stargazing -f
systemctl status touch2-stargazing
```

The daemon uses one Pi 4 core continuously. **`fps` is a ceiling, not a promise:** on the reference build the loop settles at **roughly 14 fps** with `fps = 20` set. Lowering `fps` below that does reduce CPU; raising it above that does nothing.

---

## 📁 File structure

There are two builds, differing in panel and board. They share one engine in
`core/`; each build folder holds only what is specific to its hardware — layout,
config, systemd units and deploy script. A build folder plus `core/` is
everything that gets installed on a Pi.

```
core/                   Shared engine: weather sources, target reports, imagery,
                        animated sky, night filter, framebuffer, touch controls
build5/                 5" Touch Display 2 on a Pi 4 (720x1280) - the reference build
  display.py              Entry point and 1280x720 layout
  touch.py                Touchscreen reader (evdev; run alone to check mapping)
  config.toml             Local config (gitignored)
  config.example.toml     Template ([weather] + [location] + [display] + [touch])
  deploy.ps1              Windows → Pi deploy script
  setup.sh                One-time Pi setup (run with sudo)
  systemd/
    touch2-stargazing.service   Always-on animated display daemon
    fbcon-detach.service        Frees /dev/fb0 from the text console
    install-units.sh            Installs the units - interactive sudo, by design
build10/                10.1" Touch Display 2 on a Pi 5 (1200x1920) - in progress
screenshots/            README images, regenerated with display.py --save
harden-pi.sh            Optional: key-only SSH + automatic security updates
case/
  README.md               Print settings, hardware, assembly
  shell.py                Display shell (front frame + back plate)
  pi_models.py            Measured Pi 4 / Pi 5 connector tables
  case_bottom.py          Pi clamshell base (bay, walls, port sill, lid spigots)
  case_top.py             Ventilated lid (ports, fan grille + mounting)
  stand.py                Bolt-on desk stand — print 2
```

---

## 💬 Feedback and contributions

Bug reports, questions and build photos are all welcome via [Issues](https://github.com/alienryes/touch2-stargazing-display/issues).

Two areas where reports are especially useful, because they cannot be verified here:

- **The Pi 5 case variant has never been built on hardware.** It is derived from the board model and checked in software only, and its display ribbon routes differently — see [`case/README.md`](case/README.md) before committing to a print.
- **Other latitudes.** The reference build sits at 51°N. The targets page caps its altitude axis at 70° because nothing near the ecliptic rises higher from there; much further south that will clip real objects, and `PAN_ALT_MAX` in `display.py` is the value to raise.

---

## 🙏 Acknowledgements

This project is a thin dashboard over other people's hard work.

- **[AstroWeather](https://github.com/mawinkler/astroweather) and [pyastroweatherio](https://github.com/mawinkler/pyastroweatherio)** by Markus Winkler (MIT). The seeing, transparency, calm and deep-sky figures are its model, not a reimplementation of it — the display calls the same library the Home Assistant integration wraps.
- **[UpTonight](https://github.com/mawinkler/uptonight)**, also by Markus Winkler, computes the target lists on the Pi.
- **Weather data** from [MET Norway](https://www.met.no/) and [Open-Meteo](https://open-meteo.com/), via the above.
- **The star catalogue** behind the real sky in both builds is the **Yale Bright Star Catalogue** (Hoffleit & Warren, 5th revised edition), obtained from **VizieR at CDS, Strasbourg Observatory, France** (catalogue V/50) and trimmed to magnitude 6.5. It ships in the repository as `core/data/stars.tsv`, so the display needs no network to draw the sky.
- **Sky imagery** from the [`hips2fits` service](https://alasky.cds.unistra.fr/hips-image-services/hips2fits) at **CDS, Strasbourg Observatory, France**, rendering the **DSS2 colour** HiPS survey. The Digitized Sky Survey was produced at the Space Telescope Science Institute under U.S. Government grant NAG W-2166, from photographic data of the Oschin Schmidt Telescope on Palomar Mountain and the UK Schmidt Telescope.
- **Lunar imagery** from **[Dial-a-Moon](https://svs.gsfc.nasa.gov/4442)**, by **Ernie Wright** at **NASA's Scientific Visualization Studio**, rendered from Lunar Reconnaissance Orbiter data. SVS content is public domain. Each frame shows the Moon's real phase, libration and terminator for that hour — the display is compositing an actual render, not drawing an approximation.
- **The case** is a remix of **"Raspberry Pi Touch Display 2 Case" by RonnyS** ([Printables 1377047](https://www.printables.com/model/1377047-raspberry-pi-touch-display-2-case)), used under CC BY.

## 📄 Licence

**GPL-3.0** — see [LICENSE](LICENSE). Chosen to match [pilomar](https://github.com/Short-bus/pilomar), the Pi miniature-observatory project by Short-bus that this display was inspired by.

**Except `case/`**, which is **CC BY** rather than GPL, because it is a remix of RonnyS's CC-BY model and that licence carries forward. Credit RonnyS and this project if remixed further.
