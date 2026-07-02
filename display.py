#!/usr/bin/env python3
"""Stargazing conditions display for Pimoroni Inky Impression 4" (640×400, 7-colour)."""

import argparse
import logging
import math
import random as _rng
import sys
from datetime import datetime
from pathlib import Path

import requests
import tomllib
from PIL import Image, ImageDraw, ImageFont

FIRMWARE_VERSION = "1.2.2"

CONFIG_PATH = Path(__file__).parent / "config.toml"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Inky Impression palette colour indices
BLACK, WHITE, GREEN, BLUE, RED, YELLOW, ORANGE = 0, 1, 2, 3, 4, 5, 6

# Preview palette for --save mode (RGB values for each index)
PREVIEW_PALETTE = [
    0,   0,   0,    # 0 BLACK
    255, 255, 255,  # 1 WHITE
    0,   200, 0,    # 2 GREEN
    30,  80,  220,  # 3 BLUE
    220, 30,  30,   # 4 RED
    240, 220, 0,    # 5 YELLOW
    230, 120, 0,    # 6 ORANGE
] + [0, 0, 0] * 249

W, H = 640, 400

# Layout constants
DIV_X    = 375                        # vertical divider: conditions | moon
HLINE1   = 40                         # header bottom
HLINE2   = 128                        # verdict bottom
HLINE3   = 290                        # footer top
RIGHT_CX = (DIV_X + W) // 2          # horizontal centre of right (moon) panel = 507

# Right-aligned edge text nudged 1.5mm (~11px) left; version also 1mm (~7px) up.
# Active area is 86x54mm over 640x400 -> ~7.44 px/mm.
EDGE_DX  = 11
VER_DY   = 7

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

# Seeded star positions in the header gap between "STARGAZING" and the timestamp.
# x 235–490 avoids both text blocks; y 5–32 stays within the 40px header.
_rng.seed(42)
_STARS = [
    (int(_rng.uniform(235, 490)), int(_rng.uniform(5, 32)), 2 if _rng.random() > 0.6 else 1)
    for _ in range(14)
]


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
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BLUE, outline=YELLOW, width=2)

    if illumination < 1:
        return  # new moon — dark circle only

    if illumination > 99:
        draw.ellipse([cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2], fill=YELLOW)
        return

    phase_angle = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * illumination / 100.0)))
    term_scale  = math.cos(phase_angle)

    steps = 80
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


def render(states):
    """Render the 640×400 display image. Returns a PIL Image in P mode."""
    img  = Image.new("P", (W, H))
    img.putpalette(PREVIEW_PALETTE)
    draw = ImageDraw.Draw(img)

    f_large = _font("DejaVuSans-Bold.ttf", 52)
    f_med   = _font("DejaVuSans-Bold.ttf", 22)
    f_sm    = _font("DejaVuSans.ttf", 16)
    f_xs    = _font("DejaVuSans.ttf", 13)

    # ── Parse ─────────────────────────────────────────────────────────
    s = states

    astro_dur = _f(s.get("sensor.astroweather_backyard_astronomical_night_duration"))
    no_dark   = astro_dur < 3600

    dsky_today      = _i(s.get("sensor.astroweather_backyard_deepsky_forecast_today"))
    dsky_today_desc = s.get("sensor.astroweather_backyard_deepsky_forecast_today_description", "")
    dsky_tmrw       = _i(s.get("sensor.astroweather_backyard_deepsky_forecast_tomorrow"))
    dsky_tmrw_desc  = s.get("sensor.astroweather_backyard_deepsky_forecast_tomorrow_description", "")

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

    # ── Background ────────────────────────────────────────────────────
    draw.rectangle([0, 0, W, H], fill=BLACK)

    # ── Stars (precomputed, header zone) ──────────────────────────────
    for sx, sy, sr in _STARS:
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=WHITE)

    # ── Header (y 0–40) ───────────────────────────────────────────────
    draw.text((12, 10), "STARGAZING", fill=WHITE, font=f_med)
    now_str = datetime.now().strftime("%a %d %b  %H:%M")
    ts_w    = int(draw.textlength(now_str, font=f_sm))
    draw.text((W - ts_w - 10 - EDGE_DX, 13), now_str, fill=WHITE, font=f_sm)
    draw.line([(0, HLINE1), (W, HLINE1)], fill=WHITE, width=1)

    # ── Verdict (y 44–126) ────────────────────────────────────────────
    if no_dark:
        v_text   = "NO DARK SKY"
        v_colour = ORANGE
        v_sub    = f"Next dark night: {next_dark.strftime('%d %b') if next_dark else 'unknown'}"
    else:
        v_text, v_colour = _verdict(dsky_today)
        v_sub = f"Deep sky: {dsky_today}%  –  {dsky_today_desc}"

    draw.text((12, 46), v_text, fill=v_colour, font=f_large)
    draw.text((12, 107), v_sub, fill=WHITE, font=f_sm)
    draw.line([(0, HLINE2), (W, HLINE2)], fill=WHITE, width=1)

    # ── Left panel (x 0–375, y 132–288) ──────────────────────────────
    LP_CX = DIV_X // 2  # 187 — horizontal centre of left panel

    if no_dark:
        # Condition bars are irrelevant without astronomical darkness.
        # Show a countdown to next dark sky instead.
        if next_dark:
            days_until = max(0, (next_dark.date() - datetime.now().date()).days)
            if days_until == 0:
                big_text = "Tonight"
                sub_text = "dark sky returns"
            else:
                big_text = str(days_until)
                sub_text = "days until dark sky"
            big_w = int(draw.textlength(big_text, font=f_large))
            draw.text((LP_CX - big_w // 2, 148), big_text, fill=ORANGE, font=f_large)
            sub_w = int(draw.textlength(sub_text, font=f_sm))
            draw.text((LP_CX - sub_w // 2, 210), sub_text, fill=WHITE, font=f_sm)
            dt_text = next_dark.strftime("%d %b %Y")
            dt_w = int(draw.textlength(dt_text, font=f_xs))
            draw.text((LP_CX - dt_w // 2, 230), dt_text, fill=ORANGE, font=f_xs)
        else:
            msg = "No dark sky"
            msg_w = int(draw.textlength(msg, font=f_med))
            draw.text((LP_CX - msg_w // 2, 195), msg, fill=ORANGE, font=f_med)
    else:
        LX, LBLW, BARW, BARH, GAP = 12, 105, 210, 14, 37
        BARX = LX + LBLW
        VALX = BARX + BARW + 8

        conditions = [
            ("Cloudless",    100 - cloud, _bar_colour(100 - cloud, 60, 40)),
            ("Seeing",       seeing,      _bar_colour(seeing,       60, 40)),
            ("Transparency", transp,      _bar_colour(transp,       60, 40)),
            ("Calm",         calm,        _bar_colour(calm,         70, 50)),
        ]
        for i, (label, value, colour) in enumerate(conditions):
            y = 138 + i * GAP
            draw.text((LX, y), label, fill=WHITE, font=f_sm)
            # Coloured border > black trough > coloured fill — correct empty/full contrast.
            draw.rectangle([BARX - 1, y + 2,  BARX + BARW + 1, y + BARH + 4], fill=BLUE)
            draw.rectangle([BARX,     y + 3,  BARX + BARW,     y + BARH + 3], fill=BLACK)
            filled = max(1, int(BARW * value / 100))
            draw.rectangle([BARX, y + 3, BARX + filled, y + BARH + 3], fill=colour)
            draw.text((VALX, y), f"{value}%", fill=WHITE, font=f_sm)

    # Vertical divider
    draw.line([(DIV_X, HLINE2), (DIV_X, HLINE3)], fill=WHITE, width=1)

    # ── Moon — right panel (x 380–640, y 132–288) ─────────────────────
    # All text below the circle avoids the original overlap with phase labels.
    MCX = RIGHT_CX  # 507
    MR  = 58
    MCY = 194       # circle: top=136, bottom=252

    _draw_moon(draw, MCX, MCY, MR, moon_phase, waxing)

    # Phase name centred below circle
    phase_name = PHASE_NAMES.get(
        moon_icon, moon_icon.replace("moon-", "").replace("-", " ").title()
    )
    pn_w = int(draw.textlength(phase_name, font=f_sm))
    draw.text((MCX - pn_w // 2, MCY + MR + 4), phase_name, fill=YELLOW, font=f_sm)

    # Constellation centred below phase name
    if moon_const:
        mc_text = f"in {moon_const}"
        mc_w    = int(draw.textlength(mc_text, font=f_xs))
        draw.text((MCX - mc_w // 2, MCY + MR + 22), mc_text, fill=WHITE, font=f_xs)

    # ── Footer (y 292–400) ────────────────────────────────────────────
    draw.line([(0, HLINE3), (W, HLINE3)], fill=WHITE, width=1)

    # Row 1 — tomorrow forecast (left) + lifted index (right)
    t_colour = _verdict(dsky_tmrw)[1]
    draw.text((12, 297), "Tomorrow:", fill=WHITE, font=f_sm)
    draw.text((100, 297), f"{dsky_tmrw_desc}  ({dsky_tmrw}%)", fill=t_colour, font=f_sm)
    if lifted and lifted not in ("unknown", ""):
        li_w = int(draw.textlength(lifted, font=f_xs))
        draw.text((W - li_w - 8 - EDGE_DX, 301), lifted, fill=WHITE, font=f_xs)

    # Row 2 — sun times (left) + next new/full moon dates (right)
    sun_parts = []
    if sunset:
        sun_parts.append(f"Sunset {sunset.strftime('%H:%M')}")
    if sunrise:
        sun_parts.append(f"Sunrise {sunrise.strftime('%H:%M')}")
    draw.text((12, 319), "  ·  ".join(sun_parts), fill=WHITE, font=f_sm)

    moon_date_parts = []
    if next_new:
        moon_date_parts.append(f"New {next_new.strftime('%d %b')}")
    if next_full:
        moon_date_parts.append(f"Full {next_full.strftime('%d %b')}")
    if moon_date_parts:
        md_text = "  ·  ".join(moon_date_parts)
        md_w    = int(draw.textlength(md_text, font=f_xs))
        draw.text((W - md_w - 8 - EDGE_DX, 323), md_text, fill=WHITE, font=f_xs)

    # Row 3 — weather
    wx = f"{temp:.1f}°C  ·  Dew {dew:.1f}°  ·  {humidity}% RH  ·  {wind_dir} {wind_spd:.1f} m/s"
    draw.text((12, 342), wx, fill=WHITE, font=f_sm)

    # Version stamp
    ver   = f"v{FIRMWARE_VERSION}"
    ver_w = int(draw.textlength(ver, font=f_xs))
    draw.text((W - ver_w - 6 - EDGE_DX, H - 15 - VER_DY), ver, fill=WHITE, font=f_xs)

    return img


def main():
    parser = argparse.ArgumentParser(description="Inky Impression stargazing display")
    parser.add_argument("--save", metavar="PATH", help="Save PNG preview instead of driving the display")
    args = parser.parse_args()

    config = load_config()
    ha_url = config["ha"]["url"].rstrip("/")
    token  = config["ha"]["token"]

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
        log.error("inky library not available -- use --save <path.png> for development")
        sys.exit(1)

    img = render(states).convert("RGB")
    inky.set_image(img)
    inky.show()
    log.info("Done. v%s", FIRMWARE_VERSION)


if __name__ == "__main__":
    main()
