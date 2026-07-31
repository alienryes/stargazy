#!/usr/bin/env python3
"""Stargazing conditions display for the Raspberry Pi Touch Display 2 (5", 720x1280).

Renders a 1280x720 landscape dashboard over a live, data-reactive animated night
sky (twinkling starfield + drift + meteors) and writes frames to the Linux
framebuffer (/dev/fb0, RGB565). Runs as a long-lived daemon; a background thread
refetches AstroWeather data from the Home Assistant REST API.

  python3 display.py                 # daemon (mode from config, default animated)
  python3 display.py --once          # render a single frame to the panel and exit
  python3 display.py --save out.png  # save a single composited frame (dev/review)
"""

import argparse
import logging
import math
import random
import re
import signal
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import requests
import tomllib
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FIRMWARE_VERSION = "2.4.1"

CONFIG_PATH = Path(__file__).parent / "config.toml"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Framebuffer geometry (Touch Display 2 native portrait). The landscape frame is
# rotated to this before packing to RGB565. Flip ROTATE if the panel is upside down.
FB_DEV = "/dev/fb0"
FB_W, FB_H = 720, 1280
ROTATE = Image.ROTATE_90

# ── Palette ───────────────────────────────────────────────────────────────
BG     = (10, 12, 28)      # opaque fills (bar troughs) — matches the night sky
WHITE  = (230, 232, 240)
GREEN  = (46, 204, 96)
BLUE   = (70, 130, 240)
RED    = (224, 66, 66)
YELLOW = (240, 212, 60)
ORANGE = (238, 140, 44)
DIM    = (90, 98, 120)     # divider lines / subtle rules
STAR_COLOUR = (232, 234, 248)

W, H = 1280, 720

# ── Layout constants (1280x720 landscape) ─────────────────────────────────
MARGIN = 28
HLINE1 = 80                 # header bottom
HLINE2 = 252                # verdict bottom
HLINE3 = 548                # footer top
DIV_X  = 800                # vertical divider: conditions | moon
RIGHT_CX = (DIV_X + W) // 2  # centre of right (moon) panel = 1040

ENTITIES = [
    "sensor.astroweather_backyard_astronomical_night_duration",
    "sensor.astroweather_backyard_deepsky_forecast_today",
    "sensor.astroweather_backyard_deepsky_forecast_today_description",
    "sensor.astroweather_backyard_deepsky_forecast_tomorrow",
    "sensor.astroweather_backyard_deepsky_forecast_tomorrow_description",
    "sensor.astroweather_backyard_cloud_cover",
    "sensor.astroweather_backyard_seeing_percentage",
    "sensor.astroweather_backyard_transparency",
    "sensor.astroweather_backyard_calm_percentage",
    "sensor.astroweather_backyard_moon_phase",
    "sensor.astroweather_backyard_moon_icon",
    "sensor.astroweather_backyard_moon_constellation",
    "sensor.astroweather_backyard_moon_next_new_moon",
    "sensor.astroweather_backyard_moon_next_full_moon",
    "sensor.astroweather_backyard_moon_next_dark_night",
    "sensor.astroweather_backyard_sun_next_setting",
    "sensor.astroweather_backyard_sun_next_rising",
    "sensor.astroweather_backyard_2m_temperature",
    "sensor.astroweather_backyard_2m_dewpoint",
    "sensor.astroweather_backyard_2m_relative_humidity",
    "sensor.astroweather_backyard_10m_wind_speed",
    "sensor.astroweather_backyard_10m_wind_direction",
    "sensor.astroweather_backyard_lifted_index_plain",
]

PHASE_NAMES = {
    "moon-new":             "New Moon",
    "moon-waxing-crescent": "Waxing Crescent",
    "moon-first-quarter":   "First Quarter",
    "moon-waxing-gibbous":  "Waxing Gibbous",
    "moon-full":            "Full Moon",
    "moon-waning-gibbous":  "Waning Gibbous",
    "moon-last-quarter":    "Last Quarter",
    "moon-waning-crescent": "Waning Crescent",
}

# AstroWeather condition strings arrive as joined words ("Partlycloudy",
# "Clearsky"); split before a known second component so they read naturally.
_COMPOUND_RE = re.compile(
    r"(?<=[a-z])(cloudy|clouds|sky|rain|snow|fog|mist|overcast|sunny)", re.IGNORECASE
)

# Fixed, seeded starfield spanning the whole screen. Each star:
# x, y, base brightness, twinkle phase, twinkle speed, size.
random.seed(7)
STARS = [
    (
        random.randint(0, W - 1),
        random.randint(0, H - 1),
        random.uniform(0.35, 1.0),
        random.uniform(0.0, 2 * math.pi),
        random.uniform(0.4, 2.6),
        1 if random.random() > 0.28 else (2 if random.random() > 0.25 else 3),
    )
    for _ in range(200)
]

_RUNNING = True  # cleared by SIGTERM/SIGINT so the daemon exits gracefully


def _phrase(s):
    """'Partlycloudy night' -> 'Partly cloudy night'."""
    return _COMPOUND_RE.sub(r" \1", s) if s else s


def load_config():
    with open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def fetch_states(ha_url, token):
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"
    states = {}
    for eid in ENTITIES:
        try:
            r = session.get(f"{ha_url}/api/states/{eid}", timeout=10)
            r.raise_for_status()
            states[eid] = r.json()["state"]
        except Exception as e:
            log.warning("Failed to fetch %s: %s", eid, e)
            states[eid] = "unknown"
    return states


def _f(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _i(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _dt(s):
    if not s or s == "unknown":
        return None
    try:
        return datetime.fromisoformat(s).astimezone()
    except ValueError:
        return None


def _font(name, size):
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except OSError:
        return ImageFont.load_default()


def _verdict(score):
    """(label, colour) for a deep-sky forecast score 0-100."""
    if score >= 75:
        return "EXCELLENT", GREEN
    if score >= 50:
        return "GOOD", YELLOW
    if score >= 25:
        return "FAIR", ORANGE
    if score > 0:
        return "POOR", RED
    return "NONE", RED


def _bar_colour(value, good, warn):
    if value >= good:
        return GREEN
    if value >= warn:
        return YELLOW
    return RED


def _draw_moon(draw, cx, cy, r, illumination, waxing=True):
    """Draw moon phase using parametric geometry."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BLUE, outline=YELLOW, width=3)

    if illumination < 1:
        return  # new moon -- dark circle only

    if illumination > 99:
        draw.ellipse([cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3], fill=YELLOW)
        return

    phase_angle = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * illumination / 100.0)))
    term_scale  = math.cos(phase_angle)

    steps = 120
    pts   = []
    for i in range(steps + 1):
        t = math.pi / 2.0 - math.pi * i / steps
        pts.append((cx + r * math.cos(t), cy - r * math.sin(t)))
    for i in range(steps + 1):
        t = -math.pi / 2.0 + math.pi * i / steps
        pts.append((cx + r * term_scale * math.cos(t), cy - r * math.sin(t)))

    if not waxing:
        pts = [(2 * cx - px, py) for px, py in pts]

    draw.polygon(pts, fill=YELLOW)


# ── Animated sky ──────────────────────────────────────────────────────────

def make_base(top, bot):
    """Vertical gradient background, built once."""
    top = np.array(top, dtype=np.float32)
    bot = np.array(bot, dtype=np.float32)
    col = (top + (bot - top) * (np.arange(H)[:, None] / H)).astype(np.uint8)  # (H,3)
    arr = np.repeat(col[:, None, :], W, axis=1)  # (H,W,3)
    return Image.fromarray(arr, "RGB")


# Forced vivid clear-sky mood for --demo (visual testing regardless of weather).
DEMO_PARAMS = {"twilight": False, "gain": 1.0, "drift": 6.0, "meteors": True,
               "met_min": 7.0, "met_max": 15.0, "cloud": 30, "cloud_speed": 14.0}


def sky_params(states):
    """Derive the sky animation's mood from the conditions."""
    cloud   = _i(states.get("sensor.astroweather_backyard_cloud_cover"))
    seeing  = _i(states.get("sensor.astroweather_backyard_seeing_percentage"))
    transp  = _i(states.get("sensor.astroweather_backyard_transparency"))
    calm    = _i(states.get("sensor.astroweather_backyard_calm_percentage"))
    wind    = _f(states.get("sensor.astroweather_backyard_10m_wind_speed"))
    no_dark = _f(states.get("sensor.astroweather_backyard_astronomical_night_duration")) < 3600

    clarity = max(0.0, min(1.0, (seeing + transp + calm) / 300.0))
    # Keep the sky clearly alive in all conditions; modulate within a visible range.
    gain = (0.60 + 0.40 * clarity) * (1.0 - 0.35 * cloud / 100.0)
    gain = max(0.45, min(1.0, gain))
    if no_dark:
        gain = 0.40                          # twilight: dimmer, few stars
    # Meteors whenever it's dark; rarer (longer gaps) when cloudy/poor.
    met_min = 8.0 + 0.22 * cloud
    return {
        "twilight": no_dark,
        "gain": gain,
        "drift": 2.5 + wind * 0.7,           # px/sec
        "meteors": not no_dark,
        "met_min": met_min,
        "met_max": met_min + 8.0,
        "cloud": cloud,                      # % -> number of drifting cloud sprites
        "cloud_speed": 6.0 + wind * 1.2,     # px/sec
    }


def draw_stars(draw, t, params):
    gain = params["gain"]
    drift = (t * params["drift"]) % W
    for x0, y, base, phase, speed, size in STARS:
        val = base * (0.55 + 0.45 * math.sin(t * speed + phase)) * gain
        if val <= 0.05:
            continue
        c = tuple(int(ch * val) for ch in STAR_COLOUR)
        x = (x0 + drift) % W
        if size == 1:
            draw.point((x, y), fill=c)
        else:
            r = size - 1
            draw.ellipse([x - r, y - r, x + r, y + r], fill=c)
            if size == 3 and val > 0.7:  # faint glint on the brightest stars
                g = tuple(int(ch * val * 0.5) for ch in STAR_COLOUR)
                draw.line([(x - 4, y), (x + 4, y)], fill=g, width=1)
                draw.line([(x, y - 4), (x, y + 4)], fill=g, width=1)


def spawn_meteor():
    return {
        "x": random.uniform(W * 0.25, W - 10),
        "y": random.uniform(10, H * 0.45),
        "vx": -random.uniform(4.0, 7.5),
        "vy": random.uniform(2.0, 4.0),
        "life": 0,
        "max": random.randint(40, 58),
    }


def draw_meteor(draw, m):
    frac = m["life"] / m["max"]
    fade = math.sin(math.pi * min(1.0, frac))
    mag = math.hypot(m["vx"], m["vy"])
    ux, uy = m["vx"] / mag, m["vy"] / mag
    seg, nseg = 11.0, 14
    for i in range(nseg):
        b = fade * (1.0 - i / nseg)
        c = (int(255 * b), int(255 * b), int(235 * b))
        x1, y1 = m["x"] - ux * seg * i, m["y"] - uy * seg * i
        x2, y2 = m["x"] - ux * seg * (i + 1), m["y"] - uy * seg * (i + 1)
        draw.line([(x1, y1), (x2, y2)], fill=c, width=2)
    hb = int(255 * fade)
    draw.ellipse([m["x"] - 2, m["y"] - 2, m["x"] + 2, m["y"] + 2], fill=(hb, hb, int(235 * fade)))


# Drifting cloud sprites (phase 2). Pre-rendered blurred blobs, count scaled by
# cloud cover; they drift across the sky and dim the stars they pass over.
MAX_CLOUDS = 7
CLOUD_COLOUR = (48, 53, 72)   # muted blue-grey, lighter than the navy sky
CLOUD_SPRITES = None


def make_cloud_sprite():
    """One soft, translucent cloud: overlapping blobs on an alpha mask, blurred."""
    w = random.randint(360, 540)
    h = random.randint(150, 240)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    for _ in range(random.randint(5, 8)):
        cx = random.uniform(w * 0.30, w * 0.70)   # keep blobs off the tile edges
        cy = random.uniform(h * 0.38, h * 0.62)
        rw = random.uniform(w * 0.10, w * 0.22)
        rh = random.uniform(h * 0.14, h * 0.28)
        md.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=random.randint(120, 200))
    mask = mask.filter(ImageFilter.GaussianBlur(w * 0.06))
    # Feather the alpha to zero at the tile border so the sprite never shows a
    # hard rectangular edge where it overlaps the sky.
    env = Image.new("L", (w, h), 0)
    ImageDraw.Draw(env).rectangle([w * 0.14, h * 0.16, w * 0.86, h * 0.84], fill=255)
    env = env.filter(ImageFilter.GaussianBlur(min(w, h) * 0.13))
    mask = ImageChops.multiply(mask, env)
    mask = mask.point(lambda p: int(p * 0.6))   # cap opacity so stars faintly show through
    sprite = Image.new("RGBA", (w, h), CLOUD_COLOUR + (0,))
    sprite.putalpha(mask)
    return sprite


def cloud_sprites():
    global CLOUD_SPRITES
    if CLOUD_SPRITES is None:
        CLOUD_SPRITES = [make_cloud_sprite() for _ in range(5)]
    return CLOUD_SPRITES


def spawn_cloud():
    sp = random.choice(cloud_sprites())
    if random.random() < 0.5:
        sp = sp.transpose(Image.FLIP_LEFT_RIGHT)
    return {"sprite": sp,
            "x": random.uniform(-sp.width, W),
            "y": random.randint(-40, int(H * 0.72))}


def initial_clouds(params):
    n = round(params.get("cloud", 0) / 100 * MAX_CLOUDS)
    return [spawn_cloud() for _ in range(n)]


def render_foreground(states):
    """Render the dashboard as an RGBA overlay: opaque content, transparent sky."""
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    f_large = _font("DejaVuSans-Bold.ttf", 96)
    f_med   = _font("DejaVuSans-Bold.ttf", 42)
    f_sm    = _font("DejaVuSans.ttf", 30)
    f_xs    = _font("DejaVuSans.ttf", 24)

    s = states

    astro_dur = _f(s.get("sensor.astroweather_backyard_astronomical_night_duration"))
    no_dark   = astro_dur < 3600

    dsky_today      = _i(s.get("sensor.astroweather_backyard_deepsky_forecast_today"))
    dsky_today_desc = _phrase(s.get("sensor.astroweather_backyard_deepsky_forecast_today_description", ""))
    dsky_tmrw       = _i(s.get("sensor.astroweather_backyard_deepsky_forecast_tomorrow"))
    dsky_tmrw_desc  = _phrase(s.get("sensor.astroweather_backyard_deepsky_forecast_tomorrow_description", ""))

    cloud  = _i(s.get("sensor.astroweather_backyard_cloud_cover"))
    seeing = _i(s.get("sensor.astroweather_backyard_seeing_percentage"))
    transp = _i(s.get("sensor.astroweather_backyard_transparency"))
    calm   = _i(s.get("sensor.astroweather_backyard_calm_percentage"))

    moon_phase = _f(s.get("sensor.astroweather_backyard_moon_phase"))
    moon_icon  = s.get("sensor.astroweather_backyard_moon_icon", "moon-new")
    moon_const = s.get("sensor.astroweather_backyard_moon_constellation", "")

    next_new  = _dt(s.get("sensor.astroweather_backyard_moon_next_new_moon"))
    next_full = _dt(s.get("sensor.astroweather_backyard_moon_next_full_moon"))
    next_dark = _dt(s.get("sensor.astroweather_backyard_moon_next_dark_night"))
    sunset    = _dt(s.get("sensor.astroweather_backyard_sun_next_setting"))
    sunrise   = _dt(s.get("sensor.astroweather_backyard_sun_next_rising"))

    temp     = _f(s.get("sensor.astroweather_backyard_2m_temperature"))
    dew      = _f(s.get("sensor.astroweather_backyard_2m_dewpoint"))
    humidity = _i(s.get("sensor.astroweather_backyard_2m_relative_humidity"))
    wind_spd = _f(s.get("sensor.astroweather_backyard_10m_wind_speed"))
    wind_dir = s.get("sensor.astroweather_backyard_10m_wind_direction", "")
    lifted   = s.get("sensor.astroweather_backyard_lifted_index_plain", "")

    waxing = any(k in moon_icon for k in ("waxing", "new", "first"))

    # ── Header ────────────────────────────────────────────────────────
    draw.text((MARGIN, 18), "STARGAZING", fill=WHITE, font=f_med)
    # The clock is NOT drawn here: this overlay is cached between data refreshes,
    # so a timestamp baked in would sit frozen for refresh_min. See draw_clock().
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM, width=2)

    # ── Verdict ───────────────────────────────────────────────────────
    if no_dark:
        v_text   = "NO DARK SKY"
        v_colour = ORANGE
        v_sub    = f"Next dark night: {next_dark.strftime('%d %b') if next_dark else 'unknown'}"
    else:
        v_text, v_colour = _verdict(dsky_today)
        v_sub = f"Deep sky: {dsky_today}%  -  {dsky_today_desc}"

    draw.text((MARGIN, 92), v_text, fill=v_colour, font=f_large)
    draw.text((MARGIN, 202), v_sub, fill=WHITE, font=f_sm)
    draw.line([(0, HLINE2), (W, HLINE2)], fill=DIM, width=2)

    # ── Left panel ────────────────────────────────────────────────────
    LP_CX = DIV_X // 2

    if no_dark:
        if next_dark:
            days_until = max(0, (next_dark.date() - datetime.now().date()).days)
            if days_until == 0:
                big_text = "Tonight"
                sub_text = "dark sky returns"
            else:
                big_text = str(days_until)
                sub_text = "days until dark sky"
            big_w = int(draw.textlength(big_text, font=f_large))
            draw.text((LP_CX - big_w // 2, 300), big_text, fill=ORANGE, font=f_large)
            sub_w = int(draw.textlength(sub_text, font=f_sm))
            draw.text((LP_CX - sub_w // 2, 410), sub_text, fill=WHITE, font=f_sm)
            dt_text = next_dark.strftime("%d %b %Y")
            dt_w = int(draw.textlength(dt_text, font=f_xs))
            draw.text((LP_CX - dt_w // 2, 452), dt_text, fill=ORANGE, font=f_xs)
        else:
            msg = "No dark sky"
            msg_w = int(draw.textlength(msg, font=f_med))
            draw.text((LP_CX - msg_w // 2, 380), msg, fill=ORANGE, font=f_med)
    else:
        LX, LBLW, BARW, BARH, GAP = MARGIN, 200, 400, 30, 66
        BARX = LX + LBLW
        VALX = BARX + BARW + 16

        conditions = [
            ("Cloudless",    100 - cloud, _bar_colour(100 - cloud, 60, 40)),
            ("Seeing",       seeing,      _bar_colour(seeing,       60, 40)),
            ("Transparency", transp,      _bar_colour(transp,       60, 40)),
            ("Calm",         calm,        _bar_colour(calm,         70, 50)),
        ]
        for i, (label, value, colour) in enumerate(conditions):
            y = 272 + i * GAP
            draw.text((LX, y), label, fill=WHITE, font=f_sm)
            # Coloured border > opaque trough > coloured fill (opaque over the sky).
            draw.rectangle([BARX - 2, y + 2, BARX + BARW + 2, y + BARH + 6], fill=BLUE)
            draw.rectangle([BARX,     y + 4, BARX + BARW,     y + BARH + 4], fill=BG)
            filled = max(2, int(BARW * value / 100))
            draw.rectangle([BARX, y + 4, BARX + filled, y + BARH + 4], fill=colour)
            draw.text((VALX, y), f"{value}%", fill=WHITE, font=f_sm)

    draw.line([(DIV_X, HLINE2), (DIV_X, HLINE3)], fill=DIM, width=2)

    # ── Moon ──────────────────────────────────────────────────────────
    MCX = RIGHT_CX
    MR  = 100
    MCY = 364
    _draw_moon(draw, MCX, MCY, MR, moon_phase, waxing)

    phase_name = PHASE_NAMES.get(
        moon_icon, moon_icon.replace("moon-", "").replace("-", " ").title()
    )
    pn_w = int(draw.textlength(phase_name, font=f_sm))
    draw.text((MCX - pn_w // 2, MCY + MR + 8), phase_name, fill=YELLOW, font=f_sm)

    if moon_const:
        mc_text = f"in {moon_const}"
        mc_w    = int(draw.textlength(mc_text, font=f_xs))
        draw.text((MCX - mc_w // 2, MCY + MR + 44), mc_text, fill=WHITE, font=f_xs)

    # ── Footer ────────────────────────────────────────────────────────
    draw.line([(0, HLINE3), (W, HLINE3)], fill=DIM, width=2)

    # Row 1 -- tomorrow's forecast (left) + next new/full moon dates (right,
    # grouped under the moon card with the rest of the astronomical data).
    t_colour = _verdict(dsky_tmrw)[1]
    draw.text((MARGIN, 560), "Tomorrow:", fill=WHITE, font=f_sm)
    tm_w = int(draw.textlength("Tomorrow: ", font=f_sm))
    draw.text((MARGIN + tm_w, 560), f"{dsky_tmrw_desc}  ({dsky_tmrw}%)", fill=t_colour, font=f_sm)

    moon_date_parts = []
    if next_new:
        moon_date_parts.append(f"New {next_new.strftime('%d %b')}")
    if next_full:
        moon_date_parts.append(f"Full {next_full.strftime('%d %b')}")
    if moon_date_parts:
        md_text = "  -  ".join(moon_date_parts)
        md_w    = int(draw.textlength(md_text, font=f_sm))
        draw.text((W - md_w - MARGIN, 560), md_text, fill=WHITE, font=f_sm)

    # Row 2 -- lifted index (left, with the meteorology) + dusk/dawn (right).
    if lifted and lifted not in ("unknown", ""):
        draw.text((MARGIN, 606), f"LI: {lifted}", fill=WHITE, font=f_sm)

    # AstroWeather's sun rise/set entities are civil twilight bounds (sun 6deg
    # below horizon), not the geometric sun crossing -- so label them dusk/dawn.
    sun_parts = []
    if sunset:
        sun_parts.append(f"Dusk {sunset.strftime('%H:%M')}")
    if sunrise:
        sun_parts.append(f"Dawn {sunrise.strftime('%H:%M')}")
    if sun_parts:
        sun_text = "  -  ".join(sun_parts)
        sun_w    = int(draw.textlength(sun_text, font=f_sm))
        draw.text((W - sun_w - MARGIN, 606), sun_text, fill=WHITE, font=f_sm)

    # Row 3 -- weather
    wx = f"Temp {temp:.1f}°C  -  Dew {dew:.1f}°C  -  RH {humidity}%  -  Wind {wind_dir} {wind_spd:.1f} m/s"
    draw.text((MARGIN, 652), wx, fill=WHITE, font=f_sm)

    ver   = f"v{FIRMWARE_VERSION}"
    ver_w = int(draw.textlength(ver, font=f_xs))
    draw.text((W - ver_w - MARGIN, H - 30), ver, fill=DIM, font=f_xs)

    return img


# ── Framebuffer ───────────────────────────────────────────────────────────

def to_fb_bytes(img):
    rot = img.transpose(ROTATE)
    if rot.size != (FB_W, FB_H):
        rot = rot.resize((FB_W, FB_H))
    arr = np.asarray(rot, dtype=np.uint16)
    packed = ((arr[:, :, 0] >> 3) << 11) | ((arr[:, :, 1] >> 2) << 5) | (arr[:, :, 2] >> 3)
    return packed.astype("<u2").tobytes()


NIGHT_BASE = None
TWILIGHT_BASE = None


def _bases():
    global NIGHT_BASE, TWILIGHT_BASE
    if NIGHT_BASE is None:
        NIGHT_BASE = make_base((6, 8, 20), (15, 17, 42))
        TWILIGHT_BASE = make_base((22, 32, 62), (44, 60, 100))
    return NIGHT_BASE, TWILIGHT_BASE


def draw_clock(draw):
    """Stamp the header date and time onto a composed frame.

    Drawn per frame rather than into the cached dashboard overlay, so the minute
    advances live and the date rolls over at midnight. It is one short text draw
    over transparent sky, which the 20 fps loop does not notice.
    """
    f_sm    = _font("DejaVuSans.ttf", 30)
    now_str = datetime.now().strftime("%a %d %b  %H:%M")
    ts_w    = int(draw.textlength(now_str, font=f_sm))
    draw.text((W - ts_w - MARGIN, 28), now_str, fill=WHITE, font=f_sm)


def compose(fg, params, t, meteors, clouds):
    """One composited frame: sky + drifting clouds + meteors + dashboard on top."""
    night, twi = _bases()
    frame = (twi if params["twilight"] else night).copy()
    d = ImageDraw.Draw(frame)
    draw_stars(d, t, params)
    for c in clouds:
        frame.paste(c["sprite"], (int(c["x"]), c["y"]), c["sprite"])
    for m in meteors:
        draw_meteor(d, m)
    frame.paste(fg, (0, 0), fg)
    draw_clock(d)
    return frame


# ── Run modes ─────────────────────────────────────────────────────────────

def _install_signal_handlers():
    def stop(_signum, _frame):
        global _RUNNING
        _RUNNING = False
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)


def run_daemon(ha_url, token, animated, fps, refresh_min, demo=False):
    """Long-running loop: animate the panel while a thread refreshes HA data."""
    state = {"fg": None, "params": None}

    def load():
        states = fetch_states(ha_url, token)
        state["fg"] = render_foreground(states)
        state["params"] = DEMO_PARAMS if demo else sky_params(states)

    log.info("Fetching HA states...")
    load()

    def refresher():
        while _RUNNING:
            for _ in range(int(refresh_min * 60)):
                if not _RUNNING:
                    return
                time.sleep(1)
            if _RUNNING:
                try:
                    load()
                    log.info("Data refreshed.")
                except Exception as e:  # keep animating on a transient fetch error
                    log.warning("Refresh failed: %s", e)

    threading.Thread(target=refresher, daemon=True).start()

    fb = open(FB_DEV, "wb")
    try:
        if not animated:
            log.info("Static mode: redraw on data change.")
            last = None
            while _RUNNING:
                if state["fg"] is not last:
                    frame = compose(state["fg"], state["params"], 0.0, [], initial_clouds(state["params"]))
                    fb.seek(0)
                    fb.write(to_fb_bytes(frame))
                    last = state["fg"]
                time.sleep(1)
            return

        log.info("Animated mode at %.0f fps.", fps)
        frame_dt = 1.0 / fps
        t0 = time.time()
        meteors = []
        clouds = initial_clouds(state["params"])
        next_meteor = t0 + random.uniform(1.0, 3.0)
        while _RUNNING:
            now = time.time()
            t = now - t0
            params = state["params"]
            # Clouds: match the count to cover, drift across, recycle off the right edge.
            tgt = round(params["cloud"] / 100 * MAX_CLOUDS)
            while len(clouds) > tgt:
                clouds.pop()
            while len(clouds) < tgt:
                clouds.append(spawn_cloud())
            for c in clouds:
                c["x"] += params["cloud_speed"] * frame_dt
                if c["x"] > W:
                    c["x"] = -c["sprite"].width
                    c["y"] = random.randint(-40, int(H * 0.72))
            if params["meteors"] and now >= next_meteor:
                meteors.append(spawn_meteor())
                next_meteor = now + random.uniform(params["met_min"], params["met_max"])
            for m in meteors[:]:
                m["x"] += m["vx"]
                m["y"] += m["vy"]
                m["life"] += 1
                if m["life"] >= m["max"] or m["y"] > H + 20 or m["x"] < -20:
                    meteors.remove(m)
            frame = compose(state["fg"], params, t, meteors, clouds)
            fb.seek(0)
            fb.write(to_fb_bytes(frame))
            dt = time.time() - now
            if dt < frame_dt:
                time.sleep(frame_dt - dt)
    finally:
        fb.close()
    log.info("Stopped. v%s", FIRMWARE_VERSION)


def main():
    parser = argparse.ArgumentParser(description="Touch Display 2 stargazing display")
    parser.add_argument("--save", metavar="PATH", help="Save a single composited frame and exit")
    parser.add_argument("--once", action="store_true", help="Render one frame to the panel and exit")
    parser.add_argument("--demo", action="store_true", help="Force vivid clear-sky animation (ignore conditions)")
    args = parser.parse_args()

    config = load_config()
    ha_url = config["ha"]["url"].rstrip("/")
    token  = config["ha"]["token"]
    disp   = config.get("display", {})
    mode   = disp.get("mode", "animated")
    fps    = float(disp.get("fps", 20))
    refresh_min = float(disp.get("data_refresh_min", 15))

    if args.save or args.once:
        log.info("Fetching HA states...")
        states = fetch_states(ha_url, token)
        params = sky_params(states)
        fg = render_foreground(states)
        frame = compose(fg, params, 1.7, [], initial_clouds(params))
        if args.save:
            frame.save(args.save)
            log.info("Saved %s", args.save)
        else:
            with open(FB_DEV, "wb") as fb:
                fb.write(to_fb_bytes(frame))
            log.info("Done. v%s", FIRMWARE_VERSION)
        return

    _install_signal_handlers()
    run_daemon(ha_url, token, animated=(mode != "static"), fps=fps,
               refresh_min=refresh_min, demo=args.demo)


if __name__ == "__main__":
    main()
