#!/usr/bin/env python3
"""Stargazing conditions display for the Raspberry Pi Touch Display 2 (5", 720x1280).

Renders a 1280x720 landscape RGB dashboard and writes it to the Linux framebuffer
(/dev/fb0, RGB565) rotated 90 deg to the panel's native portrait. Data comes from
the AstroWeather integration via the Home Assistant REST API.
"""

import argparse
import logging
import math
import random as _rng
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
import tomllib
from PIL import Image, ImageDraw, ImageFont

FIRMWARE_VERSION = "2.1.0"

CONFIG_PATH = Path(__file__).parent / "config.toml"
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Framebuffer geometry (Touch Display 2 native portrait). Landscape render is
# rotated to this before packing to RGB565. Flip ROTATE if the panel is upside down.
FB_DEV = "/dev/fb0"
FB_W, FB_H = 720, 1280
ROTATE = Image.ROTATE_90

# ── Full-RGB palette (dark night-sky theme) ───────────────────────────────
BG     = (10, 12, 28)      # near-black navy background
WHITE  = (230, 232, 240)
GREEN  = (46, 204, 96)
BLUE   = (70, 130, 240)
RED    = (224, 66, 66)
YELLOW = (240, 212, 60)
ORANGE = (238, 140, 44)
DIM    = (90, 98, 120)     # divider lines / subtle rules

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

# Seeded star positions in the header gap between "STARGAZING" and the timestamp.
_rng.seed(42)
_STARS = [
    (int(_rng.uniform(430, 880)), int(_rng.uniform(10, 66)), 2 if _rng.random() > 0.55 else 1)
    for _ in range(20)
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


# AstroWeather condition strings arrive as joined words ("Partlycloudy",
# "Clearsky"); split before a known second component so they read naturally.
_COMPOUND_RE = re.compile(
    r"(?<=[a-z])(cloudy|clouds|sky|rain|snow|fog|mist|overcast|sunny)", re.IGNORECASE
)


def _phrase(s):
    """'Partlycloudy night' -> 'Partly cloudy night'."""
    return _COMPOUND_RE.sub(r" \1", s) if s else s


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


def render(states):
    """Render the 1280x720 landscape display image. Returns a PIL RGB Image."""
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    f_large = _font("DejaVuSans-Bold.ttf", 96)
    f_med   = _font("DejaVuSans-Bold.ttf", 42)
    f_sm    = _font("DejaVuSans.ttf", 30)
    f_xs    = _font("DejaVuSans.ttf", 24)

    # ── Parse ─────────────────────────────────────────────────────────
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

    # ── Stars (precomputed, header zone) ──────────────────────────────
    for sx, sy, sr in _STARS:
        draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=WHITE)

    # ── Header (y 0-80) ───────────────────────────────────────────────
    draw.text((MARGIN, 18), "STARGAZING", fill=WHITE, font=f_med)
    now_str = datetime.now().strftime("%a %d %b  %H:%M")
    ts_w    = int(draw.textlength(now_str, font=f_sm))
    draw.text((W - ts_w - MARGIN, 28), now_str, fill=WHITE, font=f_sm)
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM, width=2)

    # ── Verdict (y 80-252) ────────────────────────────────────────────
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

    # ── Left panel (x 0-800, y 252-548) ──────────────────────────────
    LP_CX = DIV_X // 2  # 400 -- horizontal centre of left panel

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
            # Coloured border > background trough > coloured fill.
            draw.rectangle([BARX - 2, y + 2, BARX + BARW + 2, y + BARH + 6], fill=BLUE)
            draw.rectangle([BARX,     y + 4, BARX + BARW,     y + BARH + 4], fill=BG)
            filled = max(2, int(BARW * value / 100))
            draw.rectangle([BARX, y + 4, BARX + filled, y + BARH + 4], fill=colour)
            draw.text((VALX, y), f"{value}%", fill=WHITE, font=f_sm)

    # Vertical divider
    draw.line([(DIV_X, HLINE2), (DIV_X, HLINE3)], fill=DIM, width=2)

    # ── Moon -- right panel (x 800-1280, y 252-548) ──────────────────
    MCX = RIGHT_CX  # 1040
    MR  = 100
    MCY = 364       # circle: top=264, bottom=464; leaves room for the labels below

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

    # ── Footer (y 548-720) ────────────────────────────────────────────
    draw.line([(0, HLINE3), (W, HLINE3)], fill=DIM, width=2)

    # Row 1 -- tomorrow forecast (left) + lifted index (right)
    t_colour = _verdict(dsky_tmrw)[1]
    draw.text((MARGIN, 560), "Tomorrow:", fill=WHITE, font=f_sm)
    tm_w = int(draw.textlength("Tomorrow: ", font=f_sm))
    draw.text((MARGIN + tm_w, 560), f"{dsky_tmrw_desc}  ({dsky_tmrw}%)", fill=t_colour, font=f_sm)
    if lifted and lifted not in ("unknown", ""):
        li_w = int(draw.textlength(lifted, font=f_xs))
        draw.text((W - li_w - MARGIN, 564), lifted, fill=WHITE, font=f_xs)

    # Row 2 -- sun times (left) + next new/full moon dates (right)
    sun_parts = []
    if sunset:
        sun_parts.append(f"Sunset {sunset.strftime('%H:%M')}")
    if sunrise:
        sun_parts.append(f"Sunrise {sunrise.strftime('%H:%M')}")
    draw.text((MARGIN, 606), "  -  ".join(sun_parts), fill=WHITE, font=f_sm)

    moon_date_parts = []
    if next_new:
        moon_date_parts.append(f"New {next_new.strftime('%d %b')}")
    if next_full:
        moon_date_parts.append(f"Full {next_full.strftime('%d %b')}")
    if moon_date_parts:
        md_text = "  -  ".join(moon_date_parts)
        md_w    = int(draw.textlength(md_text, font=f_sm))
        draw.text((W - md_w - MARGIN, 606), md_text, fill=WHITE, font=f_sm)

    # Row 3 -- weather (consistent: Header value unit)
    wx = f"Temp {temp:.1f}°C  -  Dew {dew:.1f}°C  -  RH {humidity}%  -  Wind {wind_dir} {wind_spd:.1f} m/s"
    draw.text((MARGIN, 652), wx, fill=WHITE, font=f_sm)

    # Version stamp
    ver   = f"v{FIRMWARE_VERSION}"
    ver_w = int(draw.textlength(ver, font=f_xs))
    draw.text((W - ver_w - MARGIN, H - 30), ver, fill=DIM, font=f_xs)

    return img


def push_to_framebuffer(img):
    """Rotate the landscape image to the panel's portrait framebuffer and write
    it to /dev/fb0 as little-endian RGB565."""
    import numpy as np

    rot = img.transpose(ROTATE)
    if rot.size != (FB_W, FB_H):
        rot = rot.resize((FB_W, FB_H))
    arr = np.asarray(rot.convert("RGB"), dtype=np.uint16)
    r = (arr[:, :, 0] >> 3) << 11
    g = (arr[:, :, 1] >> 2) << 5
    b = arr[:, :, 2] >> 3
    packed = (r | g | b).astype("<u2")
    with open(FB_DEV, "wb") as f:
        f.write(packed.tobytes())


def main():
    parser = argparse.ArgumentParser(description="Touch Display 2 stargazing display")
    parser.add_argument("--save", metavar="PATH", help="Save PNG preview instead of driving the panel")
    args = parser.parse_args()

    config = load_config()
    ha_url = config["ha"]["url"].rstrip("/")
    token  = config["ha"]["token"]

    log.info("Fetching HA states...")
    states = fetch_states(ha_url, token)

    img = render(states)

    if args.save:
        log.info("Saving preview to %s", args.save)
        img.save(args.save)
        log.info("Saved.")
        return

    log.info("Writing to framebuffer %s...", FB_DEV)
    try:
        push_to_framebuffer(img)
    except FileNotFoundError:
        log.error("%s not found -- use --save <path.png> for development", FB_DEV)
        sys.exit(1)
    log.info("Done. v%s", FIRMWARE_VERSION)


if __name__ == "__main__":
    main()
