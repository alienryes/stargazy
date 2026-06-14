#!/usr/bin/env python3
"""Stargazing conditions display for Pimoroni Inky Impression 4" (640×400, 7-colour)."""

import argparse
import logging
import math
import sys
from datetime import datetime
from pathlib import Path

import requests
import tomllib
from PIL import Image, ImageDraw, ImageFont

FIRMWARE_VERSION = "1.0.0"

CONFIG_PATH = Path(__file__).parent / "config.toml"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Inky Impression palette colour indices
BLACK, WHITE, GREEN, BLUE, RED, YELLOW, ORANGE = 0, 1, 2, 3, 4, 5, 6

# Preview palette for --save mode (RGB values for each index)
PREVIEW_PALETTE = [
    0, 0, 0,          # 0 BLACK
    255, 255, 255,    # 1 WHITE
    0, 200, 0,        # 2 GREEN
    30, 80, 220,      # 3 BLUE
    220, 30, 30,      # 4 RED
    240, 220, 0,      # 5 YELLOW
    230, 120, 0,      # 6 ORANGE
] + [0, 0, 0] * 249

W, H = 640, 400

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
    "moon-new": "New Moon",
    "moon-waxing-crescent": "Waxing Crescent",
    "moon-first-quarter": "First Quarter",
    "moon-waxing-gibbous": "Waxing Gibbous",
    "moon-full": "Full Moon",
    "moon-waning-gibbous": "Waning Gibbous",
    "moon-last-quarter": "Last Quarter",
    "moon-waning-crescent": "Waning Crescent",
}


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
    """(label, colour_index) for a deep-sky forecast score 0–100."""
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
    """Draw moon phase on a palette-mode image using parametric geometry."""
    # Dark face
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BLUE, outline=YELLOW, width=2)

    if illumination < 1:
        return  # New moon — just the dark circle

    if illumination > 99:
        draw.ellipse([cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2], fill=YELLOW)
        return

    # Build the lit polygon: bright-limb semicircle + terminator ellipse
    phase_angle = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * illumination / 100.0)))
    term_scale = math.cos(phase_angle)  # terminator semi-minor / r

    steps = 80
    pts = []
    for i in range(steps + 1):
        t = math.pi / 2.0 - math.pi * i / steps
        pts.append((cx + r * math.cos(t), cy - r * math.sin(t)))
    for i in range(steps + 1):
        t = -math.pi / 2.0 + math.pi * i / steps
        pts.append((cx + r * term_scale * math.cos(t), cy - r * math.sin(t)))

    if not waxing:
        pts = [(2 * cx - px, py) for px, py in pts]

    draw.polygon(pts, fill=YELLOW)


def render(states):
    """Render the 640×400 display image. Returns a PIL Image in P mode."""
    img = Image.new("P", (W, H))
    img.putpalette(PREVIEW_PALETTE)
    draw = ImageDraw.Draw(img)

    f_large = _font("DejaVuSans-Bold.ttf", 52)
    f_med = _font("DejaVuSans-Bold.ttf", 22)
    f_sm = _font("DejaVuSans.ttf", 16)
    f_xs = _font("DejaVuSans.ttf", 13)

    # ── Parse ────────────────────────────────────────────────────────
    s = states  # shorthand

    astro_dur = _f(s.get("sensor.astroweather_backyard_astronomical_night_duration"))
    no_dark = astro_dur < 3600  # < 1 h of astronomical darkness (midsummer at 51°N)

    dsky_today = _i(s.get("sensor.astroweather_backyard_deepsky_forecast_today"))
    dsky_today_desc = s.get("sensor.astroweather_backyard_deepsky_forecast_today_description", "")
    dsky_tmrw = _i(s.get("sensor.astroweather_backyard_deepsky_forecast_tomorrow"))
    dsky_tmrw_desc = s.get("sensor.astroweather_backyard_deepsky_forecast_tomorrow_description", "")

    cloud = _i(s.get("sensor.astroweather_backyard_cloud_cover"))
    seeing = _i(s.get("sensor.astroweather_backyard_seeing_percentage"))
    transp = _i(s.get("sensor.astroweather_backyard_transparency"))
    calm = _i(s.get("sensor.astroweather_backyard_calm_percentage"))

    moon_phase = _f(s.get("sensor.astroweather_backyard_moon_phase"))
    moon_icon = s.get("sensor.astroweather_backyard_moon_icon", "moon-new")
    moon_const = s.get("sensor.astroweather_backyard_moon_constellation", "")

    next_new = _dt(s.get("sensor.astroweather_backyard_moon_next_new_moon"))
    next_full = _dt(s.get("sensor.astroweather_backyard_moon_next_full_moon"))
    next_dark = _dt(s.get("sensor.astroweather_backyard_moon_next_dark_night"))
    sunset = _dt(s.get("sensor.astroweather_backyard_sun_next_setting"))
    sunrise = _dt(s.get("sensor.astroweather_backyard_sun_next_rising"))

    temp = _f(s.get("sensor.astroweather_backyard_2m_temperature"))
    dew = _f(s.get("sensor.astroweather_backyard_2m_dewpoint"))
    humidity = _i(s.get("sensor.astroweather_backyard_2m_relative_humidity"))
    wind_spd = _f(s.get("sensor.astroweather_backyard_10m_wind_speed"))
    wind_dir = s.get("sensor.astroweather_backyard_10m_wind_direction", "")
    lifted = s.get("sensor.astroweather_backyard_lifted_index_plain", "")

    waxing = any(k in moon_icon for k in ("waxing", "new", "first"))

    # ── Background ───────────────────────────────────────────────────
    draw.rectangle([0, 0, W, H], fill=BLACK)

    # ── Header (y 0–38) ──────────────────────────────────────────────
    draw.text((12, 8), "STARGAZING", fill=WHITE, font=f_med)
    now_str = datetime.now().strftime("%a %d %b  %H:%M")
    ts_w = int(draw.textlength(now_str, font=f_sm))
    draw.text((W - ts_w - 10, 11), now_str, fill=WHITE, font=f_sm)
    draw.line([(0, 38), (W, 38)], fill=WHITE, width=1)

    # ── Verdict (y 45–118) ───────────────────────────────────────────
    if no_dark:
        v_text = "NO DARK SKY"
        v_colour = ORANGE
        v_sub = f"Next dark night: {next_dark.strftime('%d %b') if next_dark else 'unknown'}"
    else:
        v_text, v_colour = _verdict(dsky_today)
        v_sub = f"Deep sky: {dsky_today}%  –  {dsky_today_desc}"

    draw.text((12, 45), v_text, fill=v_colour, font=f_large)
    draw.text((12, 105), v_sub, fill=WHITE, font=f_sm)
    draw.line([(0, 126), (W, 126)], fill=WHITE, width=1)

    # ── Condition bars — left side (x 0–350, y 134–282) ─────────────
    LX, LBLW, BARW, BARH, GAP = 12, 120, 178, 13, 35
    BARX = LX + LBLW
    VALX = BARX + BARW + 6

    conditions = [
        ("Cloudless", 100 - cloud, _bar_colour(100 - cloud, 60, 40)),
        ("Seeing",    seeing,      _bar_colour(seeing,       60, 40)),
        ("Transparency", transp,   _bar_colour(transp,       60, 40)),
        ("Calm",      calm,        _bar_colour(calm,         70, 50)),
    ]
    for i, (label, value, colour) in enumerate(conditions):
        y = 136 + i * GAP
        draw.text((LX, y), label, fill=WHITE, font=f_sm)
        draw.rectangle([BARX, y + 3, BARX + BARW, y + 3 + BARH], fill=WHITE)
        filled = max(1, int(BARW * value / 100))
        draw.rectangle([BARX, y + 3, BARX + filled, y + 3 + BARH], fill=colour)
        draw.text((VALX, y), f"{value}%", fill=WHITE, font=f_sm)

    draw.line([(355, 126), (355, 288)], fill=WHITE, width=1)

    # ── Moon — right side (x 360–600, y 134–282) ─────────────────────
    MX = 368
    MCX, MCY, MR = 490, 208, 52

    phase_name = PHASE_NAMES.get(moon_icon, moon_icon.replace("moon-", "").replace("-", " ").title())
    draw.text((MX, 134), "MOON", fill=WHITE, font=f_med)
    draw.text((MX, 158), phase_name, fill=YELLOW, font=f_sm)
    if moon_const:
        draw.text((MX, 176), f"In {moon_const}", fill=WHITE, font=f_xs)

    _draw_moon(draw, MCX, MCY, MR, moon_phase, waxing)

    y_dates = MCY + MR + 6
    if next_new:
        draw.text((MX, y_dates), f"New: {next_new.strftime('%d %b')}", fill=WHITE, font=f_xs)
    if next_full:
        draw.text((MX + 88, y_dates), f"Full: {next_full.strftime('%d %b')}", fill=WHITE, font=f_xs)

    # ── Bottom (y 288–400) ────────────────────────────────────────────
    draw.line([(0, 288), (W, 288)], fill=WHITE, width=1)

    # Tomorrow forecast
    t_colour = _verdict(dsky_tmrw)[1]
    draw.text((12, 296), "Tomorrow:", fill=WHITE, font=f_sm)
    draw.text((97, 296), f"{dsky_tmrw_desc}  ({dsky_tmrw}%)", fill=t_colour, font=f_sm)

    # Atmospheric stability (right side)
    if lifted and lifted not in ("unknown", ""):
        draw.text((360, 296), lifted, fill=WHITE, font=f_xs)

    # Sun times
    sun_parts = []
    if sunset:
        sun_parts.append(f"Sunset {sunset.strftime('%H:%M')}")
    if sunrise:
        sun_parts.append(f"Sunrise {sunrise.strftime('%H:%M')}")
    draw.text((12, 318), "  ·  ".join(sun_parts), fill=WHITE, font=f_xs)

    # Weather
    wx = f"{temp:.1f}°C  ·  Dew {dew:.1f}°  ·  {humidity}% RH  ·  {wind_dir} {wind_spd:.1f} m/s"
    draw.text((12, 335), wx, fill=WHITE, font=f_xs)

    # No-dark-sky note
    if no_dark and next_dark:
        draw.text((12, 354), f"Astronomical night returns: {next_dark.strftime('%d %b %Y')}", fill=ORANGE, font=f_xs)

    # Version stamp
    ver = f"v{FIRMWARE_VERSION}"
    ver_w = int(draw.textlength(ver, font=f_xs))
    draw.text((W - ver_w - 6, H - 16), ver, fill=WHITE, font=f_xs)

    return img


def main():
    parser = argparse.ArgumentParser(description="Inky Impression stargazing display")
    parser.add_argument("--save", metavar="PATH", help="Save PNG preview instead of driving the display")
    args = parser.parse_args()

    config = load_config()
    ha_url = config["ha"]["url"].rstrip("/")
    token = config["ha"]["token"]

    log.info("Fetching HA states...")
    states = fetch_states(ha_url, token)

    if args.save:
        log.info("Rendering preview to %s", args.save)
        img = render(states)
        img.save(args.save)
        log.info("Saved.")
        return

    log.info("Rendering to Inky display...")
    try:
        from inky.inky_uc8159 import Inky
        inky = Inky(resolution=(640, 400))
    except ImportError:
        log.error("inky library not available — use --save <path.png> for development")
        sys.exit(1)

    img = render(states).convert("RGB")
    inky.set_image(img)
    inky.show()
    log.info("Done. v%s", FIRMWARE_VERSION)


if __name__ == "__main__":
    main()
