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
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from core.aurora import FIELD_ALT_BINS, FIELD_AZ_BINS, compass
from core.aurora import visible_now as aurora_now
from core.daemon import Paged, flatten, install_signal_handlers, run_daemon
from core.fonts import font
from core.imagery import moon_image, paste_moon, paste_sun, sun_image
from core.meteors import (
    NAMED_SHOWER_FLOOR,
    PEAKING_STRENGTH,
    SPORADIC_ZHR,
    active,
    next_shower,
    solar_longitude,
    upcoming,
    visible_rate,
)
from core.night import (
    NIGHT_CYCLE,
    apply_night,
    inside_window,
    night_mode_now,
    night_window,
    tonight,
)
from core.palette import (
    AURORA_GREEN,
    AURORA_RED,
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
from core.panel import PIL_ROTATION, Framebuffer, Strip
from core.positions import alt_az, next_rise, observer, plot_instant
from core.satellites import elements_age, passes
from core.sky import Sky
from core.sky import sky_params as core_sky_params
from core.solar import CME_LOOKAHEAD_DAYS, next_eclipse, project_spot, solar_b0, sun_up
from core.solar import activity as solar_activity
from core.starfield import (
    SIZE_BANDS_SPARSE_10,
    SPARSE_BRIGHT,
    SPARSE_FLOOR,
    SPARSE_RATIO,
    project,
    project_point,
    px_per_degree,
)
from core.targets import load_cutouts, peak, rank_objects, read_targets, ut_dt
from core.touch import TouchReader
from core.values import _dt, _f, _i, _phrase, load_config
from core.weather import KMH_TO_MPH, compare_sources, make_fetcher, obscuration_of

VERSION = "0.46.0"

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

# Native portrait, but mounted UPSIDE DOWN - see stand10/README.md. The panel's
# two bracket pairs sit at different offsets and its Pi is not vertically
# centred, so only one way up leaves a stand anywhere to bolt to; that way up
# also puts the Pi's port face at the top, where the cables want to leave from.
#
# The turn happens here rather than in the DSI overlay. The overlay's own
# rotation= sets a KMS property, which fbcon honours and a process writing
# bytes straight at /dev/fb0 does not - the hardware simply scans out what it
# is given. Measured cost of doing it here is 2.4 ms a frame, because to_bytes
# already had to hand the image to PIL and a transpose is one more C pass.
#
# ONE figure, handed to both the framebuffer and the touch reader. The
# touchscreen reports in the panel's own frame whatever the renderer does, so a
# rotation applied to the image and not to the taps puts every press
# diagonally opposite where the finger went.
FB_DEV = "/dev/fb0"
W, H = 1200, 1920
FB_W, FB_H = 1200, 1920
ROTATE_DEG = 180
ROTATE = PIL_ROTATION[ROTATE_DEG]

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
#
# SUPERSEDED IN PRACTICE, and left in place as the floor it always was. It is
# what made drawn area track star COUNT rather than magnitude on this panel -
# measured, all 1060 stars in view came out at 3x3 - so the ordering that makes
# a sky recognisable was absent entirely. SIZE_BANDS_SPARSE_10 has a catch-all
# of 3, so this no longer binds on anything; it still guards a build that raises
# its limiting magnitude far enough to reach the 1-pixel band.
STAR_MIN_SIZE = 2

# Faintest star drawn, matching the 5" build. The same site cannot have two
# different skies, so this is deliberately not tuned per panel even though this
# one shows a narrower window magnified over more pixels and so holds fewer
# stars. What compensates is the size table, not a fainter cut.
LIMITING_MAG = 5.0

# Twinkle amplitude at the ZENITH, and the ceiling near the horizon. Each star
# takes the first scaled by the airmass its light crosses and clamped to the
# second, so a star overhead sits almost steady while one low down shimmers -
# which is what scintillation actually does, and why a single figure looked
# wrong in both halves of the field at once.
#
# In magnitudes, 0.05 is a 0.20 mag swing and 0.20 is 0.83. The field shipped
# at a flat 0.45, or 1.33 mag, against the 0.1-0.3 mag real scintillation
# manages at mid altitude - so it read as the sky breathing.
#
# Both are well under 0.327, the amplitude at which the trough of the faintest
# star meets draw_stars' cull at the lowest gain the display produces.
TWINKLE_AMP, TWINKLE_MAX = 0.018, 0.12

# How often the real positions are recomputed. Nothing interpolates between
# refreshes - the whole field is swapped at once - so this interval IS the size
# of the step the sky takes, and the step is coherent: the mean displacement
# vector at 60 s was (+8.6, +0.1) px, the entire field sliding sideways
# together. Coherent motion is far more visible than the same distance
# scattered across stars, which is why a jump this small was noticed on the
# panel.
#
# At 21.3 px/degree here and 0.2507 degrees a minute, 5 s puts the step at
# about 0.5 px. Since positions are rounded to whole pixels, most stars then do
# not move at all on a given refresh and the rest step by one, so what was one
# visible slide becomes a scatter of single pixels. Measured cost is 32 ms a
# refresh, i.e. 0.64% of one core - interpolation would buy nothing this does
# not, for a great deal more machinery.
STAR_REFRESH_S = 5

# Aurora. The emission height is the honest knob for how far into the distance
# this may claim to see: 250 km is the high red emission, which is the part that
# clears a distant horizon first and is what gets reported from well south of
# the oval. The threshold is deliberately NOT per-site - the same cut gives a
# temperate site an event every few years and a high-latitude one a frequent
# page, because that difference is real rather than a setting.
AURORA_ENABLED = True
AURORA_THRESHOLD = 10.0
AURORA_EMISSION_KM = 250.0

# The engine, sized for this panel. The daemon reads these three off this module
# as its layout.
sky = Sky(W, H, stars=520, twinkle=TWINKLE_AMP, twinkle_max=TWINKLE_MAX, fov=CAMERA_FOV)
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
        # ⇒ THE FOOTNOTE SIZE, AND DIM IS WHAT SELECTS IT. core.palette defines
        # DIM as rules, ticks and marginal notes and says outright that it is
        # never content, so "drawn in DIM" already means "this is a footnote" -
        # the size follows the colour rather than being chosen per call site.
        # Four stacked credit lines at the xs size read as a block rather than
        # as margin, which is what prompted the separate size.
        "fn":  font("IBMPlexSans-Regular.ttf", 26),
    }


def _centre(draw, text, y, fill, f):
    draw.text(((W - int(draw.textlength(text, font=f))) // 2, y), text, fill=fill, font=f)


def _days(n):
    """A rounded day count with the plural that matches it.

    The count is rounded first and the plural follows the ROUNDED value, so a
    peak 1.4 days away reads "1 day" and not "1 days". Every day figure on this
    page went through `:.0f`, which meant the singular case was wrong on
    precisely the day the page matters most - the day before a shower peak.

    Under half a day it switches to hours. Days alone were enough while nothing
    could be reported closer to its peak than half a degree of solar longitude,
    which is about twelve hours; measuring that window by rate instead admits
    distances far shorter than a day for the sharply peaked showers, and the
    rounding would otherwise render them as "0 days".
    """
    n_days = round(n)
    if n_days == 0:
        hours = max(1, round(n * 24))
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    return f"{n_days} day" if n_days == 1 else f"{n_days} days"


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

    # Obscuration, not raw cover: 100% thin cirrus stops far less light than
    # 100% stratus, and the Cloudless bar is a judgement about observing.
    # See core.weather.cloud_obscuration.
    cloud  = obscuration_of(s)
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

    _right(draw, f"v{VERSION}", H - 44, DIM, f["fn"])
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
# The 'below the horizon' line, clear of the compass row at PAN_BASE + 14.
PAN_BELOW_Y = 848

P2_CARDS = 6
# CARD_Y0 moved down 24 to make room for the below-horizon line above it.
# Six cards at CARD_TILE + CARD_GAP end at 1840, clear of the footer at
# H - 44.
CARD_Y0, CARD_TILE, CARD_GAP = 964, 130, 16
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
        # Modulo AFTER rounding: 359.7 rounds to 360, which is a bearing that
        # does not exist and reads as an error next to a compass axis marked N.
        bearing = f"  {int(round(az)) % 360}°"
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
    """One screenful of deep-sky targets, with a real cutout of each patch of sky.

    Takes the objects already chosen rather than slicing here, so the caller's
    heading, the panorama marks and these cards cannot disagree about which
    screenful is showing.
    """
    x0, y = MARGIN, CARD_Y0
    tile = CARD_TILE
    tx = x0 + tile + 24
    bar_w = 200
    bar_x = W - MARGIN - bar_w
    cap = "% of dark hours up"
    draw.text((bar_x + bar_w - draw.textlength(cap, font=f["xs"]), CARD_Y0 - 52),
              cap, font=f["xs"], fill=MUTED)

    for o in objects:
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


def render_targets(states, targets, images, lat=None, lon=None, offset=0):
    """One screenful of page 2, or None when UpTonight has produced nothing.

    `offset` is the first card's place in the ranking. The panorama marks follow
    it, so the plot and the cards always describe the same objects; showing
    marks for the first six while the cards list the next six would be two
    answers to one question.
    """
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
    # Bodies below the horizon are dropped from the plot, which leaves nothing
    # to distinguish "no planets tonight" from "none of them has risen yet".
    # They are collected here and reported with their rise times underneath,
    # which is most useful exactly when the plot looks empty.
    below = []
    for b in bodies:
        ra, dec = b.get("right ascension"), b.get("declination")
        if ra is None or dec is None:
            continue
        alt, az = alt_az(obs, ra, dec)
        name = str(b.get("target name", "?"))
        if alt < 0:
            rise = next_rise(obs, name, ra, dec)
            below.append((name, rise))
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

    ranked = rank_objects(objects)
    page_objects = ranked[offset:offset + P2_CARDS]
    for o in page_objects:
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

    if below:
        # Soonest first: the next thing to rise is the actionable one. A body
        # ephem reports as never rising carries no time rather than a guess.
        below.sort(key=lambda r: (r[1] is None, r[1]))
        parts = [f"{n} {t:%H:%M}" if t else n for n, t in below]
        # MUTED throughout, not DIM. DIM is for rules and ticks; at 3.2:1 on
        # this background it is below AA wherever it is legible at all, and
        # these are rise times someone acts on.
        draw.text((MARGIN, PAN_BELOW_Y),
                  "Below the horizon:   " + "   ·   ".join(parts),
                  font=f["xs"], fill=MUTED)

    count = (f"all {len(objects)}" if len(objects) <= P2_CARDS
             else f"{offset + 1}-{offset + len(page_objects)} of {len(objects)}")
    draw.text((MARGIN, CARD_Y0 - 60), f"DEEP SKY  ({count})", font=f["med"], fill=NOMINAL)
    _draw_cards(img, draw, page_objects, images, lat, obs, f)

    draw.text((MARGIN, H - 44), "Sky imagery: DSS2 / CDS Strasbourg",
              font=f["fn"], fill=DIM)
    return img


# ── Page 3: meteors ───────────────────────────────────────────────────────
MET_Y0, MET_GAP = 300, 190
# How tall one active shower's block actually is - name, radiant line, bar - as
# against MET_GAP, which is the pitch between them. The difference is the gap
# below the last one, and it has to be taken back before measuring what is left
# for the "coming up" list or the section starts a whole gap too low.
MET_ROW_H = 150
MET_UP_HEAD, MET_UP_ROW, MET_UP_PAD = 60, 66, 70
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
    # Faded showers are dropped here rather than in active(), which the animated
    # sky and its radiants also read: they are still falling, and only the claim
    # that they are worth watching for expires. See NAMED_SHOWER_FLOOR.
    showers = [s for s in active(utc)
               if s["zhr"] * s["strength"] >= NAMED_SHOWER_FLOOR]
    if not showers:
        return None

    obs = observer(lat or 0.0, lon or 0.0, when=utc)
    cloud = obscuration_of(states)
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
        # Both sides are quoted in elapsed time. Solar longitude is how the
        # table is stored and searched, but it is not a unit anyone observes
        # in, so it is converted here rather than leaking into one branch of
        # the label: past the peak the next crossing is nearly a full orbit
        # away, so the forward distance is useless and the elapsed distance is
        # the answer.
        #
        # Whether the shower is AT its peak is a separate question, and asking
        # it of the distance was the bug: see PEAKING_STRENGTH.
        days_to = (s["peak_lambda"] - lam) % 360.0 / 0.9856
        days_since = s["delta_lambda"] / 0.9856
        peak_note = ("peaking now" if s["strength"] >= PEAKING_STRENGTH
                     else f"{_days(days_to)} before peak" if days_to < 180
                     else f"{_days(days_since)} past peak")
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
        # The two figures on this row differ by a factor nothing named, which
        # read as a contradiction: 150 beside 100 with no stated link. "overhead"
        # is the link, because the radiant's altitude is what almost always
        # accounts for the gap, and the line above this one has already printed
        # it. Quoting the surviving fraction instead was tried and did not help:
        # it stated the SIZE of the gap without naming its cause, which leaves
        # the reader exactly where they started. The foot of the page carries the
        # definition in full.
        #
        # KEEP THIS STRING SHORT. It is right-aligned and the rate figure is
        # drawn from a fixed x, so every character eats leftward into it. The
        # widest the page can print is the rate at the zenith, which leaves
        # 288px here in Plex at this size; "ZHR 150 at peak - 67% of it tonight"
        # wanted 492 and overlapped the rate on the panel, and even
        # "ZHR 150 at the zenith" misses at 293. Measure any replacement ON the
        # Pi: core.fonts resolves two Linux paths and otherwise silently returns
        # Pillow's default bitmap face, which is narrow enough to report a
        # comfortable fit for a string that collides.
        _right(draw, f"ZHR {s['zhr']} overhead", by + 8, DIM, f["fn"])
        y += MET_GAP

    # Anchored to the bottom rather than flowing after the last shower: the
    # number of active showers swings between one and four through the year, and
    # a summary that wanders up and down the page with it is harder to find than
    # one that is always in the same place.
    sy = H - 260

    # What the active rows did not use goes to the next peaks. Measured over a
    # year at this site, no shower is running on 43% of nights and exactly one
    # on a further 27%, so the common case left most of this page empty - and
    # the emptiest night of all is 14 December, the Geminids' own peak, when
    # nothing else is up. The count is derived from the space rather than
    # fixed, which gives the section the property worth having: it grows
    # precisely when there is least else to report.
    used = MET_Y0 + len(showers[:4]) * MET_GAP - (MET_GAP - MET_ROW_H)
    room = (sy - 30) - used - MET_UP_PAD
    # Bounded by the room, not by a fixed count. The table holds eleven showers,
    # so on a quiet night this becomes the year's meteor calendar and on a busy
    # one it truncates to whatever is left - which is the behaviour worth having
    # rather than a compromise, since a distant peak is only worth printing when
    # there is nothing nearer to say.
    n_up = max(0, min(10, int((room - MET_UP_HEAD) // MET_UP_ROW)))
    shown = {s["name"] for s in showers[:4]}
    soon = ()
    if n_up:
        soon = upcoming(utc, exclude=shown, within_days=365, limit=n_up)
        if soon:
            uy = used + MET_UP_PAD
            draw.text((MARGIN, uy), "COMING UP",
                      font=f["fn"], fill=DIM)
            uy += MET_UP_HEAD
            for name, days, zhr in soon:
                draw.text((MARGIN, uy), name, font=f["med"], fill=MUTED)
                _right(draw, f"in {_days(days)}   ·   ZHR {zhr:.0f}",
                       uy + 8, DIM, f["sm"])
                uy += MET_UP_ROW

    draw.line([(0, sy - 30), (W, sy - 30)], fill=DIM, width=2)
    # Sporadics are the floor: quoting shower rates alone implies nothing falls
    # on an ordinary night, which is not true.
    spor = visible_rate(SPORADIC_ZHR, 1.0, 45.0, cloud, moon_illum)
    draw.text((MARGIN, sy), f"Sporadic background   ~{spor:.0f}/hr",
              font=f["sm"], fill=MUTED)
    # The fallback for a page with no room for COMING UP, not a second copy of
    # it: when that list rendered, its first row IS the next peak, and printing
    # the same shower again in a different format is the duplication upcoming()
    # already excludes actives to avoid.
    if not soon:
        nxt = next_shower(utc, exclude=shown)
        if nxt:
            draw.text((MARGIN, sy + 56),
                      f"Next peak: {nxt[0]} in {_days(nxt[1])}",
                      font=f["sm"], fill=MUTED)

    # Both notes explain what is being read rather than reporting anything, so
    # they sit together at the foot. ZHR is the page's one piece of jargon and
    # the only figure on it that is not an observation: saying so once here
    # carries every row, where the rows themselves have about two words of space.
    draw.text((MARGIN, H - 88),
              "ZHR assumes an overhead radiant and a perfect sky",
              font=f["fn"], fill=DIM)
    draw.text((MARGIN, H - 44),
              "Shower elements are orbital constants, stored by solar longitude",
              font=f["fn"], fill=DIM)
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
    stars = project(obs, W, H, CAMERA_AZ, CAMERA_ALT, CAMERA_FOV, STAR_MIN_SIZE,
                    limit=LIMITING_MAG, bands=SIZE_BANDS_SPARSE_10,
                    ratio=SPARSE_RATIO, floor=SPARSE_FLOOR,
                    bright=SPARSE_BRIGHT)
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
    # From the projection itself, not h/fov: gnomonic scale at the axis is
    # not the plate carree's uniform pixels-per-degree, and the two differ
    # by about a quarter on the 10.1" field.
    ppd = px_per_degree(H, CAMERA_FOV)
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
    sky.set_radiants(radiants, ppd)


def _star_thread():
    while True:
        time.sleep(STAR_REFRESH_S)
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
    cloud = obscuration_of(states)
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


# ── Page 4: aurora ────────────────────────────────────────────────────────
AUR_Y0, AUR_GAP = 900, 64
AUR_KP_H = 220
# Kp runs 0-9 and 5 is the minor-storm threshold, which is the level worth
# getting up for from a temperate latitude. Drawing the axis to 9 rather than to
# whatever the forecast happens to reach keeps a quiet outlook looking quiet.
AUR_KP_MAX, AUR_KP_STORM = 9.0, 5.0


# Opacity IS the probability - a 60% cell is drawn 60% solid - so the shape
# carries the strength without a legend, and no separate brightness constant can
# drift away from the numbers printed beside it. Measured on the composited
# frame, not on the bare overlay, where transparent reads as black and the same
# values look far stronger than the panel renders them.
AUR_FIELD_BLUR = 20
# Where the colour turns over, in km of lowest-visible altitude. The green line
# is emitted around 100-150 km, so once the Earth hides everything below about
# 180 km only the red is left; below about 110 km the green band is fully in
# view. An inference from geometry, not something OVATION reports.
AUR_GREEN_SEEN_KM, AUR_RED_ONLY_KM = 110.0, 180.0


def _draw_aurora_field(img, field):
    """The storm's real extent on the bearing-by-altitude plot.

    Every lit model cell above the horizon, binned and shaded by probability, so
    the drawn shape is the model's own from this position. The blur is
    PRESENTATION and nothing else: it smooths the grid's steps, which is exactly
    why the two reported points and every number on the page come from the
    unsmoothed cells rather than from this image.

    What is deliberately not drawn is structure - curtains, rays, a green glow.
    The model resolves nothing of the sort, so drawing it would be inventing on
    top of data that already exists, which is the error the starfield and the
    meteor radiants were changed to stop making.
    """
    if not field:
        return
    w, h = FIELD_AZ_BINS, FIELD_ALT_BINS
    # The unlit background is red, not black: blurring pulls the surround into
    # the edges, and the faint fringe of any aurora is its most distant part -
    # which is the red one. Black would just dirty the edge.
    hue = Image.new("RGB", (w, h), AURORA_RED)
    alpha = Image.new("L", (w, h), 0)
    phue, palpha = hue.load(), alpha.load()
    for az, alt, prob, low_km in field:
        x = min(w - 1, int(az / 360.0 * w))
        # Altitude runs up the plot, so the top row is the zenith.
        y = min(h - 1, int((1.0 - min(alt, PAN_ALT_MAX) / PAN_ALT_MAX) * h))
        v = int(min(100.0, prob) / 100.0 * 255)
        if v > palpha[x, y]:
            palpha[x, y] = v
            # Green only where the green-line altitudes are actually above the
            # horizon; red where the low emission is hidden by the Earth.
            t = (AUR_RED_ONLY_KM - low_km) / (AUR_RED_ONLY_KM - AUR_GREEN_SEEN_KM)
            t = max(0.0, min(1.0, t))
            phue[x, y] = tuple(int(r + (g - r) * t)
                               for r, g in zip(AURORA_RED, AURORA_GREEN))

    box = (PAN_X1 - PAN_X0, PAN_BASE - PAN_TOP)
    blur = ImageFilter.GaussianBlur(AUR_FIELD_BLUR)
    glow = hue.resize(box, Image.BILINEAR).filter(blur).convert("RGBA")
    glow.putalpha(alpha.resize(box, Image.BILINEAR).filter(blur))
    img.alpha_composite(glow, (PAN_X0, PAN_TOP))


def _draw_kp_forecast(draw, rows, top, f):
    """SWPC's three-day Kp outlook: is this building or fading.

    The obvious next question once the page has appeared at all, and the only
    part of it that speaks about nights other than tonight.
    """
    if not rows:
        return
    draw.text((MARGIN, top), "Kp forecast", font=f["med"], fill=WHITE)
    base = top + 70 + AUR_KP_H
    x0, x1 = MARGIN, PAN_X1
    span = (x1 - x0) / len(rows)
    bw = max(6, int(span) - 6)

    y_storm = base - (AUR_KP_STORM / AUR_KP_MAX) * AUR_KP_H
    draw.line([(x0, y_storm), (x1, y_storm)], fill=STEEL + (70,))
    draw.text((x1 + 6, y_storm - 14), "5", font=f["xs"], fill=MUTED)

    for i, (tag, kp) in enumerate(rows):
        bx = int(x0 + i * span)
        bh = int((min(kp, AUR_KP_MAX) / AUR_KP_MAX) * AUR_KP_H)
        draw.rectangle([bx, base - bh, bx + bw, base], fill=NOMINAL)
        # A day label at each midnight, so the bars carry dates without a
        # tick for every three-hour step.
        when = datetime.fromisoformat(tag)
        if when.hour == 0:
            draw.text((bx, base + 12), when.strftime("%a"), font=f["xs"], fill=MUTED)
    draw.line([(x0, base), (x1, base)], fill=STEEL, width=2)


def render_aurora(states, lat, lon):
    """Page 4: aurora, when there is any to be seen from here.

    Returns None unless the model puts aurora above this site's horizon AND it
    is dark enough to see it. Both gates matter and for opposite reasons: at
    temperate latitudes the page is absent almost always, while at high latitude
    the sky is busy but there is no astronomical night from May to August, so
    without the darkness gate a Reykjavik panel would carry an aurora page all
    summer for something nobody could possibly see.

    A page that appears when nothing can be seen is worse than no page at all.
    """
    if not AURORA_ENABLED or not inside_window(night_window(states)):
        return None
    data = aurora_now(lat or 0.0, lon or 0.0,
                      AURORA_EMISSION_KM, AURORA_THRESHOLD)
    if data is None:
        return None

    strongest, highest = data["strongest"], data["highest"]
    cloud = obscuration_of(states)

    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = _fonts()
    draw.text((MARGIN, 30), "AURORA", font=font("IBMPlexSans-Bold.ttf", 60), fill=WHITE)
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM, width=2)

    kp = f"   ·   Kp {data['kp']:.0f}" if data.get("kp") is not None else ""
    # NOT "chance overhead": OVATION's figure is the chance of aurora above each
    # MODEL POINT, and the strongest of those is routinely sitting on the
    # observer's horizon rather than over their head. Saying "overhead" here
    # would promise the one thing the number does not mean.
    draw.text((MARGIN, 160),
              f"Up to {strongest['probability']:.0f}% probability in view{kp}",
              font=f["sm"], fill=MUTED)
    draw.text((MARGIN, 210),
              f"{data['visible_cells']} model cells above the horizon from here.",
              font=f["xs"], fill=MUTED)

    # The same bearing-by-altitude plot page 2 uses, so "north and low" is said
    # by the axes rather than in words - and so it reads the same way at a
    # latitude where the answer is "overhead" or "south" instead.
    same = (abs(strongest["bearing"] - highest["bearing"]) < 0.5
            and abs(strongest["elevation"] - highest["elevation"]) < 0.5)
    marks = ([(strongest["bearing"], strongest["elevation"], "aurora", OBJECT, 9)]
             if same else
             [(strongest["bearing"], strongest["elevation"], "strongest", OBJECT, 9),
              (highest["bearing"], highest["elevation"], "best placed", OBJECT, 9)])
    # Storm first, axes and marks over it: the shape is the background the
    # numbers are annotations on, not the other way round.
    _draw_aurora_field(img, data.get("field") or [])
    _draw_panorama(draw, marks, "now", f["sm"], f["xs"])

    y = AUR_Y0
    for label, d in (("Strongest", strongest), ("Best placed", highest)):
        if same and label == "Best placed":
            continue
        draw.text((MARGIN, y), label, font=f["med"], fill=WHITE)
        draw.text((MARGIN, y + AUR_GAP),
                  f"{d['probability']:.0f}%  ·  {compass(d['bearing'])} "
                  f"{int(round(d['bearing'])) % 360}°  ·  {d['elevation']:.0f}° up  ·  "
                  f"{d['distance_km']:.0f} km away",
                  font=f["sm"], fill=MUTED)
        y += AUR_GAP * 2 + 20

    # Neither heading explains itself to somebody seeing the page for the first
    # time, and they are the two numbers the page exists to give.
    if not same:
        draw.text((MARGIN, y - 10),
                  "Strongest is the brightest patch in view; best placed is the "
                  "one highest",
                  font=f["fn"], fill=DIM)
        draw.text((MARGIN, y + 32), "above your horizon.", font=f["fn"], fill=DIM)
        y += 60

    # What the local sky is doing about it. A forecast the observer cannot act
    # on because it is overcast is worth saying out loud rather than leaving
    # them to look up and find out.
    sky = ("Your sky is clear." if cloud <= 20
           else f"Your sky is {cloud}% obscured." if cloud < 80
           else f"Your sky is {cloud}% obscured - almost certainly not visible from here.")
    draw.text((MARGIN, y + 20), sky, font=f["sm"], fill=MUTED)

    _draw_kp_forecast(draw, data.get("kp_forecast") or [], y + 130, f)

    when = (data.get("forecast_at") or "").replace("T", " ").rstrip("Z")
    draw.text((MARGIN, H - 156),
              "The figure is the chance of aurora above a model point, not a sighting.",
              font=f["fn"], fill=DIM)
    draw.text((MARGIN, H - 100),
              f"OVATION forecast for {when} UTC",
              font=f["fn"], fill=DIM)
    draw.text((MARGIN, H - 44),
              "Aurora model: NOAA Space Weather Prediction Center",
              font=f["fn"], fill=DIM)
    return img


# ── Page 5: satellite passes ──────────────────────────────────────────────
# How far ahead a pass may be and still earn the page. A pass is a scheduled
# event rather than a condition, so unlike aurora this page does NOT require the
# sky to be dark right now - the whole point is to say when to go out, which is
# information worth having at nine in the evening for an event at five in the
# morning. Beyond a day it stops being actionable and becomes a timetable.
SAT_HORIZON_HOURS = 24
SAT_ENABLED = True
# How far the listing below the plot reaches. Longer than the gate on purpose:
# whether the page EXISTS is a question about acting tonight, while the list is
# a schedule, and passes come in runs over several days rather than singly. One
# walk answers both - the page appears when the soonest pass is imminent, and
# once it is there it shows the run it belongs to.
#
# ⚠ AND IT STOPS AT A WEEK FOR A REASON. Pass times come from orbital elements
# that age, and the station manoeuvres; quoting a minute a fortnight out would
# state a precision the elements do not carry. A week is already the edge of it.
SAT_SCHEDULE_HOURS = 168
SAT_ROWS = 8
SAT_Y0, SAT_ROW_H = 900, 80
# The sky line follows the listing, but may not be pushed past this: a full list
# would otherwise walk it into the footer.
SAT_SKY_MAX_Y = 1660


# ⚠ PIL ANTIALIASES NEITHER LINES NOR ELLIPSES, so the track is drawn large and
# reduced. Two things about how, both established by measuring rather than by
# looking, after two wrong attempts:
#
# 1. REDUCE AN "L" MASK, NOT RGBA. Resizing RGBA interpolates the colour
#    channels independently of alpha, so the RGB of the fully transparent pixels
#    - black - bleeds into every edge pixel. On this page the sky behind the arc
#    is nearly black, so that was measured to be INVISIBLE here: zero pixels
#    darker than the local background in any version. It is kept because it is
#    the correct form and would show plainly over the lunar photo or a DSS2
#    cutout. _draw_aurora_field resizes hue and alpha separately for this reason.
#
# 2. THE FACTOR SETS THE NUMBER OF GRADATIONS, AND IT IS A SQUARE. An exact area
#    average yields only ss*ss + 1 coverage levels. At 4 that is 17, which
#    measured COARSER than the LANCZOS attempt it replaced (96) - the right
#    method producing a banded result. 8 gives 67, past what the panel resolves.
#    114 ms per draw on the Pi 5, on the data thread, once per refresh.
#
# BOX is the exact area average at an integer factor. LANCZOS was NOT rejected
# for ringing - that was claimed and disproved; it is simply the wrong tool for
# reducing a coverage mask by a whole number.
TRACK_SS = 8
TRACK_WIDTH = 3
TRACK_DOT_R = 7
# Room for the dot and the line's half-width at the plot's edges, where a pass
# rises and sets exactly on the baseline.
TRACK_PAD = 12


def _composite_aa(img, origin, size, colour, paint):
    """Draw at TRACK_SS scale into a mask, reduce it, and composite in one colour.

    `paint` receives a Draw over the oversized mask and the scale factor. One
    colour per call because a single mask carries coverage and nothing else -
    which is the whole point, since only alpha may be interpolated.
    """
    w, h = size
    mask = Image.new("L", (w * TRACK_SS, h * TRACK_SS), 0)
    paint(ImageDraw.Draw(mask), TRACK_SS)
    layer = Image.new("RGBA", size, colour)
    layer.putalpha(mask.resize(size, Image.BOX))
    img.alpha_composite(layer, origin)


def _draw_pass_track(img, track, colour):
    """The pass's own path across the bearing-by-altitude plot.

    ⚠ NORTH IS AT BOTH ENDS OF THE AXIS, so a pass crossing north is two
    polylines rather than one. Joining those samples directly would draw a line
    straight back across the whole plot - the same wrap that the aurora band had
    to be split for. The break is detected on the azimuth step rather than on the
    bearing's sign, because a pass can cross north in either direction.
    """
    if len(track) < 2:
        return
    size = (PAN_X1 - PAN_X0 + 2 * TRACK_PAD, PAN_BASE - PAN_TOP + 2 * TRACK_PAD)
    origin = (PAN_X0 - TRACK_PAD, PAN_TOP - TRACK_PAD)

    def point(az, alt, ss):
        """Plot coordinates on the oversized mask, relative to its corner."""
        x = TRACK_PAD + (az / 360.0) * (PAN_X1 - PAN_X0)
        y = TRACK_PAD + (PAN_BASE - PAN_TOP) * (
            1.0 - min(alt, PAN_ALT_MAX) / PAN_ALT_MAX)
        return (x * ss, y * ss)

    def paint_line(ld, ss):
        run = []
        for az, alt in track:
            if run and abs(az - run[-1][0]) > 180.0:
                if len(run) > 1:
                    ld.line([p[1] for p in run], fill=255,
                            width=TRACK_WIDTH * ss, joint="curve")
                run = []
            run.append((az, point(az, alt, ss)))
        if len(run) > 1:
            ld.line([p[1] for p in run], fill=255,
                    width=TRACK_WIDTH * ss, joint="curve")

    def paint_dot(ld, ss):
        px, py = point(*max(track, key=lambda p: p[1]), ss)
        r = TRACK_DOT_R * ss
        ld.ellipse([px - r, py - r, px + r, py + r], fill=255)

    _composite_aa(img, origin, size, colour, paint_line)
    # The culmination, marked but NOT labelled. _draw_panorama's labels avoid
    # each other and know nothing about this track, so a name placed here landed
    # squarely across the descending limb. The heading above the plot already
    # names the object and states the bearing, so a label here would be
    # duplication that damages the one thing the plot is for. Composited
    # separately because it is a different colour from the line.
    _composite_aa(img, origin, size, WHITE, paint_dot)


def _until(when, now):
    """"in 6h 33m" for a future time, or "now" once it has started."""
    secs = (when - now).total_seconds()
    if secs <= 0:
        return "now"
    h, m = int(secs // 3600), int((secs % 3600) // 60)
    return f"in {h}h {m:02d}m" if h else f"in {m} min"


def render_satellites(states, lat, lon):
    """Page 5: the next bright satellite pass, when there is one worth going out for.

    Returns None unless a pass clears every gate in core.satellites within the
    next day. That module decides visibility; this one decides only whether the
    result is worth a page, which is the same division the meteor page uses.

    ⇒ THE PATH IS THE POINT, and it is why this is a page rather than a line of
    text. A pass is the one man-made thing the display can plot honestly - the
    object really is at those bearings and those altitudes at those minutes - and
    the panorama is already a bearing-by-altitude instrument, so the track needs
    no axes of its own.
    """
    if not SAT_ENABLED:
        return None
    # ONE walk for both answers: the soonest pass decides whether there is a
    # page, the rest become the schedule under the plot.
    found = passes(lat or 0.0, lon or 0.0, hours=SAT_SCHEDULE_HOURS, with_track=True)
    if not found:
        return None

    nxt = found[0]
    now = datetime.now().astimezone()
    if nxt["culminate"] - now > timedelta(hours=SAT_HORIZON_HOURS):
        return None
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = _fonts()

    draw.text((MARGIN, 30), "SATELLITES", font=font("IBMPlexSans-Bold.ttf", 60),
              fill=WHITE)
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM, width=2)

    # The weekday only when the pass is not today. A bare time reads as tonight,
    # and at 22:30 a pass at 04:56 is not.
    day = "" if nxt["culminate"].date() == now.date() else f"{nxt['culminate']:%a} "
    draw.text((MARGIN, 160),
              f"{nxt['name']}  ·  {day}{nxt['culminate']:%H:%M}  ·  "
              f"{_until(nxt['culminate'], now)}",
              font=f["sm"], fill=WHITE)
    draw.text((MARGIN, 210),
              f"Rises {compass(nxt['rise_bearing'])}, highest {nxt['max_altitude']:.0f}° "
              f"in the {compass(nxt['culminate_bearing'])} at "
              f"{int(round(nxt['culminate_bearing'])) % 360}°, "
              f"sets {compass(nxt['set_bearing'])}",
              font=f["xs"], fill=MUTED)
    draw.text((MARGIN, 258),
              f"{nxt['duration_min']:.0f} minutes in view  ·  {nxt['range_km']:.0f} km away "
              f"at its highest",
              font=f["xs"], fill=MUTED)

    # Track first, then the axes over it, matching the aurora page: the path is
    # the background its numbers annotate. No marks are passed - the track draws
    # its own culmination dot, and see _draw_pass_track for why it is unlabelled.
    _draw_pass_track(img, nxt.get("track") or [], NOMINAL)
    _draw_panorama(draw, [], "pass", f["sm"], f["xs"])

    # The FIRST pass is the heading above, so the list starts after it. Printed
    # in full it duplicated the headline on every render - the same fault the
    # meteor page's footer had, where "Next peak" repeated the first row of its
    # own list. The heading is suppressed with the list rather than left
    # standing over nothing.
    later = found[1:SAT_ROWS + 1]
    if later:
        y = SAT_Y0
        # "Over the next week", not "later this week": the listing runs a week
        # forward from now, so on a Wednesday it reaches the following Wednesday
        # and "this week" is simply untrue of the last rows.
        draw.text((MARGIN, y), "Over the next week", font=f["med"], fill=WHITE)
        y += 70
        for p in later:
            # The DATE as well as the weekday. A week's listing can contain the
            # same weekday as today - it did on the first render, where two rows
            # read "Wed" on a Wednesday and looked like they meant tonight.
            draw.text((MARGIN, y), f"{p['culminate']:%a %d  %H:%M}", font=f["sm"],
                      fill=WHITE)
            draw.text((MARGIN + 280, y), p["name"], font=f["sm"], fill=MUTED)
            draw.text((MARGIN + 500, y),
                      f"{p['max_altitude']:.0f}° up  ·  {compass(p['rise_bearing'])} to "
                      f"{compass(p['set_bearing'])}",
                      font=f["sm"], fill=MUTED)
            y += SAT_ROW_H
    else:
        y = SAT_Y0

    # What the local sky is doing about it, as the aurora page does: a pass the
    # observer cannot see because it is overcast is worth saying rather than
    # leaving them to go outside and find out. Pinned rather than following the
    # list, so a short list cannot walk this line into the footer.
    cloud = obscuration_of(states)
    sky = ("Your sky is clear." if cloud <= 20
           else f"Your sky is {cloud}% obscured." if cloud < 80
           else f"Your sky is {cloud}% obscured - almost certainly not visible from here.")
    draw.text((MARGIN, min(y + 40, SAT_SKY_MAX_Y)), sky, font=f["sm"], fill=MUTED)

    # ⇒ NO BRIGHTNESS IS CLAIMED ANYWHERE ON THIS PAGE. Apparent magnitude
    # depends on which face the station has turned towards the observer, and
    # nothing keyless reports its attitude, so the page gives the geometry it
    # actually knows and leaves brightness alone.
    draw.text((MARGIN, H - 156),
              "Sunlit satellite in a dark sky. Times are predicted from orbital "
              "elements.",
              font=f["fn"], fill=DIM)
    draw.text((MARGIN, H - 100),
              f"Elements: CelesTrak, {elements_age()}",
              font=f["fn"], fill=DIM)
    draw.text((MARGIN, H - 44),
              "Positions computed for this site; brightness is not predicted.",
              font=f["fn"], fill=DIM)
    return img


# ── Page 6: the Sun ───────────────────────────────────────────────────────
# ⇒ THE FIRST PAGE GATED ON DAYLIGHT. Every other conditional page here exists
# only while it is dark, because aurora and meteors are conditions of the night
# sky and a page about either is worthless at noon. The Sun inverts that
# exactly, and it fills the hours in which the rest of the panel has least to
# say - so this is a departure from the "absent unless firing" pattern rather
# than an instance of it. What makes the departure honest is that the subject is
# genuinely always there: a quiet Sun is a fact about today, not an empty page.
SOLAR_ENABLED = True

# How close an eclipse has to be before it takes the top of the page. Outside
# this it is still stated, as one line in the footer, because the next partial
# visible from 51.4N is in August 2027 and an event mentioned only on the day is
# one nobody knew was coming. Inside it the eclipse displaces the activity
# figures, which is the point: those are the same every day and this is not.
SOL_ECLIPSE_BAND_HOURS = 24.0

# The row pitch was 132 with three rows. The permanent CME row makes four, and
# at that pitch the disc's two caption lines ran into the footer block with no
# gap between them - so the pitch pays for the row rather than the page losing
# the separation that tells a reader where one block ends.
SOL_ROW_H, SOL_VALUE_DY = 120, 58

# ⇒ THE GRAPHIC GOES ABOVE THE DETAIL, WHICH IS WHAT EVERY OTHER PAGE DOES. The
# Moon disc is centred at MOON_CY and its facts sit under it; the aurora field
# and the satellite track are drawn over the top half with their text blocks
# starting at 900. This page shipped inverted - four rows of text and then a
# disc below them - and was the only one that read that way.
#
# The preferred centre is MOON_CY itself, so the Sun lands where the Moon lands
# and the two cards agree at a glance. It moves DOWN only when the header block
# above it needs the room, which is the eclipse state.
SOL_DISC_CY = MOON_CY
SOL_HEAD_BOTTOM = 340       # bottom of the verdict block, ordinary state
SOL_BAND_BOTTOM = 740       # bottom of the eclipse band, including its rule
SOL_ROWS_GAP = 70           # caption bottom -> first row label

# ⇒ THE SAME RADIUS AS THE MOON CARD, AND THAT IS NOT A MATTER OF TASTE. The Sun
# and the Moon subtend almost exactly the same half-degree from Earth - the
# near-equality that makes eclipses possible at all - so two discs drawn at one
# scale are in true proportion to each other, and drawing the Sun larger than
# the Moon would state something false about both. MOON_R is 300; so is this.
#
# Both are still enormously exaggerated against the sky layer's 21.3 px per
# degree, where half a degree is about 11 px. That is the documented bargain
# behind the Moon card: at this size it is a card and not sky-layer content, and
# it makes no positional claim. The Sun inherits the same standing.
#
# SOL_SPOT_SCALE below is an exaggeration factor, not a measurement, and applies
# only to the drawn fallback: at true scale a 120-millionths group is about
# 3 px across here. The photograph needs none of it.
SOL_DISC_R = 300
SOL_SPOT_MIN, SOL_SPOT_MAX, SOL_SPOT_SCALE = 9, 30, 6.0


def _solar_verdict(peak_class):
    """One word for the day's flare activity, from the day's strongest flare.

    Derived from a single stated quantity and printed beside it, so the word can
    be checked against the figure rather than standing on its own. A label
    making a claim about activity that is not computed from the activity is the
    fault the meteor page's "peaking now" had, where a claim about a RATE was
    measured in time.
    """
    return {"X": "SEVERE", "M": "ACTIVE", "C": "MODERATE"}.get(
        (peak_class or " ")[0], "QUIET")


def _eclipse_line(eclipse):
    """The always-present footer statement about the next eclipse."""
    if not eclipse:
        return "No solar eclipse is visible from here in the next two years."
    return (f"Next eclipse here: {eclipse['maximum']:%-d %b %Y}, "
            f"{eclipse['magnitude'] * 100:.0f}% of the Sun's diameter covered.")


def _draw_eclipse_band(draw, eclipse, now, f):
    """The eclipse at the top of the page, and where the rest may start.

    ⚠ NO WORDING HERE MAY READ AS AN INSTRUCTION TO LOOK AT THE SUN, and the
    filter caveat is attached to the figures rather than footnoted - which is
    why it is drawn here and not with the other footer lines. In the ordinary
    state there is no figure for it to attach to and it sits in the footer
    instead; the placement follows what it qualifies.

    ⚠ MAGNITUDE AND OBSCURATION ARE BOTH PRINTED AND BOTH NAMED. Magnitude is
    the fraction of the solar DIAMETER covered and obscuration the fraction of
    its AREA; they read 0.94 and 0.90 at the same event. Printing either under
    the other's label is the ZHR-versus-observed-rate error in a new place.
    """
    started = eclipse["begins"] <= now <= (eclipse["ends"] or now)
    heading = "PARTIAL ECLIPSE IN PROGRESS" if started else "PARTIAL ECLIPSE"
    draw.text((MARGIN, 150), heading, font=font("IBMPlexSans-Bold.ttf", 66),
              fill=WHITE)

    # The countdown counts to the MAXIMUM once the eclipse has begun and to the
    # first contact before it. Counting to a start that has passed reads as an
    # event that has not happened yet.
    #
    # ⇒ THE RELATIVE LINE NAMES NO CLOCK TIME AND THE ABSOLUTE LINE NO INTERVAL.
    # Both carried "begins 09:02" on the first render, one under the other - the
    # same duplication the meteors footer and the satellite listing each had,
    # where a headline repeated the first row beneath it. Split by KIND, the two
    # lines answer different questions.
    target, label = ((eclipse["maximum"], "Maximum") if started
                     else (eclipse["begins"], "Starts"))
    draw.text((MARGIN, 250), f"{label} {_until(target, now)}",
              font=f["med"], fill=WHITE)
    day = "" if eclipse["maximum"].date() == now.date() \
        else f"{eclipse['maximum']:%a %-d %b}  ·  "
    times = (f"{day}begins {eclipse['begins']:%H:%M}  ·  "
             f"maximum {eclipse['maximum']:%H:%M}")
    if eclipse["ends"]:
        times += f"  ·  ends {eclipse['ends']:%H:%M}"
    draw.text((MARGIN, 320), times, font=f["sm"], fill=MUTED)

    draw.text((MARGIN, 420),
              f"{eclipse['magnitude'] * 100:.0f}% of the Sun's diameter is "
              f"covered at maximum",
              font=f["sm"], fill=WHITE)
    draw.text((MARGIN, 476),
              f"{eclipse['obscuration'] * 100:.0f}% of its disc area  ·  "
              f"Sun {eclipse['sun_altitude']:.0f}° above the horizon",
              font=f["sm"], fill=MUTED)

    # Attached to the figures above, deliberately. This is the one line on the
    # page that must not be missed by somebody who read the percentage.
    draw.text((MARGIN, 566),
              "Safe to read about, not to look at: the Sun needs a certified",
              font=f["sm"], fill=WHITE)
    draw.text((MARGIN, 616),
              "solar filter at every stage of a partial eclipse.",
              font=f["sm"], fill=WHITE)
    draw.line([(MARGIN, 700), (W - MARGIN, 700)], fill=DIM, width=2)
    return SOL_BAND_BOTTOM


def _draw_activity_head(draw, data, f):
    """The ordinary state: a verdict, and the figure it was derived from."""
    xray = data.get("xray") or {}
    draw.text((MARGIN, 150), _solar_verdict(xray.get("peak_class")),
              font=font("IBMPlexSans-Bold.ttf", 110), fill=WHITE)
    # ⇒ THE WORD ABOVE IS DERIVED FROM THIS LINE, so the two are drawn together
    # and this line is the ONLY place the flare figures appear. Printed here and
    # again as a row, they read as two measurements that happen to agree.
    #
    # Kept to one line that fits: the first render ran off the right edge at
    # "the level now is B3.8" and lost the figure the sentence existed to give.
    if xray.get("peak_class"):
        draw.text((MARGIN, 290),
                  f"Strongest flare in the last day {xray['peak_class']}  ·  "
                  f"{xray['latest_class']} now",
                  font=f["sm"], fill=MUTED)
    else:
        draw.text((MARGIN, 290), "No flare measurement is available.",
                  font=f["sm"], fill=MUTED)
    return SOL_HEAD_BOTTOM


def _solar_rows(data, compact):
    """[(label, value)] for the activity block, skipping what did not arrive.

    Each feed is independent and one failing costs its own row rather than the
    page - which is also why the CME row is absent on most days: no CME is
    modelled to arrive within the lookahead, and that is the normal case rather
    than a fault.
    """
    regions = data.get("regions") or {}
    cme = data.get("cme") or {}
    rows = []
    if regions:
        largest = f"  ·  largest group {regions['largest']}" \
            if regions.get("largest") else ""
        rows.append(("Sunspots",
                     f"{regions['regions']} regions  ·  {regions['spots']} spots"
                     f"{largest}"))
    # ⇒ THE CME ROW IS ALWAYS PRESENT, because its normal state is absence and an
    # absent row cannot say so. Left conditional, the page said nothing at all
    # about CMEs on the great majority of days, and a reader could not tell "none
    # coming" from "not looked at" - the same reasoning that put a permanent
    # eclipse line in the footer. A failed fetch says so rather than reporting
    # calm it never established.
    if cme:
        # The repo genuinely holds both conventions - core.satellites returns
        # aware datetimes while anything that has been through the disk cache
        # returns ISO strings - so which one arrives depends on the caller, and
        # assuming either is how the satellite page crashed on first render.
        arrival = cme["arrival"]
        if isinstance(arrival, str):
            arrival = datetime.fromisoformat(arrival)
        arrival = arrival.astimezone()
        kp = f"  ·  Kp {cme['kp']:.0f} predicted" if cme.get("kp") else ""
        rows.append(("Coronal mass ejection",
                     f"{'Glancing blow' if cme.get('glancing') else 'Direct hit'} "
                     f"expected {arrival:%a %H:%M}{kp}"))
    elif compact:
        # An eclipse is on the page and the space is the eclipse's. "No CME" is
        # worth a line on an ordinary day and not worth one today.
        pass
    elif "cme" in (data.get("unavailable") or []):
        rows.append(("Coronal mass ejection", "Model runs are unavailable."))
    else:
        rows.append(("Coronal mass ejection",
                     f"None modelled to reach Earth in the next "
                     f"{CME_LOOKAHEAD_DAYS} days."))
    if compact:
        return rows
    # ⇒ THE LABEL NAMES THE CLASSES BECAUSE THE FORECAST ONLY COVERS THEM. SWPC
    # publishes c/m/x_flare_probability and nothing for A or B, which is not an
    # omission: A and B flares are the continuous background, so their
    # probability would sit near 100% and say nothing. C is the conventional
    # threshold for a forecastable event.
    #
    # Note the division this creates with the heading above, which reports the
    # MEASURED strongest flare and today reads B7.4. Measured includes A and B;
    # forecast never does. "Chance of a flare" over three letters that exclude
    # the class printed two lines up invites exactly the question it should
    # answer.
    if regions and regions.get("forecast_issued"):
        rows.append(("Chance of a C, M or X flare today",
                     f"C {regions['c_probability']}%     "
                     f"M {regions['m_probability']}%     "
                     f"X {regions['x_probability']}%"))
    elif regions:
        # NOT "C 0%". The day's region list is published before the forecast is
        # attached, and in that window every probability reads zero - which as a
        # printed forecast asserts near-certainty of a quiet Sun at the one
        # moment nobody has forecast anything.
        rows.append(("Chance of a C, M or X flare today",
                     "Today's forecast has not been issued yet."))
    # No flare row: the heading above already states the day's strongest and the
    # current level, and that line is what the verdict word is derived from.
    if data.get("f107"):
        rows.append(("Radio flux", f"F10.7 = {data['f107']:.0f}"))
    return rows


def _draw_solar_photo(img, draw, photo, observed, y, f):
    """The photographed disc, which is the preferred drawing and the honest one.

    ⇒ A PHOTOGRAPH HAS NO POSITION LAG, AND THE DRAWN DISC DID. Marks plotted
    from SWPC's regional report sat consistently east of the real spots, because
    that report is a daily snapshot while rotation carries a group about 13.2
    degrees a day. The frame shows the spots where they were at its own
    timestamp, so there is no rotation arithmetic to get wrong and no enlarged
    mark to apologise for - the spots are simply in the picture, at their real
    size.
    """
    cx, r = W // 2, SOL_DISC_R
    paste_sun(img, photo, cx, y, r)
    # ⇒ "SUNSPOTS", NOT "SPOT GROUPS", AND THAT WAS MEASURED RATHER THAN JUDGED.
    # SWPC counts both regions and the spots inside them, so the caption can only
    # be right about one. Labelling the dark blobs in the frame: 11 to 21 of them
    # depending on threshold, merging to 4-5 clusters, against SWPC's 7 regions
    # and 22 spots on the same day. The blob count tracks the SPOT count, so what
    # is resolved here is individual spots - several close enough to read as one
    # patch - and the groups are the clusters they form, which the row above
    # already counts.
    #
    # ⇒ THE COLOUR IS SAID TO BE SDO'S, NOT THE SUN'S. The orange is a colour
    # table applied to continuum intensity - the same measurement is published as
    # a grey frame - and from space the Sun is white. "White light" names the
    # technique and leaves the picture asserting a colour the Sun does not have.
    # Stated flatly and left there: the claim needs no argument attached, and one
    # line costs the page less than two.
    draw.text((MARGIN, y + r + 40),
              f"SDO/HMI white light, {observed:%H:%M} UTC. Colour is SDO's own; "
              f"the dark marks are sunspots.",
              font=f["fn"], fill=DIM)
    return y + r + 80


def _draw_solar_disc(draw, groups, y, f, now=None):
    """The Sun's disc drawn, for when no photograph could be fetched.

    ⚠ THE POSITIONS BEHIND THIS ARE UP TO A DAY STALE and it is the reason the
    photograph is preferred. SWPC's regional report is a daily snapshot, and
    solar rotation carries a group about 13.2 degrees a day - measured against
    an SDO frame, every mark sat east of its real spot by roughly the report's
    age. Nothing here corrects for that: this path exists so the page still
    shows the disc when the network is down, and at that point stating roughly
    where the groups were is better than an empty page. The caption says the
    positions are as reported rather than as they now are.

    ⇒ THE MARK SIZES ARE NOT REAL EITHER. A group of 120 millionths of the
    hemisphere is about 3 px across at this radius, so the marks are floored at
    a legible size - the same bargain the Moon card makes, stated on the page.

    Far-side positions are dropped rather than folded onto the visible half. A
    region that has rotated over the west limb is genuinely not in view, and the
    projection alone would put it back on the wrong edge.
    """
    cx, r = W // 2, SOL_DISC_R
    draw.ellipse([cx - r, y - r, cx + r, y + r], outline=MUTED, width=3)

    b0 = solar_b0(now)
    # The equator, which is what makes the tilt visible rather than merely
    # applied: at +7 degrees the line bows below centre and the disc reads as a
    # sphere seen slightly from above.
    equator = [(cx + x * r, y + ey * r)
               for x, ey, front in
               (project_spot(0.0, lo, b0) for lo in range(-90, 91, 5))
               if front]
    if len(equator) > 1:
        draw.line(equator, fill=DIM, width=2)

    # The limbs are labelled because the orientation is a convention rather than
    # anything the picture shows: solar west is to the right, which is the way
    # rotation carries a group and the way every published solar image is drawn.
    # Unlabelled, a mirrored disc looks exactly like a correct one.
    draw.text((cx - r - 34, y - 15), "E", font=f["fn"], fill=DIM)
    draw.text((cx + r + 14, y - 15), "W", font=f["fn"], fill=DIM)

    drawn = 0
    for g in groups:
        if g.get("latitude") is None:
            continue
        x, ey, front = project_spot(g["latitude"], g["longitude"], b0)
        if not front:
            continue
        # Area sets the mark size, floored so the smallest group is still
        # visible and capped so the largest cannot swallow its neighbours.
        rr = max(SOL_SPOT_MIN, min(SOL_SPOT_MAX,
                                   r * math.sqrt(max(g["area"], 1) / 1e6) * SOL_SPOT_SCALE))
        px, py = cx + x * r, y + ey * r
        draw.ellipse([px - rr, py - rr, px + rr, py + rr], fill=BG, outline=WHITE,
                     width=2)
        drawn += 1

    draw.text((MARGIN, y + r + 40),
              f"{drawn} spot group{'' if drawn == 1 else 's'}, as last reported "
              f"rather than as they now are.",
              font=f["fn"], fill=DIM)
    draw.text((MARGIN, y + r + 84),
              "Marks are enlarged to be visible; real spots are far smaller.",
              font=f["fn"], fill=DIM)
    return y + r + 124


def render_solar(states, lat, lon, now=None):
    """Page 6: what the Sun is doing, while the Sun is up.

    Returns None after sunset, which is the whole gate - see the note on
    SOLAR_ENABLED for why this page departs from the "absent unless firing"
    rule the others follow.

    ⇒ THE ECLIPSE SURVIVES A NETWORK FAILURE AND THE ACTIVITY DOES NOT. Every
    figure on this page but the eclipse comes from a feed; the eclipse is
    computed from ephem alone. So a page with no data at all is still drawn when
    there is an eclipse to announce, and that is the only thing on this display
    that can be said with the internet down.

    `now` moves the whole page together - the gate, the eclipse search and the
    countdown all take it - so a preview of the eclipse states is a page a user
    could really have rather than one instant dressed in another's clock. The
    daemon never passes it.
    """
    now = now or datetime.now().astimezone()
    if not SOLAR_ENABLED or not sun_up(lat or 0.0, lon or 0.0, now=now):
        return None
    data = solar_activity() or {}
    eclipse = next_eclipse(lat or 0.0, lon or 0.0, now=now)
    if not data and not eclipse:
        return None

    # In the band when the eclipse is close enough to be worth the top of the
    # page, and while it is actually running.
    imminent = bool(eclipse
                    and eclipse["begins"] - now
                    <= timedelta(hours=SOL_ECLIPSE_BAND_HOURS)
                    and (eclipse["ends"] or eclipse["maximum"]) >= now)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f = _fonts()
    draw.text((MARGIN, 30), "SOLAR", font=font("IBMPlexSans-Bold.ttf", 60),
              fill=WHITE)
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM, width=2)

    y = (_draw_eclipse_band(draw, eclipse, now, f) if imminent
         else _draw_activity_head(draw, data, f))

    # ⇒ DISC FIRST, ROWS UNDER IT - the order every other page uses, and the one
    # this page shipped inverted. The photograph is preferred and the drawing is
    # the fallback, because the frame carries no position lag and the drawn
    # marks do. Each returns the y below its own caption, so the rows are placed
    # from what was actually drawn rather than from a constant that has to be
    # kept in step with it.
    groups = (data.get("regions") or {}).get("groups") or []
    photo, observed = sun_image()
    if photo is not None or groups:
        cy = max(SOL_DISC_CY, y + SOL_DISC_R)
        y = (_draw_solar_photo(img, draw, photo, observed, cy, f)
             if photo is not None
             else _draw_solar_disc(draw, groups, cy, f, now=now))
        y += SOL_ROWS_GAP

    for label, value in _solar_rows(data, compact=imminent):
        draw.text((MARGIN, y), label, font=f["med"], fill=WHITE)
        draw.text((MARGIN, y + SOL_VALUE_DY), value, font=f["sm"], fill=MUTED)
        y += SOL_ROW_H

    if not data:
        draw.text((MARGIN, y), "Solar activity data is unavailable.",
                  font=f["sm"], fill=MUTED)
    # Credited only when the frame was actually used. Left unconditional, the
    # page would attribute a disc it had drawn itself to SDO, on precisely the
    # occasions SDO could not be reached.
    credit = ("CME arrival: NASA DONKI via CCMC  ·  disc: NASA SDO/HMI"
              if photo is not None else
              "CME arrival: NASA DONKI model runs, served by CCMC")

    # The eclipse line stays in the footer whenever the band is not up, however
    # far off the event is. It is the rarest thing this panel shows and the one
    # worth knowing about in advance.
    if not imminent:
        draw.text((MARGIN, H - 212), _eclipse_line(eclipse), font=f["xs"],
                  fill=DIM)
        # In this state no figure is being given that the caveat qualifies, so
        # it sits with the other standing notes rather than beside a number.
        draw.text((MARGIN, H - 156),
                  "The Sun is never safe to look at without a certified solar "
                  "filter.",
                  font=f["fn"], fill=DIM)
    else:
        draw.text((MARGIN, H - 156),
                  "Eclipse times and coverage are computed for this site.",
                  font=f["fn"], fill=DIM)
    draw.text((MARGIN, H - 100),
              "Spots, flares and radio flux: NOAA Space Weather Prediction Centre",
              font=f["fn"], fill=DIM)
    draw.text((MARGIN, H - 44), credit, font=f["fn"], fill=DIM)
    return img


def target_pages(states, targets, lat):
    """Every screenful of page 2, as a Paged run, or empty if there is nothing.

    All of them are rendered here because stepping between them happens on the
    render loop, which can afford neither a re-render nor the cutout fetches
    behind one. Cutouts are therefore fetched for the whole list, not the first
    screenful; they are cached on disk, so this is a one-off cost per object.
    """
    objects = targets.get("objects") or []
    n = max(1, -(-len(objects) // P2_CARDS))   # ceiling division
    images = load_cutouts(targets, len(objects) or P2_CARDS, CUTOUT_PX)
    out = Paged()
    for i in range(n):
        page = render_targets(states, targets, images, lat, LON, i * P2_CARDS)
        if page is None:      # no objects and no bodies: there is no page at all
            return Paged()
        out.append(page)
    return out


def build_pages(states, targets, lat, moon_ring=False):
    """Every page as an RGBA overlay. Data thread only: this fetches the hour's
    lunar frame and any deep-sky cutouts not already cached."""
    photo, facts = moon_image()
    pages = [render_conditions(states, photo, moon_ring, facts)]
    # The targets page joins the rotation only when there is something on it -
    # better one live page than two with a dead one. It carries every object
    # UpTonight passed rather than the first screenful, as a Paged run stepped
    # by its own button: the heading has always said "of 40" while showing six,
    # and naming what it is withholding is not the same as offering it.
    page2 = target_pages(states, targets, lat)
    if page2:
        pages.append(page2)
    page3 = render_meteors(states, lat, LON)
    if page3 is not None:
        pages.append(page3)
    # Aurora joins the rotation only when there is aurora to see, which is the
    # same mechanism pages 2 and 3 use - and the reason this page is independent
    # of UpTonight. Drawn on the targets panorama instead, a real storm could
    # have gone unshown because an unrelated data source had failed.
    page4 = render_aurora(states, lat, LON)
    if page4 is not None:
        pages.append(page4)
    # Same mechanism again: present only when a bright satellite crosses a dark
    # sky within the day. Unlike the pages above it this one is not gated on the
    # sky being dark NOW, because a pass is an appointment rather than a
    # condition - and it is the only page here whose subject is man-made.
    page5 = render_satellites(states, lat, LON)
    if page5 is not None:
        pages.append(page5)
    # The one page here that requires the Sun to be UP. It does not lengthen the
    # worst-case rotation: aurora needs darkness and cannot coexist with it, so
    # the count peaks at five either way - by night with aurora, by day with
    # this.
    page6 = render_solar(states, lat, LON)
    if page6 is not None:
        pages.append(page6)
    return pages


def compose(frame, overlay, labels=None):
    """Dashboard, clock and control strip over a painted sky frame.

    This puts the clouds BEHIND the moon disc, which looks wrong and is not.
    Cloud is a few kilometres up and the Moon is 384,000 km away, so in the sky
    cloud always crosses in front - but the disc here is a card, not a view.
    The sky layer runs about 21 px per degree on this panel, where the real Moon
    is roughly 11 px across; the card draws it near fifty times that, at a fixed
    place in the layout rather than where the Moon is. Cloud drifting across it
    would assert the Moon really is there, that big, in that direction, which is
    the class of claim the starfield and the meteor radiants were changed to
    stop making. Do not "fix" this by compositing the moon into the sky frame
    without also solving the size and the position.
    """
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
    parser.add_argument("--no-night", action="store_true",
                        help="Save in the daylight palette whatever the hour "
                             "(for documentation; the panel is unaffected)")
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
    global LIMITING_MAG, METEOR_COMPRESSION, REAL_STARS, CAMERA_AZ, CAMERA_ALT, CAMERA_FOV
    global AURORA_ENABLED, AURORA_THRESHOLD, AURORA_EMISSION_KM
    global SAT_ENABLED, SAT_HORIZON_HOURS
    global SOLAR_ENABLED, SOL_ECLIPSE_BAND_HOURS
    METEOR_COMPRESSION = float(disp.get("meteor_compression", METEOR_COMPRESSION))
    sol = config.get("solar", {})
    SOLAR_ENABLED = bool(sol.get("enabled", SOLAR_ENABLED))
    SOL_ECLIPSE_BAND_HOURS = float(
        sol.get("eclipse_band_hours", SOL_ECLIPSE_BAND_HOURS))
    sat = config.get("satellites", {})
    SAT_ENABLED = bool(sat.get("enabled", SAT_ENABLED))
    SAT_HORIZON_HOURS = float(sat.get("horizon_hours", SAT_HORIZON_HOURS))
    aur = config.get("aurora", {})
    AURORA_ENABLED = bool(aur.get("enabled", AURORA_ENABLED))
    AURORA_THRESHOLD = float(aur.get("threshold_percent", AURORA_THRESHOLD))
    AURORA_EMISSION_KM = float(aur.get("emission_km", AURORA_EMISSION_KM))
    skycfg = config.get("sky", {})
    REAL_STARS = bool(skycfg.get("real_stars", REAL_STARS))
    CAMERA_AZ  = float(skycfg.get("camera_azimuth", CAMERA_AZ))
    CAMERA_ALT = float(skycfg.get("camera_altitude", CAMERA_ALT))
    CAMERA_FOV = float(skycfg.get("field_of_view", CAMERA_FOV))
    LIMITING_MAG = float(skycfg.get("limiting_magnitude", LIMITING_MAG))
    # sky was constructed at import with the default field of view, and the
    # cloud drift converts degrees to pixels through its angular scale. A
    # configured field of view has to reach it or the clouds keep the default's
    # rate while everything else uses the configured one.
    sky.px_per_degree = px_per_degree(H, CAMERA_FOV)
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
        # --save normally applies night mode so a preview does not lie about
        # how the panel looks after dark. A screenshot documenting colour
        # wants the opposite, since red mode collapses everything to luma -
        # the aurora page in particular renders its emission-height colours
        # and night mode hides exactly what they are there to show.
        now_mode = "off" if args.no_night else night_mode_now(night, night_window(states))
        # Flattened: with no button and no rotation, a one-shot takes every
        # screenful of a paged page rather than only its first.
        frames = [compose(sky.paint(params, 1.7, [], 0.0), p)
                  for p in flatten(pages)]
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
    reader = (TouchReader(W, H, FB_W, FB_H, rotate_deg=ROTATE_DEG)
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
