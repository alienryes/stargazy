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

FIRMWARE_VERSION = "2.7.3"

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
# Conditions run on a cool-to-warm ramp: a clear night reads cold and blue, a
# washed-out one warm. Amber is reserved for the moon and for cautions.
BG       = (10, 12, 28)      # opaque fills (bar troughs) — matches the night sky
WHITE    = (230, 232, 240)   # data text
ICE      = (165, 243, 252)   # #A5F3FC — best conditions
ELECTRIC = (56, 189, 248)    # #38BDF8 — good conditions, bar fills
AMBER    = (245, 158, 11)    # #F59E0B — moon, and fair/caution
ROSE     = (244, 63, 94)     # #F43F5E — poor conditions
STEEL    = (29, 94, 128)     # muted electric — bar trough frame
MOON_DARK = (27, 36, 64)     # unlit lunar disc, just above the sky navy
DIM      = (90, 98, 120)     # divider lines / subtle rules
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
    "sensor.astroweather_backyard_moon_next_rising",
    "sensor.astroweather_backyard_moon_next_setting",
    # The plain sun_next_setting/rising are CIVIL twilight; these are the real
    # astronomical dark bounds the timeline highlights.
    "sensor.astroweather_backyard_sun_next_setting_astronomical",
    "sensor.astroweather_backyard_sun_next_rising_astronomical",
]

# UpTonight publishes its content in ATTRIBUTES, not state: the state is just a
# count. The attribute key matches the section name in each case.
UPTONIGHT = {
    "objects": "sensor.uptonight_backyard_objects_garyimm",
    "bodies":  "sensor.uptonight_backyard_bodies_garyimm",
    "comets":  "sensor.uptonight_backyard_comets_garyimm",
}

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
    """Returns (states, targets). states maps entity -> state string; targets is
    UpTonight's object/body/comet lists, empty if it has not published."""
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

    targets = {}
    for key, eid in UPTONIGHT.items():
        try:
            r = session.get(f"{ha_url}/api/states/{eid}", timeout=10)
            r.raise_for_status()
            j = r.json()
            # Its state topics are not retained, so after an HA restart these
            # sit unavailable until the refresh automation fires. Skip quietly.
            if j.get("state") in (None, "unknown", "unavailable"):
                continue
            attrs = j.get("attributes", {})
            targets[key] = attrs.get(key, [])
            targets.setdefault("meta", attrs)
        except Exception as e:
            log.warning("Failed to fetch %s: %s", eid, e)
    return states, targets


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
        return "EXCELLENT", ICE
    if score >= 50:
        return "GOOD", ELECTRIC
    if score >= 25:
        return "FAIR", AMBER
    if score > 0:
        return "POOR", ROSE
    return "NONE", ROSE


def _bar_colour(value, good, warn):
    if value >= good:
        return ELECTRIC
    if value >= warn:
        return AMBER
    return ROSE


def _draw_moon(draw, cx, cy, r, illumination, waxing=True):
    """Draw moon phase using parametric geometry."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=MOON_DARK, outline=AMBER, width=3)

    if illumination < 1:
        return  # new moon -- dark circle only

    if illumination > 99:
        draw.ellipse([cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3], fill=AMBER)
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

    draw.polygon(pts, fill=AMBER)


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


# Parallax depth, keyed by the star's size. Bigger stars read as nearer, so they
# drift faster; brightness and depth then reinforce each other instead of
# fighting. Three offsets are computed per frame, not per star.
STAR_DEPTH = {1: 0.25, 2: 0.6, 3: 1.3}


def draw_stars(draw, t, params):
    gain = params["gain"]
    drift = {s: (t * params["drift"] * d) % W for s, d in STAR_DEPTH.items()}
    for x0, y, base, phase, speed, size in STARS:
        val = base * (0.55 + 0.45 * math.sin(t * speed + phase)) * gain
        if val <= 0.05:
            continue
        c = tuple(int(ch * val) for ch in STAR_COLOUR)
        x = (x0 + drift[size]) % W
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
            "y": random.randint(-40, int(H * 0.72)),
            "depth": random.uniform(0.75, 1.35)}   # parallax: clouds separate


def initial_clouds(params):
    n = round(params.get("cloud", 0) / 100 * MAX_CLOUDS)
    return [spawn_cloud() for _ in range(n)]


# ── Deep-sky imagery ──────────────────────────────────────────────────────
# Real sky cutouts from the CDS hips2fits service, which resolves the object
# name itself and renders the actual patch of sky. That beats an image-library
# search: coverage is total (NGC and LBN designations work as well as Messier)
# and it cannot return a confidently-wrong picture of something else. DSS2
# colour renders on black, so the tiles composite onto the night sky cleanly.
CACHE_DIR = Path(__file__).parent / "cache" / "dso"
HIPS_URL = "https://alasky.cds.unistra.fr/hips-image-services/hips2fits"


def cutout(obj_id, size_arcmin, px=200):
    """Cached DSS2 colour cutout for an object, or None. NETWORK - background
    thread only; never call this from the render loop."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / (re.sub(r"[^A-Za-z0-9]+", "_", obj_id).strip("_") + ".jpg")
    if path.exists():
        try:
            return Image.open(path).convert("RGB")
        except Exception:
            path.unlink(missing_ok=True)
    # Frame the object rather than the pixel grid: catalogue size in arcmin,
    # with margin, clamped so a tiny galaxy is not a dot and M31 is not a smear.
    fov = min(max(size_arcmin * 1.8, 12.0), 50.0) / 60.0
    try:
        r = requests.get(HIPS_URL, timeout=25, params={
            "hips": "CDS/P/DSS2/color", "object": obj_id, "fov": f"{fov:.4f}",
            "width": px, "height": px, "format": "jpg"})
        r.raise_for_status()
        path.write_bytes(r.content)
        img = Image.open(path).convert("RGB")
        log.info("Cutout fetched for %s (fov %.1f')", obj_id, fov * 60)
        return img
    except Exception as e:
        log.warning("Cutout for %s failed: %s", obj_id, e)
        return None


def _glyph(draw, cx, cy, r, otype):
    """Fallback mark when no cutout is available (offline, or a failed fetch)."""
    t = (otype or "").lower()
    if "globular" in t or "cluster" in t:
        random.seed(hash(otype) & 0xFFFF)
        for _ in range(28):
            a, d = random.uniform(0, 2 * math.pi), random.uniform(0, r * 0.85)
            draw.point((cx + d * math.cos(a), cy + d * math.sin(a)), fill=WHITE)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=STEEL)
    elif "galaxy" in t:
        draw.ellipse([cx - r, cy - r * 0.45, cx + r, cy + r * 0.45], outline=ICE, width=2)
        draw.ellipse([cx - r * 0.28, cy - r * 0.16, cx + r * 0.28, cy + r * 0.16], fill=ICE)
    else:                                            # nebulae and everything else
        draw.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], outline=ELECTRIC)
        draw.ellipse([cx - r * 0.6, cy - r * 0.45, cx + r * 0.6, cy + r * 0.45], outline=STEEL)


def load_cutouts(targets, limit):
    """{object id: image} for the objects the page will show. NETWORK on a cache
    miss, so this runs on the data thread, not the render loop."""
    images = {}
    for o in sorted(targets.get("objects") or [],
                    key=lambda o: (-_f(o.get("foto")), _f(o.get("mag"), 99)))[:limit]:
        oid = str(o.get("id", ""))
        pic = cutout(oid, _f(o.get("size"), 10.0))
        if pic is not None:
            images[oid] = pic
    return images


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
        v_colour = AMBER
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
            draw.text((LP_CX - big_w // 2, 300), big_text, fill=AMBER, font=f_large)
            sub_w = int(draw.textlength(sub_text, font=f_sm))
            draw.text((LP_CX - sub_w // 2, 410), sub_text, fill=WHITE, font=f_sm)
            dt_text = next_dark.strftime("%d %b %Y")
            dt_w = int(draw.textlength(dt_text, font=f_xs))
            draw.text((LP_CX - dt_w // 2, 452), dt_text, fill=AMBER, font=f_xs)
        else:
            msg = "No dark sky"
            msg_w = int(draw.textlength(msg, font=f_med))
            draw.text((LP_CX - msg_w // 2, 380), msg, fill=AMBER, font=f_med)
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
            draw.rectangle([BARX - 2, y + 2, BARX + BARW + 2, y + BARH + 6], fill=STEEL)
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
    draw.text((MCX - pn_w // 2, MCY + MR + 8), phase_name, fill=AMBER, font=f_sm)

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

# ── Page 2: tonight's targets ─────────────────────────────────────────────
P2_DIV_X = 636       # panorama | deep-sky cards
P2_CARDS = 4         # cards that fit the right column
PAN_TOP, PAN_BASE = 214, 566          # top and bottom of the altitude axis
PAN_X0, PAN_X1 = MARGIN, P2_DIV_X - 24
# The axis stops at 70 deg, not 90. Everything plotted here sits near the
# ecliptic, which at 51.4N never climbs past about 62 deg for the planets or
# 67 for the Moon at extreme standstill - so the top fifth of a 0-90 axis was
# dead space that squeezed everything else together. Latitude-specific: raise
# this if the display is ever used much further south.
PAN_ALT_MAX = 70.0


def _tl_x(t, t0, t1, x0, x1):
    """Map a time onto the timeline, clamped to its ends. None if unusable."""
    if t is None or t0 is None or t1 is None or t1 <= t0:
        return None
    f = (t - t0).total_seconds() / (t1 - t0).total_seconds()
    return x0 + max(0.0, min(1.0, f)) * (x1 - x0)


def _draw_timeline(draw, states, y, f_xs):
    """Dusk-to-dawn bar with true astronomical darkness and moon-up marked."""
    x0, x1, h = MARGIN, W - MARGIN, 24
    dusk = _dt(states.get("sensor.astroweather_backyard_sun_next_setting"))
    dawn = _dt(states.get("sensor.astroweather_backyard_sun_next_rising"))
    if dusk is None or dawn is None or dawn <= dusk:
        return
    draw.rectangle([x0, y, x1, y + h], fill=BG, outline=STEEL)

    # Astronomical dark: the hours that actually count, not civil twilight.
    a0 = _tl_x(_dt(states.get("sensor.astroweather_backyard_sun_next_setting_astronomical")),
               dusk, dawn, x0, x1)
    a1 = _tl_x(_dt(states.get("sensor.astroweather_backyard_sun_next_rising_astronomical")),
               dusk, dawn, x0, x1)
    if a0 is not None and a1 is not None and a1 > a0:
        draw.rectangle([a0, y + 1, a1, y + h - 1], fill=ELECTRIC)

    # Moon up washes the sky out. Shown as its own strip ABOVE the bar rather
    # than a translucent overlay - amber over the electric segment just turned
    # the whole thing muddy brown and hid the darkness window.
    m0 = _tl_x(_dt(states.get("sensor.astroweather_backyard_moon_next_rising")),
               dusk, dawn, x0, x1)
    m1 = _tl_x(_dt(states.get("sensor.astroweather_backyard_moon_next_setting")),
               dusk, dawn, x0, x1)
    if m0 is not None and m1 is not None and m1 > m0:
        draw.rectangle([m0, y - 12, m1, y - 5], fill=AMBER)
        draw.text((m0 + 6, y - 34), "moon up", font=f_xs, fill=AMBER)

    # Only mark "now" while it is actually within tonight; clamping it to an end
    # would draw a marker that reads as a real time when it is not.
    now = datetime.now().astimezone()
    if dusk <= now <= dawn:
        now_x = _tl_x(now, dusk, dawn, x0, x1)
        draw.line([(now_x, y - 4), (now_x, y + h + 4)], fill=WHITE, width=2)

    draw.text((x0, y + h + 6), dusk.strftime("Dusk %H:%M"), font=f_xs, fill=DIM)
    tw = draw.textlength(dawn.strftime("Dawn %H:%M"), font=f_xs)
    draw.text((x1 - tw, y + h + 6), dawn.strftime("Dawn %H:%M"), font=f_xs, fill=DIM)


def _draw_panorama(draw, bodies, comets, f_sm, f_xs):
    """Where to look: azimuth across, altitude up. A bearing and a height."""
    draw.line([(PAN_X0, PAN_BASE), (PAN_X1, PAN_BASE)], fill=STEEL, width=2)
    for az, lab in ((0, "N"), (90, "E"), (180, "S"), (270, "W"), (360, "N")):
        x = PAN_X0 + (az / 360.0) * (PAN_X1 - PAN_X0)
        draw.line([(x, PAN_BASE), (x, PAN_BASE + 8)], fill=STEEL)
        draw.text((x - 8, PAN_BASE + 12), lab, font=f_xs, fill=DIM)
    for alt in (20, 40, 60):
        y = PAN_BASE - (alt / PAN_ALT_MAX) * (PAN_BASE - PAN_TOP)
        draw.line([(PAN_X0, y), (PAN_X1, y)], fill=(29, 94, 128, 70))
        draw.text((PAN_X1 + 4, y - 12), f"{alt}", font=f_xs, fill=DIM)

    marks = []
    for b in bodies:
        alt, az = _f(b.get("max altitude"), -99), _f(b.get("azimuth"), -1)
        name = str(b.get("target name", "?"))
        col = AMBER if name.lower() == "moon" else ICE
        marks.append((az, alt, name, col, _f(b.get("visual magnitude"), 5)))
    for c in comets:
        marks.append((_f(c.get("azimuth"), -1), _f(c.get("altitude"), -99),
                      str(c.get("target name", "?")), ROSE,
                      _f(c.get("visual magnitude"), 8)))

    # Planets bunch up along the ecliptic - Saturn, Neptune and the Moon can sit
    # within 30px of each other - so labels are nudged down until clear, with a
    # leader line back to the marker whenever one has moved.
    placed = []
    for az, alt, name, col, mag in sorted(marks, key=lambda m: -m[1]):
        if alt < 0 or az < 0:
            continue                       # below the horizon: nothing to see
        x = PAN_X0 + (az / 360.0) * (PAN_X1 - PAN_X0)
        y = PAN_BASE - (min(alt, PAN_ALT_MAX) / PAN_ALT_MAX) * (PAN_BASE - PAN_TOP)
        r = max(4.0, min(13.0, 9.0 - mag * 0.8))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=col)

        lx = x + r + 8
        lw = max(draw.textlength(name, font=f_sm), 78)
        base = y - 14
        # Try alternately below then above the marker. Purely-downward nudging
        # drove low objects' labels through the horizon axis and onto the
        # compass letters, so candidates outside the plot are rejected.
        ly = None
        for off in (0, 26, -26, 52, -52, 78, -78):
            cand = base + off
            if cand < PAN_TOP - 12 or cand + 44 > PAN_BASE - 2:
                continue
            if not any(lx < b[2] and lx + lw > b[0] and cand < b[3] and cand + 44 > b[1]
                       for b in placed):
                ly = cand
                break
        if ly is None:
            ly = max(PAN_TOP - 12, min(base, PAN_BASE - 46))
        placed.append((lx, ly, lx + lw, ly + 44))
        if abs(ly - base) > 2:
            draw.line([(x + r, y), (lx - 4, ly + 14)], fill=STEEL)
        draw.text((lx, ly), name, font=f_sm, fill=WHITE)
        draw.text((lx, ly + 22), f"{int(round(alt))}°  {int(round(az))}°",
                  font=f_xs, fill=DIM)


def _draw_cards(img, draw, objects, images, f_med, f_sm, f_xs):
    """Deep-sky targets, best first, with a real cutout of each patch of sky."""
    # Starts clear of the column heading, which descends to about y 210.
    x0, y = P2_DIV_X + 24, 220
    tile, gap = 96, 16
    for o in objects[:P2_CARDS]:
        oid = str(o.get("id", "?"))
        pic = images.get(oid)
        if pic is not None:
            pic = pic.resize((tile, tile), Image.LANCZOS)
            mask = Image.new("L", (tile, tile), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, tile - 1, tile - 1], fill=255)
            img.paste(pic, (x0, y), mask)
            draw.ellipse([x0, y, x0 + tile - 1, y + tile - 1], outline=STEEL)
        else:
            _glyph(draw, x0 + tile // 2, y + tile // 2, tile // 2 - 6, o.get("type"))

        tx = x0 + tile + 18
        draw.text((tx, y + 2), oid, font=f_med, fill=WHITE)
        draw.text((tx, y + 40), f"{o.get('type', '')} in {o.get('constellation', '')}",
                  font=f_xs, fill=DIM)
        mag = _f(o.get("mag"), 0)
        draw.text((tx, y + 68), "mag --" if mag <= 0 else f"mag {mag:.1f}",
                  font=f_xs, fill=DIM)
        # foto = fraction of astronomical darkness the object stays observable
        bx, bw = tx + 110, 150
        frac = max(0.0, min(1.0, _f(o.get("foto"))))
        draw.rectangle([bx, y + 72, bx + bw, y + 86], fill=BG, outline=STEEL)
        if frac > 0:
            draw.rectangle([bx + 1, y + 73, bx + 1 + frac * (bw - 2), y + 85],
                           fill=ELECTRIC if frac >= 0.75 else AMBER)
        y += tile + gap


def render_targets(states, targets, images):
    """Page 2 as an RGBA overlay, or None when UpTonight has published nothing."""
    objects = targets.get("objects") or []
    bodies  = targets.get("bodies") or []
    comets  = targets.get("comets") or []
    if not (objects or bodies):
        return None

    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f_title = _font("DejaVuSans-Bold.ttf", 42)
    f_med   = _font("DejaVuSans-Bold.ttf", 32)
    f_sm    = _font("DejaVuSans.ttf", 24)
    f_xs    = _font("DejaVuSans.ttf", 20)

    draw.text((MARGIN, 22), "TONIGHT'S TARGETS", font=f_title, fill=WHITE)
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM)
    _draw_timeline(draw, states, 128, f_xs)

    draw.line([(P2_DIV_X, 190), (P2_DIV_X, 664)], fill=DIM)
    draw.text((MARGIN, 182), "WHERE TO LOOK", font=f_sm, fill=ELECTRIC)
    # Say what the column is actually showing. On a dark night the cap lets 40
    # objects through against four cards, so "(40 up)" alone was misleading.
    shown = min(P2_CARDS, len(objects))
    count = (f"first {shown} of {len(objects)}" if shown < len(objects)
             else f"all {len(objects)}")
    draw.text((P2_DIV_X + 24, 182), f"DEEP SKY  ({count})", font=f_sm, fill=ELECTRIC)
    _draw_panorama(draw, bodies, comets, f_sm, f_xs)

    ranked = sorted(objects, key=lambda o: (-_f(o.get("foto")), _f(o.get("mag"), 99)))
    _draw_cards(img, draw, ranked, images, f_med, f_sm, f_xs)

    # No "+N more": it dangled an object the page never shows, and the column
    # heading already carries the total.
    if comets:
        c = comets[0]
        draw.text((MARGIN, 656),
                  f"Comet {c.get('target name', '?')} - "
                  f"alt {_f(c.get('altitude')):.0f}°, az {_f(c.get('azimuth')):.0f}°",
                  font=f_xs, fill=DIM)
    draw.text((MARGIN, 688), "Sky imagery: DSS2 / CDS Strasbourg", font=f_xs, fill=(60, 66, 86))
    return img


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


def run_daemon(ha_url, token, animated, fps, refresh_min, page_seconds, demo=False):
    """Long-running loop: animate the panel while a thread refreshes HA data."""
    state = {"pages": [], "params": None}

    def load():
        states, targets = fetch_states(ha_url, token)
        pages = [render_foreground(states)]
        # Targets page joins the rotation only when there is something on it -
        # better a single page than a dead one after a restart.
        page2 = render_targets(states, targets, load_cutouts(targets, P2_CARDS))
        if page2 is not None:
            pages.append(page2)
        state["pages"] = pages
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
                page = state["pages"][0]
                if page is not last:
                    frame = compose(page, state["params"], 0.0, [], initial_clouds(state["params"]))
                    fb.seek(0)
                    fb.write(to_fb_bytes(frame))
                    last = page
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
                c["x"] += params["cloud_speed"] * c["depth"] * frame_dt
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
            pages = state["pages"]
            page = pages[int(t / page_seconds) % len(pages)]
            frame = compose(page, params, t, meteors, clouds)
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
    page_seconds = float(disp.get("page_seconds", 20))

    if args.save or args.once:
        log.info("Fetching HA states...")
        states, targets = fetch_states(ha_url, token)
        params = sky_params(states)
        fg = render_foreground(states)
        frame = compose(fg, params, 1.7, [], initial_clouds(params))
        if args.save:
            frame.save(args.save)
            log.info("Saved %s", args.save)
            page2 = render_targets(states, targets, load_cutouts(targets, P2_CARDS))
            if page2 is not None:
                p = Path(args.save)
                out = str(p.with_name(p.stem + "_targets" + p.suffix))
                compose(page2, params, 1.7, [], initial_clouds(params)).save(out)
                log.info("Saved %s", out)
            else:
                log.warning("No UpTonight data - targets page skipped.")
        else:
            with open(FB_DEV, "wb") as fb:
                fb.write(to_fb_bytes(frame))
            log.info("Done. v%s", FIRMWARE_VERSION)
        return

    _install_signal_handlers()
    run_daemon(ha_url, token, animated=(mode != "static"), fps=fps,
               refresh_min=refresh_min, page_seconds=page_seconds, demo=args.demo)


if __name__ == "__main__":
    main()
