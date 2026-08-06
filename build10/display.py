#!/usr/bin/env python3
"""Stargazing conditions display for the Raspberry Pi Touch Display 2 (10.1", 1200x1920).

Portrait, which is the panel's native orientation - so unlike the 5" build there
is no rotation anywhere in the render path, and the touch mapping is a straight
scale. The extra area goes on content rather than on scale: type is larger than
the 5" build in pixels but the canvas is 2.5x, so more fits at a longer reading
distance.

  python3 display.py                 # daemon (mode from config, default animated)
  python3 display.py --once          # render a single frame to the panel and exit
  python3 display.py --save out.png  # save a single composited frame (dev/review)
"""

import argparse
import logging
import math
import random
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from core.daemon import install_signal_handlers, run_daemon
from core.fonts import font
from core.imagery import moon_image, paste_moon
from core.meteors import (
    SPORADIC_ZHR,
    active,
    next_shower,
    solar_longitude,
    visible_rate,
)
from core.night import NIGHT_CYCLE, apply_night, night_mode_now, night_window, tonight
from core.palette import (
    BG,
    DIM,
    MOON,
    MOON_DARK,
    MUTED,
    NOMINAL,
    OBJECT,
    STEEL,
    WHITE,
    verdict,
)
from core.panel import Framebuffer, Strip
from core.positions import alt_az, observer, plot_instant
from core.sky import Sky
from core.sky import sky_params as core_sky_params
from core.starfield import project, project_point
from core.targets import load_cutouts, peak, read_targets, ut_dt
from core.touch import TouchReader
from core.values import _dt, _f, _i, _phrase, load_config
from core.weather import KMH_TO_MPH, compare_sources, make_fetcher

VERSION = "0.6.0"

# The largest image this program legitimately opens is a 730x730 moon frame.
# PIL's default decompression-bomb threshold (~178M pixels) would let a hostile
# response balloon to a ~500MB decode before tripping. Cap it far above anything
# real and far below anything dangerous.
Image.MAX_IMAGE_PIXELS = 3_000 * 3_000

CONFIG_PATH = Path(__file__).parent / "config.toml"
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# The daemon hands build_pages a latitude, because that is all the 5" build ever
# needed. Computing alt-az needs a longitude too, and sky_params needs both
# without being handed either, so main() records them here.
LAT = None
LON = None

# Native portrait: the frame is written to the framebuffer as drawn, with no
# transpose. ROTATE stays None unless the panel is ever mounted on its side.
FB_DEV = "/dev/fb0"
W, H = 1200, 1920
FB_W, FB_H = 1200, 1920
ROTATE = None

# ── Layout constants (1200x1920 portrait) ─────────────────────────────────
# Bands, top to bottom: header, verdict, the Moon as the centrepiece, the
# condition bars, then the footer rows. The Moon gets the middle because it is
# the one element that rewards size - a 600px disc shows maria, the terminator
# and the earthshine limb, where the 5" build's 200px disc shows a shape.
MARGIN = 40
HLINE1 = 116                # header bottom
HLINE2 = 344                # verdict bottom
HLINE3 = 1240               # moon bottom
HLINE4 = 1620               # conditions bottom

MOON_CY = 700               # centre of the lunar disc
MOON_R = 300                # 600px across
# Four captions hang below the disc. Measured against their own line heights,
# not eyeballed: the first preview put the constellation line through HLINE3 and
# pushed the moon dates behind the condition bars entirely.
MOON_CAP1, MOON_CAP2 = 24, 86           # offsets below the disc edge
MOON_CAP3, MOON_CAP4 = 140, 186

BAR_Y0, BAR_GAP = 1284, 88
BAR_LBLW, BAR_W, BAR_H = 300, 620, 40

FOOT_Y0, FOOT_GAP = 1656, 56

# Touch control strip. Hidden until the panel is tapped, because this is an
# ambient display and permanent on-screen buttons would cost content space on
# every one of the thousands of frames nobody is touching.
STRIP_H = 80
STRIP_Y = H - STRIP_H - 24
BTN_GAP = 10

# Meteors are drawn at the real rate, sped up. Three an hour is honest and makes
# an animated sky look broken, so the panel runs them as though watching for this
# many minutes per minute. A stated convention, not a fudge - and it scales what
# is there rather than manufacturing what is not, so a night with nothing falling
# still shows nothing. Overridable as display.meteor_compression.
METEOR_COMPRESSION = 20.0

# Which way the window looks. The panel cannot know how it is oriented in the
# room, so this is chosen rather than detected: due south by default, because
# that is where everything transits from the northern hemisphere. The vertical
# field spans the full horizon-to-zenith; the horizontal one follows from the
# aspect ratio. Set sky.real_stars = false for the seeded random field instead.
REAL_STARS = True
CAMERA_AZ, CAMERA_ALT, CAMERA_FOV = 180.0, 45.0, 90.0
# The faintest stars are drawn 2px rather than 1px here. Portrait narrows the
# field to 56 degrees, so this panel holds a third fewer stars across 2.5x the
# pixels: measured against the 5" build it is a fifth of the lit area per
# megapixel, at identical per-star brightness. The field cannot be widened
# enough to fix that without turning the window into a fisheye, and a single
# pixel is 0.113mm here against 0.088mm on the 5", so the floor is raised
# instead. Size already stands in for brightness in this renderer - a brighter
# star reads as larger through glare - so this stays within that convention.
STAR_MIN_SIZE = 2

# The engine, sized for this panel. The daemon reads these three off this module
# as its layout.
sky = Sky(W, H, stars=520)
fb = Framebuffer(W, H, FB_W, FB_H, ROTATE, FB_DEV)
strip = Strip(W, MARGIN, STRIP_Y, STRIP_H, BTN_GAP, text_dy=24)

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


def _fonts():
    return {
        "xl":  font("IBMPlexSans-Bold.ttf", 132),
        "lg":  font("IBMPlexSans-SemiBold.ttf", 60),
        "med": font("IBMPlexSans-SemiBold.ttf", 44),
        "sm":  font("IBMPlexSans-Regular.ttf", 38),
        "xs":  font("IBMPlexSans-Regular.ttf", 30),
    }


def _centre(draw, text, y, fill, f):
    draw.text(((W - int(draw.textlength(text, font=f))) // 2, y), text, fill=fill, font=f)


def _right(draw, text, y, fill, f):
    draw.text((W - int(draw.textlength(text, font=f)) - MARGIN, y), text, fill=fill, font=f)


def _glyph(draw, cx, cy, r, otype):
    """Fallback mark when no cutout is available (offline, or a failed fetch)."""
    t = (otype or "").lower()
    if "globular" in t or "cluster" in t:
        random.seed(hash(otype) & 0xFFFF)
        for _ in range(40):
            a, d = random.uniform(0, 2 * math.pi), random.uniform(0, r * 0.85)
            draw.point((cx + d * math.cos(a), cy + d * math.sin(a)), fill=WHITE)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=STEEL)
    elif "galaxy" in t:
        draw.ellipse([cx - r, cy - r * 0.45, cx + r, cy + r * 0.45], outline=OBJECT, width=3)
        draw.ellipse([cx - r * 0.28, cy - r * 0.16, cx + r * 0.28, cy + r * 0.16], fill=OBJECT)
    else:                                            # nebulae and everything else
        draw.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], outline=OBJECT)
        draw.ellipse([cx - r * 0.6, cy - r * 0.45, cx + r * 0.6, cy + r * 0.45], outline=STEEL)


def _draw_moon(draw, cx, cy, r, illumination, waxing=True):
    """Parametric phase, used only when no Dial-a-Moon frame is available.

    A correct drawing beats a stale photograph: the phase moves about 12 degrees
    a day, so falling back to yesterday's frame would be confidently wrong.
    """
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=MOON_DARK, outline=MOON, width=4)
    if illumination < 1:
        return
    if illumination > 99:
        draw.ellipse([cx - r + 4, cy - r + 4, cx + r - 4, cy + r - 4], fill=MOON)
        return

    phase_angle = math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * illumination / 100.0)))
    term_scale  = math.cos(phase_angle)
    steps = 160
    pts   = []
    for i in range(steps + 1):
        t = math.pi / 2.0 - math.pi * i / steps
        pts.append((cx + r * math.cos(t), cy - r * math.sin(t)))
    for i in range(steps + 1):
        t = -math.pi / 2.0 + math.pi * i / steps
        pts.append((cx + r * term_scale * math.cos(t), cy - r * math.sin(t)))
    if not waxing:
        pts = [(2 * cx - px, py) for px, py in pts]
    draw.polygon(pts, fill=MOON)


def _moon_facts(facts):
    """The Moon's own numbers, as one line, or "" if the fetch failed.

    Straight from the frame's own metadata, so they describe the picture above
    them rather than a separate calculation that could disagree with it.
    Libration is given as the direction the near side is tipped, which is what
    "you can see a little further round that limb tonight" actually means.
    """
    if not facts:
        return ""
    bits = []
    age = facts.get("age")
    if age is not None:
        bits.append(f"{age:.1f} days old")
    dist = facts.get("distance")
    if dist is not None:
        bits.append(f"{dist:,.0f} km")
    diam = facts.get("diameter")
    if diam is not None:
        bits.append(f"{diam / 60:.1f}′ across")     # the API reports arcseconds
    lon, lat = facts.get("subearth_lon"), facts.get("subearth_lat")
    if lon is not None and lat is not None:
        ew = "E" if lon >= 0 else "W"
        ns = "N" if lat >= 0 else "S"
        bits.append(f"libration {abs(lon):.1f}°{ew} {abs(lat):.1f}°{ns}")
    return "   ·   ".join(bits)


def render_conditions(states, moon_photo=None, moon_ring=False, moon_facts=None):
    """Page 1 as an RGBA overlay: opaque content, transparent sky."""
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = _fonts()
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
    # The clock is NOT drawn here: this overlay is cached between data
    # refreshes, so a timestamp baked in would sit frozen. See draw_clock().
    draw.text((MARGIN, 30), "STARGAZING", fill=WHITE, font=f["lg"])
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM, width=2)

    # ── Verdict ───────────────────────────────────────────────────────
    if no_dark:
        v_text = "NO DARK SKY"
        v_sub = f"Next dark night: {next_dark.strftime('%d %b') if next_dark else 'unknown'}"
    else:
        v_text = verdict(dsky_today)
        v_sub = f"Deep sky: {dsky_today}%  -  {dsky_today_desc}"
    # Optical, not metric: heavy display type reads as indented beside regular
    # text even when the stems are flush, so it gets a small pull left.
    draw.text((MARGIN - 5, 146), v_text, fill=NOMINAL, font=f["xl"])
    draw.text((MARGIN, 288), v_sub, fill=WHITE, font=f["sm"])
    draw.line([(0, HLINE2), (W, HLINE2)], fill=DIM, width=2)

    # ── Moon ──────────────────────────────────────────────────────────
    if moon_photo is not None:
        paste_moon(img, moon_photo, W // 2, MOON_CY, MOON_R, ring=moon_ring)
    else:
        _draw_moon(draw, W // 2, MOON_CY, MOON_R, moon_phase, waxing)

    phase_name = PHASE_NAMES.get(
        moon_icon, moon_icon.replace("moon-", "").replace("-", " ").title())
    _centre(draw, phase_name, MOON_CY + MOON_R + MOON_CAP1, MOON, f["med"])
    if moon_const:
        _centre(draw, f"in {moon_const}", MOON_CY + MOON_R + MOON_CAP2, WHITE, f["sm"])

    moon_dates = []
    if next_new:
        moon_dates.append(f"New {next_new.strftime('%d %b')}")
    if next_full:
        moon_dates.append(f"Full {next_full.strftime('%d %b')}")
    if moon_dates:
        _centre(draw, "   -   ".join(moon_dates), MOON_CY + MOON_R + MOON_CAP3, MUTED, f["xs"])
    line = _moon_facts(moon_facts)
    if line:
        _centre(draw, line, MOON_CY + MOON_R + MOON_CAP4, MUTED, f["xs"])
    draw.line([(0, HLINE3), (W, HLINE3)], fill=DIM, width=2)

    # ── Conditions ────────────────────────────────────────────────────
    if no_dark and next_dark:
        days = max(0, (next_dark.date() - datetime.now().date()).days)
        big, sub = ("Tonight", "dark sky returns") if days == 0 else (str(days), "days until dark sky")
        _centre(draw, big, BAR_Y0 + 20, NOMINAL, f["xl"])
        _centre(draw, sub, BAR_Y0 + 170, WHITE, f["sm"])
    else:
        barx = MARGIN + BAR_LBLW
        valx = barx + BAR_W + 20
        # (label, value, good, warn) - the thresholds are drawn as ticks as well
        # as deciding whether the bar is filled or hollow, so the boundary the
        # form changes at is visible rather than implied.
        for i, (label, value, good, warn) in enumerate([
            ("Cloudless",    100 - cloud, 60, 40),
            ("Seeing",       seeing,      60, 40),
            ("Transparency", transp,      60, 40),
            ("Calm",         calm,        70, 50),
        ]):
            y = BAR_Y0 + i * BAR_GAP
            draw.text((MARGIN, y), label, fill=WHITE, font=f["sm"])
            # Coloured border > opaque trough > coloured fill (opaque over sky).
            draw.rectangle([barx - 2, y + 2, barx + BAR_W + 2, y + BAR_H + 6], fill=STEEL)
            draw.rectangle([barx, y + 4, barx + BAR_W, y + BAR_H + 4], fill=BG)
            # Below the warning mark the bar is hollow. Form, not colour: exact
            # rather than a gradient to read, and unaffected by the red filter.
            box = [barx, y + 4, barx + max(2, int(BAR_W * value / 100)),
                   y + BAR_H + 4]
            if value >= warn:
                draw.rectangle(box, fill=NOMINAL)
            else:
                draw.rectangle(box, outline=NOMINAL, width=3)
            for t in (warn, good):
                tx = barx + int(BAR_W * t / 100)
                draw.line([(tx, y + 4), (tx, y + 13)], fill=DIM)
                draw.line([(tx, y + BAR_H - 5), (tx, y + BAR_H + 4)], fill=DIM)
            draw.text((valx, y), f"{value}%", fill=WHITE, font=f["sm"])
    draw.line([(0, HLINE4), (W, HLINE4)], fill=DIM, width=2)

    # ── Footer ────────────────────────────────────────────────────────
    # Only the score is coloured. Colouring the whole phrase made a plain
    # description read as an alert and blunted the one figure that earned it.
    y = FOOT_Y0
    draw.text((MARGIN, y), "Tomorrow:", fill=WHITE, font=f["sm"])
    tm_w = int(draw.textlength("Tomorrow: ", font=f["sm"]))
    desc = f"{dsky_tmrw_desc}  "
    draw.text((MARGIN + tm_w, y), desc, fill=WHITE, font=f["sm"])
    draw.text((MARGIN + tm_w + int(draw.textlength(desc, font=f["sm"])), y),
              f"({dsky_tmrw}%)", fill=NOMINAL, font=f["sm"])

    # AstroWeather's sun rise/set entities are civil twilight bounds (sun 6 deg
    # below the horizon), not the geometric crossing - so they read dusk/dawn.
    y += FOOT_GAP
    sun_parts = []
    if sunset:
        sun_parts.append(f"Dusk {sunset.strftime('%H:%M')}")
    if sunrise:
        sun_parts.append(f"Dawn {sunrise.strftime('%H:%M')}")
    if sun_parts:
        draw.text((MARGIN, y), "  -  ".join(sun_parts), fill=WHITE, font=f["sm"])
    if lifted and lifted not in ("unknown", ""):
        _right(draw, f"LI: {lifted}", y, WHITE, f["sm"])

    # One row, not two: a fourth footer line would sit under the control strip
    # when it is showing. wind_spd is km/h internally and this is the only place
    # it is converted.
    y += FOOT_GAP
    draw.text((MARGIN, y),
              f"Temp {temp:.1f}°C  -  Dew {dew:.1f}°C  -  RH {humidity}%  -  "
              f"Wind {wind_dir} {wind_spd * KMH_TO_MPH:.1f} mph",
              fill=WHITE, font=f["sm"])

    _right(draw, f"v{VERSION}", H - 44, DIM, f["xs"])
    return img


# ── Page 2: tonight's targets ─────────────────────────────────────────────
P2_TIMELINE_Y = 168
# The altitude axis runs the full 0-90 here. On the 5" it stops at 70 because
# everything it plotted sat near the ecliptic and the top fifth was dead space;
# portrait has the room to carry the deep-sky objects too, and those do reach
# into it.
PAN_TOP, PAN_BASE = 348, 806
PAN_X0, PAN_X1 = MARGIN, W - MARGIN - 64
PAN_ALT_MAX = 90.0

P2_CARDS = 6
CARD_Y0, CARD_TILE, CARD_GAP = 940, 130, 16
# Requested larger than the tile so the downscale stays crisp; hips2fits renders
# whatever size is asked for, and the 5" build's 200px was only ever its own
# card size.
CUTOUT_PX = 320


def _tl_x(t, t0, t1, x0, x1):
    """Map a time onto the timeline, clamped to its ends. None if unusable."""
    if t is None or t0 is None or t1 is None or t1 <= t0:
        return None
    f = (t - t0).total_seconds() / (t1 - t0).total_seconds()
    return x0 + max(0.0, min(1.0, f)) * (x1 - x0)


def _draw_timeline(draw, states, y, f_xs):
    """Dusk-to-dawn bar with true astronomical darkness and moon-up marked."""
    x0, x1, h = MARGIN, W - MARGIN, 40
    dusk, dawn = night_window(states)
    if dusk is None or dawn <= dusk:
        return
    draw.rectangle([x0, y, x1, y + h], fill=BG, outline=STEEL)

    # Astronomical dark: the hours that actually count, not civil twilight.
    t_a0 = tonight(_dt(states.get("sensor.astroweather_backyard_sun_next_setting_astronomical")), dawn)
    t_a1 = tonight(_dt(states.get("sensor.astroweather_backyard_sun_next_rising_astronomical")), dawn)
    a0 = _tl_x(t_a0, dusk, dawn, x0, x1)
    a1 = _tl_x(t_a1, dusk, dawn, x0, x1)
    if a0 is not None and a1 is not None and a1 > a0:
        draw.rectangle([a0, y + 1, a1, y + h - 1], fill=NOMINAL)
        # The blue segment is the most important mark on the page and would
        # otherwise be the only unexplained one. Each time sits at the end of
        # the window it bounds with the name centred between them, so the strip
        # reads as an axis rather than as a caption with numbers after it.
        lab = "astronomical dark"
        s0, s1 = t_a0.strftime("%H:%M"), t_a1.strftime("%H:%M")
        w0 = draw.textlength(s0, font=f_xs)
        w1 = draw.textlength(s1, font=f_xs)
        wl = draw.textlength(lab, font=f_xs)
        seg, ty = a1 - a0, y + 6
        # Degrade by dropping pieces, never by overlapping them.
        if w0 + w1 + wl + 56 < seg:
            draw.text((a0 + 10, ty), s0, font=f_xs, fill=BG)
            draw.text((a1 - w1 - 10, ty), s1, font=f_xs, fill=BG)
            draw.text((a0 + (seg - wl) / 2, ty), lab, font=f_xs, fill=BG)
        elif w0 + w1 + 28 < seg:
            draw.text((a0 + 10, ty), s0, font=f_xs, fill=BG)
            draw.text((a1 - w1 - 10, ty), s1, font=f_xs, fill=BG)
        elif wl + 14 < seg:
            draw.text((a0 + (seg - wl) / 2, ty), lab, font=f_xs, fill=BG)

    # Moon up washes the sky out. Its own strip above the bar rather than a
    # translucent overlay, which just turned the whole thing muddy brown.
    # Setting-before-rising is what identifies "up now"; a plain day-shift gets
    # it wrong, because the next rising is tomorrow's while the next setting is
    # genuinely after the window.
    rise = _dt(states.get("sensor.astroweather_backyard_moon_next_rising"))
    set_ = _dt(states.get("sensor.astroweather_backyard_moon_next_setting"))
    m0 = m1 = None
    if rise is not None and set_ is not None:
        up_from, up_to = (dusk, set_) if set_ < rise else (rise, set_)
        m0 = _tl_x(up_from, dusk, dawn, x0, x1)
        m1 = _tl_x(up_to, dusk, dawn, x0, x1)
    if m0 is not None and m1 is not None and m1 > m0:
        draw.rectangle([m0, y - 14, m1, y - 6], fill=MOON)
        draw.text((m0 + 6, y - 20 - f_xs.size), "moon up", font=f_xs, fill=MOON)

    # Only mark "now" while it is actually within tonight; clamping it to an end
    # would draw a marker that reads as a real time when it is not.
    now = datetime.now().astimezone()
    if dusk <= now <= dawn:
        nx = _tl_x(now, dusk, dawn, x0, x1)
        draw.line([(nx, y - 6), (nx, y + h + 6)], fill=WHITE, width=3)

    d_lab, w_lab = dusk.strftime("Dusk %H:%M"), dawn.strftime("Dawn %H:%M")
    dw, ww = draw.textlength(d_lab, font=f_xs), draw.textlength(w_lab, font=f_xs)
    inside = (a0 is not None and a1 is not None
              and a0 - x0 > dw + 20 and x1 - a1 > ww + 20)
    ty = y + 6 if inside else y + h + 6
    draw.text((x0 + 10 if inside else x0, ty), d_lab, font=f_xs, fill=MUTED)
    draw.text((x1 - ww - (10 if inside else 0), ty), w_lab, font=f_xs, fill=MUTED)


def _draw_panorama(draw, marks, when_label, f_sm, f_xs):
    """Where to look: azimuth across, altitude up. A bearing and a height.

    marks are (az, alt, name, colour, radius) already computed for one instant -
    never taken from two reports written at different times.
    """
    draw.line([(PAN_X0, PAN_BASE), (PAN_X1, PAN_BASE)], fill=STEEL, width=2)
    for az, lab in ((0, "N"), (90, "E"), (180, "S"), (270, "W"), (360, "N")):
        x = PAN_X0 + (az / 360.0) * (PAN_X1 - PAN_X0)
        draw.line([(x, PAN_BASE), (x, PAN_BASE + 10)], fill=STEEL)
        draw.text((x - 9, PAN_BASE + 14), lab, font=f_xs, fill=MUTED)
    for alt in (30, 60, 90):
        y = PAN_BASE - (alt / PAN_ALT_MAX) * (PAN_BASE - PAN_TOP)
        draw.line([(PAN_X0, y), (PAN_X1, y)], fill=STEEL + (70,))
        draw.text((PAN_X1 + 6, y - 14), f"{alt}", font=f_xs, fill=MUTED)
    draw.text((PAN_X1 + 6, PAN_TOP - 38), "alt°", font=f_xs, fill=MUTED)

    # Labels are drawn at f_xs, not the body size: eleven marks share this plot
    # once the deep-sky objects join the planets, and type size is the cheapest
    # way to buy separation before resorting to leader lines everywhere.
    lh = f_xs.size + 6
    placed = []
    for az, alt, name, col, r in sorted(marks, key=lambda m: -m[1]):
        if alt < 0 or az < 0:
            continue                       # below the horizon: nothing to see
        x = PAN_X0 + (az / 360.0) * (PAN_X1 - PAN_X0)
        y = PAN_BASE - (min(alt, PAN_ALT_MAX) / PAN_ALT_MAX) * (PAN_BASE - PAN_TOP)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=col)

        # One line per object: the y axis already states the altitude, so
        # repeating it was duplication and it was what made labels collide. The
        # bearing stays - a compass axis cannot give it precisely.
        bearing = f"  {int(round(az))}°"
        nw = draw.textlength(name, font=f_xs)
        lw = nw + draw.textlength(bearing, font=f_xs)
        # Flip to the left of the marker in the right-hand third, so labels do
        # not run off the plot and so neighbours have somewhere else to go.
        side = -1 if x > PAN_X0 + 0.62 * (PAN_X1 - PAN_X0) else 1
        lx = x + r + 12 if side > 0 else x - r - 12 - lw
        base = y - lh // 2
        ly = None
        for off in (0, lh, -lh, 2 * lh, -2 * lh, 3 * lh, -3 * lh, 4 * lh, -4 * lh):
            cand = base + off
            if cand < PAN_TOP - 14 or cand + lh > PAN_BASE - 2:
                continue
            if not any(lx < b[2] and lx + lw > b[0] and cand < b[3] and cand + lh > b[1]
                       for b in placed):
                ly = cand
                break
        if ly is None:
            ly = max(PAN_TOP - 14, min(base, PAN_BASE - lh - 2))
        placed.append((lx, ly, lx + lw, ly + lh))
        if abs(ly - base) > 2:
            anchor = lx - 6 if side > 0 else lx + lw + 6
            draw.line([(x + side * r, y), (anchor, ly + lh // 2)], fill=STEEL)
        draw.text((lx, ly), name, font=f_xs, fill=WHITE)
        draw.text((lx + nw, ly), bearing, font=f_xs, fill=MUTED)


def _draw_cards(img, draw, objects, images, lat, obs, f):
    """Deep-sky targets, best first, with a real cutout of each patch of sky."""
    x0, y = MARGIN, CARD_Y0
    tile = CARD_TILE
    tx = x0 + tile + 24
    bar_w = 200
    bar_x = W - MARGIN - bar_w
    cap = "% of dark hours up"
    draw.text((bar_x + bar_w - draw.textlength(cap, font=f["xs"]), CARD_Y0 - 52),
              cap, font=f["xs"], fill=MUTED)

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
            _glyph(draw, x0 + tile // 2, y + tile // 2, tile // 2 - 8, o.get("type"))

        draw.text((tx, y + 2), oid, font=f["med"], fill=WHITE)

        mag = _f(o.get("mag"), 0)
        sub = f"{o.get('type', '')} in {o.get('constellation', '')}"
        if mag > 0:
            sub += f" · mag {mag:.1f}"
        draw.text((tx, y + 52), sub, font=f["xs"], fill=MUTED)

        # Two different questions, so both are answered: how high it ever gets
        # (from the declination, at meridian transit) and where it is at the
        # instant the plot above shows. Only the MERIDIAN transit gives the
        # time - the antimeridian one is the object's lowest point.
        dec, ra = o.get("declination"), o.get("right ascension")
        line = ""
        if dec is not None and lat is not None:
            alt, face = peak(dec, lat)
            line = f"peaks {alt:.0f}° {face}"
            when = ut_dt(str(o.get("meridian transit", "")))
            if when is not None:
                line += f" at {when.strftime('%H:%M')}"
        if ra is not None and dec is not None:
            now_alt, now_az = alt_az(obs, ra, dec)
            line += f"   ·   {now_alt:.0f}° up, bearing {now_az:.0f}°"
        if line:
            draw.text((tx, y + 92), line, font=f["xs"], fill=WHITE)

        # foto = fraction of astronomical darkness the object stays observable,
        # named by the column heading above.
        frac = max(0.0, min(1.0, _f(o.get("foto"))))
        draw.rectangle([bar_x, y + 128, bar_x + bar_w, y + 146], fill=BG, outline=STEEL)
        if frac > 0:
            # Same threshold convention as the conditions bars: short of the
            # mark is hollow. One rule across every page.
            box = [bar_x + 1, y + 129, bar_x + 1 + frac * (bar_w - 2), y + 145]
            if frac >= 0.75:
                draw.rectangle(box, fill=NOMINAL)
            else:
                draw.rectangle(box, outline=NOMINAL, width=2)
        y += tile + CARD_GAP


def render_targets(states, targets, images, lat=None, lon=None):
    """Page 2 as an RGBA overlay, or None when UpTonight has produced nothing."""
    objects = targets.get("objects") or []
    bodies  = targets.get("bodies") or []
    comets  = targets.get("comets") or []
    if not (objects or bodies):
        return None

    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = _fonts()
    f_title = font("IBMPlexSans-Bold.ttf", 60)

    draw.text((MARGIN, 30), "TONIGHT'S TARGETS", font=f_title, fill=WHITE)
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM)
    _draw_timeline(draw, states, P2_TIMELINE_Y, f["xs"])

    # One instant for everything on the plot, computed here rather than read -
    # the two report files are sampled about three hours apart.
    when, when_label = plot_instant(night_window(states))
    obs = observer(lat or 0.0, lon or 0.0, when=when.astimezone(timezone.utc).replace(tzinfo=None))

    marks = []
    for b in bodies:
        ra, dec = b.get("right ascension"), b.get("declination")
        if ra is None or dec is None:
            continue
        alt, az = alt_az(obs, ra, dec)
        name = str(b.get("target name", "?"))
        # Three populations share this plot, so each gets its own ink: the Moon
        # ivory, the planets MUTED, and everything further out - comets and deep
        # sky alike - the OBJECT green. Comet against deep sky is not a
        # distinction anyone needs at a glance, and both carry their name.
        col = MOON if name.lower() == "moon" else MUTED
        mag = _f(b.get("visual magnitude"), 5)
        marks.append((az, alt, name, col, max(5.0, min(15.0, 11.0 - mag * 0.8))))
    for c in comets:
        ra, dec = c.get("right ascension"), c.get("declination")
        if ra is not None and dec is not None:
            alt, az = alt_az(obs, ra, dec)
            marks.append((az, alt, str(c.get("target name", "?")), OBJECT, 7.0))

    ranked = sorted(objects, key=lambda o: (-_f(o.get("foto")), _f(o.get("mag"), 99)))
    for o in ranked[:P2_CARDS]:
        ra, dec = o.get("right ascension"), o.get("declination")
        if ra is None or dec is None:
            continue
        alt, az = alt_az(obs, ra, dec)
        marks.append((az, alt, str(o.get("id", "?")), OBJECT, 6.0))

    # The instant rides beside the heading, on its baseline: as a floating note
    # above the plot it landed on top of the heading itself. Without it the plot
    # silently reads as "now", which it is not once the sun is up.
    draw.text((MARGIN, 258), "WHERE TO LOOK", font=f["med"], fill=NOMINAL)
    draw.text((MARGIN + draw.textlength("WHERE TO LOOK", font=f["med"]) + 20, 272),
              when_label, font=f["sm"], fill=MUTED)
    _draw_panorama(draw, marks, when_label, f["sm"], f["xs"])

    shown = min(P2_CARDS, len(objects))
    count = (f"first {shown} of {len(objects)}" if shown < len(objects)
             else f"all {len(objects)}")
    draw.text((MARGIN, CARD_Y0 - 60), f"DEEP SKY  ({count})", font=f["med"], fill=NOMINAL)
    _draw_cards(img, draw, ranked, images, lat, obs, f)

    draw.text((MARGIN, H - 44), "Sky imagery: DSS2 / CDS Strasbourg",
              font=f["xs"], fill=DIM)
    return img


# ── Page 3: meteors ───────────────────────────────────────────────────────
MET_Y0, MET_GAP = 300, 190
MET_BAR_W, MET_BAR_H = 620, 36
# The scale the rate bars are drawn against. Fixed rather than relative to the
# strongest shower, so a quiet night looks quiet instead of being normalised
# back up to a full bar.
MET_RATE_FULL = 60.0


def render_meteors(states, lat, lon):
    """Page 3: what is actually falling tonight, computed from orbital constants.

    Returns None when nothing is running, so the page leaves the rotation rather
    than showing an empty frame.
    """
    when, when_label = plot_instant(night_window(states))
    utc = when.astimezone(timezone.utc).replace(tzinfo=None)
    showers = active(utc)
    if not showers:
        return None

    obs = observer(lat or 0.0, lon or 0.0, when=utc)
    cloud = _i(states.get("sensor.astroweather_backyard_cloud_cover"))
    moon_illum = _f(states.get("sensor.astroweather_backyard_moon_phase")) / 100.0

    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = _fonts()
    draw.text((MARGIN, 30), "METEORS", font=font("IBMPlexSans-Bold.ttf", 60), fill=WHITE)
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM, width=2)

    lam = solar_longitude(utc)
    draw.text((MARGIN, 160),
              f"Active showers {when_label}   ·   solar longitude {lam:.1f}°",
              font=f["sm"], fill=MUTED)
    draw.text((MARGIN, 210),
              f"Rates allow for radiant altitude, {cloud}% cloud "
              f"and {moon_illum * 100:.0f}% moon.",
              font=f["xs"], fill=MUTED)

    y = MET_Y0
    for s in showers[:4]:
        alt, az = alt_az(obs, s["ra"], s["dec"])
        rate = visible_rate(s["zhr"], s["strength"], alt, cloud, moon_illum)
        up = alt > 0

        draw.text((MARGIN, y), s["name"], font=f["lg"], fill=WHITE if up else DIM)
        # The peak is the actionable number when a shower is still building.
        days = (s["peak_lambda"] - lam) % 360.0 / 0.9856
        peak_note = ("peaking now" if s["delta_lambda"] < 0.5
                     else f"peak in {days:.0f} days" if days < 180
                     else f"{s['delta_lambda']:.0f}° past peak")
        _right(draw, peak_note, y + 14, MUTED, f["sm"])

        if up:
            where = f"radiant {alt:.0f}° up, bearing {az:.0f}°"
        else:
            # Below the horizon is not a failure to report - it is the answer.
            where = f"radiant below the horizon ({alt:.0f}°)"
        draw.text((MARGIN, y + 68), where, font=f["sm"], fill=MUTED)

        # Bar and figure describe the SAME quantity - what you would see - so
        # the headline ZHR rides alongside as context rather than as the number.
        by = y + 122
        draw.rectangle([MARGIN - 2, by - 2, MARGIN + MET_BAR_W + 2, by + MET_BAR_H + 2],
                       fill=STEEL)
        draw.rectangle([MARGIN, by, MARGIN + MET_BAR_W, by + MET_BAR_H], fill=BG)
        frac = max(0.0, min(1.0, rate / MET_RATE_FULL))
        if frac > 0:
            # Always filled, unlike the conditions and deep-sky bars. The hollow
            # convention marks a reading short of a threshold worth acting on,
            # and there is no such threshold here: observed rates are low single
            # digits on almost every night, so nearly every bar would be hollow,
            # and at a few pixels wide an outline degenerates into a small empty
            # box that reads as a rendering fault. The rate is printed beside it.
            draw.rectangle([MARGIN, by, MARGIN + max(2, int(MET_BAR_W * frac)),
                            by + MET_BAR_H], fill=NOMINAL)
        draw.text((MARGIN + MET_BAR_W + 20, by - 4),
                  f"~{rate:.0f}/hr", font=f["med"],
                  fill=WHITE if rate >= 1 else DIM)
        _right(draw, f"ZHR {s['zhr']} at peak", by + 8, DIM, f["xs"])
        y += MET_GAP

    # Anchored to the bottom rather than flowing after the last shower: the
    # number of active showers swings between one and four through the year, and
    # a summary that wanders up and down the page with it is harder to find than
    # one that is always in the same place.
    sy = H - 260
    draw.line([(0, sy - 30), (W, sy - 30)], fill=DIM, width=2)
    # Sporadics are the floor: quoting shower rates alone implies nothing falls
    # on an ordinary night, which is not true.
    spor = visible_rate(SPORADIC_ZHR, 1.0, 45.0, cloud, moon_illum)
    draw.text((MARGIN, sy), f"Sporadic background   ~{spor:.0f}/hr",
              font=f["sm"], fill=MUTED)
    nxt = next_shower(utc)
    if nxt:
        draw.text((MARGIN, sy + 56),
                  f"Next peak: {nxt[0]} in {nxt[1]:.0f} days",
                  font=f["sm"], fill=MUTED)

    draw.text((MARGIN, H - 44),
              "Shower elements are orbital constants, stored by solar longitude",
              font=f["xs"], fill=DIM)
    return img


def refresh_stars():
    """Point the starfield at the real sky for right now.

    The panel cannot know which way it faces, so the direction is configuration,
    not inference: CAMERA_AZ is where the window looks and CAMERA_ALT the height
    of its centre. Everything behind the dashboard is then the part of the sky
    actually in that direction, turning because the Earth does.

    Recomputed on a timer rather than per frame - the sky moves a quarter of a
    degree a minute, so once a minute is imperceptibly smooth and costs nothing.

    Meteor radiants are refreshed here and nowhere else, so switching the real
    sky off also returns meteors to arbitrary directions. That is deliberate: a
    correct radiant over an invented starfield is false precision, and the two
    should be real together or not at all.
    """
    if not REAL_STARS:
        return
    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    obs = observer(LAT or 0.0, LON or 0.0, when=utc)
    stars = project(obs, W, H, CAMERA_AZ, CAMERA_ALT, CAMERA_FOV, STAR_MIN_SIZE)
    sky.set_stars(stars)
    refresh_radiants(obs, utc)
    return len(stars)


def refresh_radiants(obs, utc):
    """Point tonight's meteors at the radiants they actually come from.

    Computed here rather than alongside the rate in sky_params because the
    radiant climbs and sets with everything else in the sky, so it belongs on
    the same minute cadence as the stars it is drawn among. The rate keeps its
    own home: this decides which way a meteor goes, not how often one appears.

    The weights are the relative rates only, so cloud and moonlight are absent
    by design - both cut every shower and the sporadics by the same factor and
    cancel out of the ratio. They already do their work on the cadence.
    """
    px_per_degree = H / CAMERA_FOV
    radiants = []
    for s in active(utc):
        alt, az = alt_az(obs, s["ra"], s["dec"])
        if alt <= 0.0:
            continue                  # radiant below the horizon: no meteors from it
        x, y, _inside = project_point(az, alt, W, H,
                                      CAMERA_AZ, CAMERA_ALT, CAMERA_FOV)
        radiants.append((x, y, s["zhr"] * s["strength"] * math.sin(math.radians(alt))))
    # A sporadic belongs to no shower and has no radiant, so it is carried as a
    # weight with no position. Its reference altitude matches the one the rate
    # uses, so the two agree on how much of tonight is sporadic.
    radiants.append((None, None, SPORADIC_ZHR * math.sin(math.radians(45.0))))
    sky.set_radiants(radiants, px_per_degree)


def _star_thread():
    while True:
        time.sleep(60)
        try:
            refresh_stars()
        except Exception as e:      # a bad fix must not stop the display
            log.warning("Star refresh failed: %s", e)


def sky_params(states):
    """The sky's mood, with the meteors made real.

    core.sky spawns meteors on a fixed cadence scaled by cloud - so a clear
    night in March, when almost nothing is falling, shows the same shower as the
    Perseid peak. This build knows better: page 3 already computes what an
    observer would actually count tonight, so the same figure sets the cadence.

    NOTHING ACTIVE MEANS NO METEORS. Once a display draws real showers, inventing
    them on a quiet night is the same class of error as showing yesterday's Moon.

    The rate is TIME-COMPRESSED, and that is a deliberate convention rather than
    an accident: three an hour is honest and makes an animated sky look broken,
    so the panel runs meteors as though watching for `meteor_compression` minutes
    per minute. Zero stays zero - the compression scales what is there and cannot
    manufacture what is not.
    """
    params = core_sky_params(states)
    when, _ = plot_instant(night_window(states))
    utc = when.astimezone(timezone.utc).replace(tzinfo=None)
    obs = observer(LAT or 0.0, LON or 0.0, when=utc)
    cloud = _i(states.get("sensor.astroweather_backyard_cloud_cover"))
    moon_illum = _f(states.get("sensor.astroweather_backyard_moon_phase")) / 100.0

    rate = visible_rate(SPORADIC_ZHR, 1.0, 45.0, cloud, moon_illum)
    for s in active(utc):
        alt, _az = alt_az(obs, s["ra"], s["dec"])
        rate += visible_rate(s["zhr"], s["strength"], alt, cloud, moon_illum)

    if rate <= 0 or params["twilight"]:
        params["meteors"] = False
        return params
    mean = 3600.0 / (rate * METEOR_COMPRESSION)
    params["meteors"] = True
    params["met_min"] = max(1.5, mean * 0.5)
    params["met_max"] = max(3.0, mean * 1.5)
    return params


def draw_clock(draw):
    """Stamp the header date and time onto a composed frame.

    Per frame rather than into the cached overlay, so the minute advances live
    and the date rolls over at midnight. Anything time-derived has to live here.
    """
    f_sm = font("IBMPlexSans-Regular.ttf", 38)
    now  = datetime.now().strftime("%a %d %b  %H:%M")
    draw.text((W - int(draw.textlength(now, font=f_sm)) - MARGIN, 44),
              now, fill=MUTED, font=f_sm)


def build_pages(states, targets, lat, moon_ring=False):
    """Every page as an RGBA overlay. Data thread only: this fetches the hour's
    lunar frame and any deep-sky cutouts not already cached."""
    photo, facts = moon_image()
    pages = [render_conditions(states, photo, moon_ring, facts)]
    # The targets page joins the rotation only when there is something on it -
    # better one live page than two with a dead one.
    page2 = render_targets(states, targets,
                           load_cutouts(targets, P2_CARDS, CUTOUT_PX), lat, LON)
    if page2 is not None:
        pages.append(page2)
    page3 = render_meteors(states, lat, LON)
    if page3 is not None:
        pages.append(page3)
    return pages


def compose(frame, overlay, labels=None):
    """Dashboard, clock and control strip over a painted sky frame."""
    frame.paste(overlay, (0, 0), overlay)
    d = ImageDraw.Draw(frame)
    draw_clock(d)
    if labels:
        strip.draw(d, labels, font("IBMPlexSans-SemiBold.ttf", 30))
    return frame


def main():
    parser = argparse.ArgumentParser(description="Touch Display 2 stargazing display (10.1\")")
    parser.add_argument("--save", metavar="PATH", help="Save a single composited frame and exit")
    parser.add_argument("--once", action="store_true", help="Render one frame to the panel and exit")
    parser.add_argument("--demo", action="store_true", help="Force vivid clear-sky animation (ignore conditions)")
    parser.add_argument("--compare", action="store_true",
                        help="Fetch from both weather sources and print a per-value diff")
    args = parser.parse_args()

    global LAT, LON
    config = load_config(CONFIG_PATH)
    out_dir = config.get("uptonight", {}).get("out_dir", "")
    lat    = config.get("location", {}).get("latitude")
    LON    = config.get("location", {}).get("longitude")
    LAT    = lat
    disp   = config.get("display", {})
    mode   = disp.get("mode", "animated")
    fps    = float(disp.get("fps", 12))
    refresh_min = float(disp.get("data_refresh_min", 15))
    page_seconds = float(disp.get("page_seconds", 20))
    night = disp.get("night_mode", "off")
    night_dim = int(disp.get("night_dim", 45))
    if night not in NIGHT_CYCLE:
        raise ValueError(f'display.night_mode is "{night}"; expected "off", "dim" or "red"')
    moon_ring = bool(disp.get("moon_ring", False))
    global METEOR_COMPRESSION, REAL_STARS, CAMERA_AZ, CAMERA_ALT, CAMERA_FOV
    METEOR_COMPRESSION = float(disp.get("meteor_compression", METEOR_COMPRESSION))
    skycfg = config.get("sky", {})
    REAL_STARS = bool(skycfg.get("real_stars", REAL_STARS))
    CAMERA_AZ  = float(skycfg.get("camera_azimuth", CAMERA_AZ))
    CAMERA_ALT = float(skycfg.get("camera_altitude", CAMERA_ALT))
    CAMERA_FOV = float(skycfg.get("field_of_view", CAMERA_FOV))
    tch = config.get("touch", {})

    if args.compare:
        return compare_sources(config)

    fetch = make_fetcher(config)

    if args.save or args.once:
        log.info("Fetching conditions...")
        n = refresh_stars()
        if n is not None:
            log.info("%d catalogue stars in view.", n)
        states = fetch()
        params = sky_params(states)
        pages = build_pages(states, read_targets(out_dir), lat, moon_ring)
        # A saved preview should look like the panel does right now, night mode
        # included - otherwise --save quietly lies once the sun goes down.
        now_mode = night_mode_now(night, night_window(states))
        frames = [compose(sky.paint(params, 1.7, [], sky.initial_clouds(params)), p)
                  for p in pages]
        if args.save:
            p = Path(args.save)
            for i, frame in enumerate(frames):
                out = args.save if i == 0 else str(p.with_name(f"{p.stem}_{i + 1}{p.suffix}"))
                apply_night(frame, now_mode, night_dim).save(out)
                log.info("Saved %s", out)
        else:
            with fb.open() as out:
                out.write(fb.to_bytes(frames[0], now_mode, night_dim))
            log.info("Done. v%s", VERSION)
        return

    install_signal_handlers()
    n = refresh_stars()
    if n is not None:
        log.info("Real sky: %d catalogue stars in view, az %.0f alt %.0f fov %.0f.",
                 n, CAMERA_AZ, CAMERA_ALT, CAMERA_FOV)
        threading.Thread(target=_star_thread, daemon=True).start()
    reader = (TouchReader(W, H, FB_W, FB_H, rotated=ROTATE is not None)
              if tch.get("enabled", True) else None)
    # This module is the layout the daemon draws through: it supplies sky, fb,
    # strip, build_pages, compose and night_window.
    run_daemon(sys.modules[__name__], fetch, read_targets, out_dir, lat,
               animated=(mode != "static"), fps=fps, refresh_min=refresh_min,
               page_seconds=page_seconds, demo=args.demo, night=night,
               night_dim=night_dim, touch_reader=reader,
               strip_seconds=float(tch.get("strip_seconds", 6)),
               moon_ring=moon_ring)


if __name__ == "__main__":
    main()
