#!/usr/bin/env python3
"""Stargazing conditions display for the Raspberry Pi Touch Display 2 (5", 720x1280).

Renders a 1280x720 landscape dashboard over a live, data-reactive animated night
sky (twinkling starfield + drift + meteors) and writes frames to the Linux
framebuffer (/dev/fb0, RGB565). Runs as a long-lived daemon; a background thread
refetches the AstroWeather conditions - computed here via pyastroweatherio, or
read from Home Assistant when weather.source says so - rereads UpTonight's
target reports, which are produced locally by a daily systemd timer, and fetches
the hour's real lunar image. Touch controls live in touch.py.

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

from core.daemon import Paged, flatten, install_signal_handlers, run_daemon
from core.fonts import font
from core.imagery import moon_image, paste_moon
from core.meteors import SPORADIC_ZHR, active, visible_rate
from core.night import (
    NIGHT_CYCLE,
    apply_night,
    night_mode_now,
    night_window,
    tonight,
)
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
from core.panel import PIL_ROTATION, Framebuffer, Strip
from core.positions import alt_az, next_rise, observer, plot_instant
from core.sky import Sky
from core.sky import sky_params as core_sky_params
from core.starfield import (
    SIZE_BANDS_SPARSE,
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

# No longer frozen - that ended at 3.7.2, and this build has taken real work
# since. What remains true is that its panel leaves the bench once the 10" one
# is running, after which nothing here can be confirmed against hardware again;
# the tag build5-hardware-verified marks the last state that was. Repo releases
# are versioned separately in pyproject.toml and will keep moving; the two were
# never going to line up.
FIRMWARE_VERSION = "3.29.0"

# The largest image this program legitimately opens is a 730x730 moon frame.
# PIL's default decompression-bomb threshold (~178M pixels) would let a hostile
# response balloon to a ~500MB decode before tripping - enough to OOM a 2GB Pi.
# Cap it far above anything real and far below anything dangerous.
Image.MAX_IMAGE_PIXELS = 3_000 * 3_000

CONFIG_PATH = Path(__file__).parent / "config.toml"
# Computing alt-az needs a longitude; the daemon only passes a latitude, so
# main() records both here.
LAT = None
LON = None
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Framebuffer geometry (Touch Display 2 native portrait). The landscape frame is
# rotated to this before packing to RGB565. Flip ROTATE if the panel is upside down.
FB_DEV = "/dev/fb0"
FB_W, FB_H = 720, 1280
ROTATE_DEG = 90
ROTATE = PIL_ROTATION[ROTATE_DEG]

W, H = 1280, 720

# ── Layout constants (1280x720 landscape) ─────────────────────────────────
MARGIN = 28
HLINE1 = 80                 # header bottom
HLINE2 = 252                # verdict bottom
HLINE3 = 548                # footer top
DIV_X  = 800                # vertical divider: conditions | moon
RIGHT_CX = (DIV_X + W) // 2  # centre of right (moon) panel = 1040

# Touch control strip. Hidden until the panel is tapped, because this is an
# ambient display and permanent on-screen buttons would cost content space on
# every one of the thousands of frames nobody is touching.
STRIP_H  = 64
STRIP_Y  = H - STRIP_H - 16
BTN_GAP  = 8

# Which way the window looks. The panel cannot know how it is oriented in the
# room, so this is chosen rather than detected: due south by default, because
# that is where everything transits from the northern hemisphere.
#
# 70 degrees vertical, not the 10" build's 90. The horizontal field follows from
# the aspect ratio, and on this landscape canvas 70 gives several hundred stars
# in view against the seeded field's 200.
#
# The old reason for preferring it - that 90 would stretch the sky further near
# the zenith - no longer applies: the projection is gnomonic, which has no pole
# to stretch around. What remains is that a wider field packs more sky into the
# same pixels, and gnomonic's own scale growth away from the axis is steeper the
# wider it is opened.
REAL_STARS = True
CAMERA_AZ, CAMERA_ALT, CAMERA_FOV = 180.0, 45.0, 70.0

# Faintest star drawn. The catalogue reaches 6.5; a suburban sky reaches about
# 5, so the difference is stars nobody standing at the panel could see.
#
# It is a legibility setting as much as an honesty one. Measured over this field
# of view, the full catalogue puts 1204 stars on the panel and 983 of them - 82%
# - are fainter than magnitude 5, carrying 56% of the lit area between them. The
# sixteen stars that make the sky recognisable as a real one were 1.3% of what
# was drawn, and the patterns were lost in the rest. At 5.0 about 224 remain.
#
# Configurable because it depends on the site's own light pollution, which the
# panel cannot know.
LIMITING_MAG = 5.0

# How often the real positions are recomputed. Nothing interpolates between
# refreshes - the whole field is swapped at once - so this interval is the size
# of the step the sky takes, and it is a coherent slide of the entire field
# rather than scattered motion, which is what makes a small one visible.
#
# 15 s here against 5 s on the 10.1" build, and the difference is both scale
# and headroom. This panel shows 70 degrees over 720 px, about 10.3 px/degree
# against 21.3, so the same 0.2507 degrees a minute moves the field less than
# half as far: 15 s already puts the step under a pixel. And this build's
# render loop is the saturated one - it settles near 14 fps with fps set to 20
# on a Pi 4 - so refreshing four times as often as it needs to would come
# straight off the frame rate.
STAR_REFRESH_S = 15

# Meteors are drawn at the real rate, sped up. Three an hour is honest and makes
# an animated sky look broken, so the panel runs them as though watching for this
# many minutes per minute. It scales what is there rather than manufacturing what
# is not, so a night with nothing falling still shows nothing.
METEOR_COMPRESSION = 20.0

# The engine, sized for this panel. `sky` is constructed exactly where the
# seeded starfield used to be generated, so the shared random stream is consumed
# in the same order - which still matters for the clouds and meteors even though
# the stars themselves are now replaced at startup. The daemon reads these three
# off this module as its layout.
sky = Sky(W, H, fov=CAMERA_FOV)
fb = Framebuffer(W, H, FB_W, FB_H, ROTATE, FB_DEV)
strip = Strip(W, MARGIN, STRIP_Y, STRIP_H, BTN_GAP)

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

def _draw_moon(draw, cx, cy, r, illumination, waxing=True):
    """Draw moon phase using parametric geometry."""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=MOON_DARK, outline=MOON, width=3)

    if illumination < 1:
        return  # new moon -- dark circle only

    if illumination > 99:
        draw.ellipse([cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3], fill=MOON)
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

    draw.polygon(pts, fill=MOON)


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
        draw.ellipse([cx - r, cy - r * 0.45, cx + r, cy + r * 0.45], outline=OBJECT, width=2)
        draw.ellipse([cx - r * 0.28, cy - r * 0.16, cx + r * 0.28, cy + r * 0.16], fill=OBJECT)
    else:                                            # nebulae and everything else
        draw.ellipse([cx - r, cy - r * 0.8, cx + r, cy + r * 0.8], outline=OBJECT)
        draw.ellipse([cx - r * 0.6, cy - r * 0.45, cx + r * 0.6, cy + r * 0.45], outline=STEEL)


def render_foreground(states, moon_photo=None, moon_ring=False):
    """Render the dashboard as an RGBA overlay: opaque content, transparent sky.

    moon_photo is a Dial-a-Moon frame fetched by the caller (network, so never
    from the render loop); without one the phase is drawn parametrically.
    """
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    f_large = font("IBMPlexSans-Bold.ttf", 104)
    f_med   = font("IBMPlexSans-SemiBold.ttf", 46)
    f_sm    = font("IBMPlexSans-Regular.ttf", 32)
    f_xs    = font("IBMPlexSans-Regular.ttf", 26)

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
    draw.text((MARGIN, 18), "STARGAZING", fill=WHITE, font=f_med)
    # The clock is NOT drawn here: this overlay is cached between data refreshes,
    # so a timestamp baked in would sit frozen for refresh_min. See draw_clock().
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM, width=2)

    # ── Verdict ───────────────────────────────────────────────────────
    if no_dark:
        v_text = "NO DARK SKY"
        v_sub  = f"Next dark night: {next_dark.strftime('%d %b') if next_dark else 'unknown'}"
    else:
        v_text = verdict(dsky_today)
        v_sub = f"Deep sky: {dsky_today}%  -  {dsky_today_desc}"

    # Measured, not guessed: at (MARGIN, 92) the verdict's ink already started
    # at x 28, exactly level with the title and the subtitle - so there was no
    # metric misalignment to fix. What there is is an optical one: 104px bold
    # reads as indented beside 32px regular even when the stems are flush, so
    # it gets a small pull left. Vertically it sat 46px below the rule and only
    # 12px above the subtitle; 74 evens that to 28 above and 30 below.
    draw.text((MARGIN - 4, 74), v_text, fill=NOMINAL, font=f_large)
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
            draw.text((LP_CX - big_w // 2, 300), big_text, fill=NOMINAL, font=f_large)
            sub_w = int(draw.textlength(sub_text, font=f_sm))
            draw.text((LP_CX - sub_w // 2, 410), sub_text, fill=WHITE, font=f_sm)
            dt_text = next_dark.strftime("%d %b %Y")
            dt_w = int(draw.textlength(dt_text, font=f_xs))
            draw.text((LP_CX - dt_w // 2, 452), dt_text, fill=NOMINAL, font=f_xs)
        else:
            msg = "No dark sky"
            msg_w = int(draw.textlength(msg, font=f_med))
            draw.text((LP_CX - msg_w // 2, 380), msg, fill=NOMINAL, font=f_med)
    else:
        # LBLW was 200 and "Transparency" measured 200 - the label was touching
        # the bar. Plex buys the room back; 216 spends a little of it so the
        # longest label has a gap. There is slack to DIV_X either way.
        LX, LBLW, BARW, BARH, GAP = MARGIN, 216, 400, 30, 66
        BARX = LX + LBLW
        VALX = BARX + BARW + 16

        # (label, value, good, warn) - the two thresholds are drawn as ticks as
        # well as driving the colour. Without them the fill changes hue at an
        # invisible boundary, which makes the colour read as decoration rather
        # than as information.
        conditions = [
            ("Cloudless",    100 - cloud, 60, 40),
            ("Seeing",       seeing,      60, 40),
            ("Transparency", transp,      60, 40),
            ("Calm",         calm,        70, 50),
        ]
        for i, (label, value, good, warn) in enumerate(conditions):
            y = 272 + i * GAP
            draw.text((LX, y), label, fill=WHITE, font=f_sm)
            # Coloured border > opaque trough > coloured fill (opaque over the sky).
            draw.rectangle([BARX - 2, y + 2, BARX + BARW + 2, y + BARH + 6], fill=STEEL)
            draw.rectangle([BARX,     y + 4, BARX + BARW,     y + BARH + 4], fill=BG)
            filled = max(2, int(BARW * value / 100))
            # A reading below its warning mark is drawn hollow. Form, not
            # colour: it reads at a glance, it is exact rather than a gradient
            # to interpret, and it survives the red night filter intact.
            box = [BARX, y + 4, BARX + filled, y + BARH + 4]
            if value >= warn:
                draw.rectangle(box, fill=NOMINAL)
            else:
                draw.rectangle(box, outline=NOMINAL, width=3)
            # Ticks at the top and bottom edges only, so they never fight the
            # fill. DIM reads darker than any fill colour and lighter than the
            # empty trough, so one colour works on both sides of the boundary.
            for t in (warn, good):
                tx = BARX + int(BARW * t / 100)
                draw.line([(tx, y + 4), (tx, y + 11)], fill=DIM)
                draw.line([(tx, y + BARH - 3), (tx, y + BARH + 4)], fill=DIM)
            draw.text((VALX, y), f"{value}%", fill=WHITE, font=f_sm)

    draw.line([(DIV_X, HLINE2), (DIV_X, HLINE3)], fill=DIM, width=2)

    # ── Moon ──────────────────────────────────────────────────────────
    MCX = RIGHT_CX
    MR  = 100
    MCY = 364
    if moon_photo is not None:
        paste_moon(img, moon_photo, MCX, MCY, MR, ring=moon_ring)
    else:
        _draw_moon(draw, MCX, MCY, MR, moon_phase, waxing)

    phase_name = PHASE_NAMES.get(
        moon_icon, moon_icon.replace("moon-", "").replace("-", " ").title()
    )
    pn_w = int(draw.textlength(phase_name, font=f_sm))
    draw.text((MCX - pn_w // 2, MCY + MR + 8), phase_name, fill=MOON, font=f_sm)

    if moon_const:
        mc_text = f"in {moon_const}"
        mc_w    = int(draw.textlength(mc_text, font=f_xs))
        draw.text((MCX - mc_w // 2, MCY + MR + 44), mc_text, fill=WHITE, font=f_xs)

    # ── Footer ────────────────────────────────────────────────────────
    draw.line([(0, HLINE3), (W, HLINE3)], fill=DIM, width=2)

    # Row 1 -- tomorrow's forecast (left) + next new/full moon dates (right,
    # grouped under the moon card with the rest of the astronomical data).
    # Only the score is coloured. Colouring the whole phrase made a plain
    # description read as an alert and blunted the one figure that earned it.
    draw.text((MARGIN, 560), "Tomorrow:", fill=WHITE, font=f_sm)
    tm_w = int(draw.textlength("Tomorrow: ", font=f_sm))
    desc = f"{dsky_tmrw_desc}  "
    draw.text((MARGIN + tm_w, 560), desc, fill=WHITE, font=f_sm)
    draw.text((MARGIN + tm_w + int(draw.textlength(desc, font=f_sm)), 560),
              f"({dsky_tmrw}%)", fill=NOMINAL, font=f_sm)

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
    # wind_spd is km/h internally; the footer is the only place it is converted.
    wx = (f"Temp {temp:.1f}°C  -  Dew {dew:.1f}°C  -  RH {humidity}%  -  "
          f"Wind {wind_dir} {wind_spd * KMH_TO_MPH:.1f} mph")
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
# The "below the horizon" line, in the band between the compass labels (which
# end near 600) and the comet note at 656. Unlike the 10" build, the cards sit
# in the right-hand column past P2_DIV_X, so nothing has to move to make room.
PAN_BELOW_Y = 612


def _tl_x(t, t0, t1, x0, x1):
    """Map a time onto the timeline, clamped to its ends. None if unusable."""
    if t is None or t0 is None or t1 is None or t1 <= t0:
        return None
    f = (t - t0).total_seconds() / (t1 - t0).total_seconds()
    return x0 + max(0.0, min(1.0, f)) * (x1 - x0)


def _draw_timeline(draw, states, y, f_xs):
    """Dusk-to-dawn bar with true astronomical darkness and moon-up marked."""
    # h must clear the in-bar label's line height, not just look right empty:
    # at 24 the larger Plex f_xs spilled out of the bar top and bottom.
    x0, x1, h = MARGIN, W - MARGIN, 32
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
        # Label it, the same way the moon strip is labelled. This is the more
        # important of the two windows and it was the only unexplained mark on
        # the page - the bar cannot be read without knowing what the blue means.
        # The times ride in the same label rather than sitting under the
        # boundaries: one element cannot collide with the Dusk/Dawn row below,
        # and it degrades by dropping detail rather than by overlapping.
        # Each time sits at the end of the window it bounds, with the name
        # centred between them - so the segment reads as an axis of its own
        # rather than as a caption with numbers trailing after it. With Dusk
        # and Dawn already at the bar's outer ends, the whole strip is then
        # labelled at every boundary it has.
        lab = "astronomical dark"
        s0, s1 = t_a0.strftime("%H:%M"), t_a1.strftime("%H:%M")
        w0 = draw.textlength(s0, font=f_xs)
        w1 = draw.textlength(s1, font=f_xs)
        wl = draw.textlength(lab, font=f_xs)
        seg, ty = a1 - a0, y + 4
        # Degrade by dropping pieces, never by overlapping them: name and both
        # times, then times alone, then the name alone.
        if w0 + w1 + wl + 48 < seg:
            draw.text((a0 + 8, ty), s0, font=f_xs, fill=BG)
            draw.text((a1 - w1 - 8, ty), s1, font=f_xs, fill=BG)
            draw.text((a0 + (seg - wl) / 2, ty), lab, font=f_xs, fill=BG)
        elif w0 + w1 + 24 < seg:
            draw.text((a0 + 8, ty), s0, font=f_xs, fill=BG)
            draw.text((a1 - w1 - 8, ty), s1, font=f_xs, fill=BG)
        elif wl + 12 < seg:
            draw.text((a0 + (seg - wl) / 2, ty), lab, font=f_xs, fill=BG)

    # Moon up washes the sky out. Shown as its own strip ABOVE the bar rather
    # than a translucent overlay - amber over the electric segment just turned
    # the whole thing muddy brown and hid the darkness window.
    # A plain day-shift does not work here: when the moon is already up, its
    # next RISING is tomorrow's (belongs before the window) while its next
    # SETTING is genuinely after it. Setting-before-rising is what says "up now".
    rise = _dt(states.get("sensor.astroweather_backyard_moon_next_rising"))
    set_ = _dt(states.get("sensor.astroweather_backyard_moon_next_setting"))
    if rise is not None and set_ is not None:
        up_from, up_to = (dusk, set_) if set_ < rise else (rise, set_)
        m0 = _tl_x(up_from, dusk, dawn, x0, x1)
        m1 = _tl_x(up_to, dusk, dawn, x0, x1)
    else:
        m0 = m1 = None
    if m0 is not None and m1 is not None and m1 > m0:
        draw.rectangle([m0, y - 12, m1, y - 5], fill=MOON)
        # Sits clear of the strip: the label's descenders reached it once the
        # type grew, so the offset is measured from the text, not guessed.
        draw.text((m0 + 6, y - 16 - f_xs.size), "moon up", font=f_xs, fill=MOON)

    # Only mark "now" while it is actually within tonight; clamping it to an end
    # would draw a marker that reads as a real time when it is not.
    now = datetime.now().astimezone()
    if dusk <= now <= dawn:
        now_x = _tl_x(now, dusk, dawn, x0, x1)
        draw.line([(now_x, y - 4), (now_x, y + h + 4)], fill=WHITE, width=2)

    # Dusk and dawn ride INSIDE the bar's own ends. They used to sit on a row
    # underneath, which the taller bar drove into the section headings below;
    # moving them in makes the strip self-contained instead of pushing every
    # constant on the page down by 8px. They are the bar's endpoints, so this
    # is also where they belong. Falls back to the old row if the dark segment
    # leaves no unlit end to write on.
    d_lab, w_lab = dusk.strftime("Dusk %H:%M"), dawn.strftime("Dawn %H:%M")
    dw, ww = draw.textlength(d_lab, font=f_xs), draw.textlength(w_lab, font=f_xs)
    inside = (a0 is not None and a1 is not None
              and a0 - x0 > dw + 16 and x1 - a1 > ww + 16)
    ty = y + 4 if inside else y + h + 4
    draw.text((x0 + 8 if inside else x0, ty), d_lab, font=f_xs, fill=MUTED)
    draw.text((x1 - ww - (8 if inside else 0), ty), w_lab, font=f_xs, fill=MUTED)


def _draw_panorama(draw, marks, when_label, f_sm, f_xs):
    """Where to look: azimuth across, altitude up. A bearing and a height.

    marks are (az, alt, name, colour, magnitude) computed for ONE instant.
    They used to be read straight out of UpTonight's report files, but the
    object and body reports are sampled about three hours apart, so that put two
    different moments on one plot - and, having no time on it at all, the plot
    read as "now" when it was neither.
    """
    draw.line([(PAN_X0, PAN_BASE), (PAN_X1, PAN_BASE)], fill=STEEL, width=2)
    for az, lab in ((0, "N"), (90, "E"), (180, "S"), (270, "W"), (360, "N")):
        x = PAN_X0 + (az / 360.0) * (PAN_X1 - PAN_X0)
        draw.line([(x, PAN_BASE), (x, PAN_BASE + 8)], fill=STEEL)
        draw.text((x - 8, PAN_BASE + 12), lab, font=f_xs, fill=MUTED)
    for alt in (20, 40, 60):
        y = PAN_BASE - (alt / PAN_ALT_MAX) * (PAN_BASE - PAN_TOP)
        draw.line([(PAN_X0, y), (PAN_X1, y)], fill=STEEL + (70,))
        draw.text((PAN_X1 + 4, y - 12), f"{alt}", font=f_xs, fill=MUTED)
    # The axis numbers were unitless; one marker at the top says what they are.
    draw.text((PAN_X1 + 4, PAN_TOP - 6), "alt°", font=f_xs, fill=MUTED)
    # Which moment this is. Without it the plot silently reads as "now".
    draw.text((PAN_X0, PAN_TOP - 6), when_label, font=f_xs, fill=MUTED)

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

        # ONE line per object. The altitude figure used to sit on a second line
        # and was pure duplication - this plot's whole y axis is altitude, so
        # the marker already states it. Dropping it halves each label's height,
        # which fixes the Moon/Neptune and Uranus/Saturn crowding at source
        # instead of nudging labels around it. The bearing stays: it is the one
        # number worth reading off precisely, and a compass axis cannot give it.
        bearing = f"  {int(round(az))}°"
        nw = draw.textlength(name, font=f_sm)
        lx = x + r + 8
        lw = max(nw + draw.textlength(bearing, font=f_sm), 60)
        base = y - 12
        # Try alternately below then above the marker. Purely-downward nudging
        # drove low objects' labels through the horizon axis and onto the
        # compass letters, so candidates outside the plot are rejected.
        ly = None
        for off in (0, 24, -24, 48, -48, 72, -72):
            cand = base + off
            if cand < PAN_TOP - 10 or cand + 24 > PAN_BASE - 2:
                continue
            if not any(lx < b[2] and lx + lw > b[0] and cand < b[3] and cand + 24 > b[1]
                       for b in placed):
                ly = cand
                break
        if ly is None:
            ly = max(PAN_TOP - 10, min(base, PAN_BASE - 26))
        placed.append((lx, ly, lx + lw, ly + 24))
        if abs(ly - base) > 2:
            draw.line([(x + r, y), (lx - 4, ly + 12)], fill=STEEL)
        draw.text((lx, ly), name, font=f_sm, fill=WHITE)
        draw.text((lx + nw, ly), bearing, font=f_sm, fill=MUTED)


def _draw_cards(img, draw, objects, images, lat, f_med, f_sm, f_xs):
    """One screenful of deep-sky targets, with a real cutout of each patch of sky.

    Takes the objects already chosen rather than slicing here, so the caller's
    heading and these cards cannot disagree about which screenful is showing.
    """
    # Starts clear of the column heading, which descends to about y 210.
    x0, y = P2_DIV_X + 24, 220
    tile, gap = 96, 16

    # One heading for the bar column. Four right-aligned bars with no axis, no
    # legend and no label are simply unreadable - the earlier note claimed
    # keeping them beside the text stopped them reading as a mystery, and on
    # the panel they still did.
    bar_x, bar_w = x0 + tile + 18 + 230, 150
    cap = "% of dark hours up"
    draw.text((bar_x + bar_w - draw.textlength(cap, font=f_xs), 186), cap,
              font=f_xs, fill=MUTED)

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
            _glyph(draw, x0 + tile // 2, y + tile // 2, tile // 2 - 6, o.get("type"))

        tx = x0 + tile + 18
        draw.text((tx, y + 2), oid, font=f_med, fill=WHITE)

        # Type, constellation and magnitude share a line to free a row for the
        # altitude, which is the more actionable of the two.
        mag = _f(o.get("mag"), 0)
        sub = f"{o.get('type', '')} in {o.get('constellation', '')}"
        if mag > 0:
            sub += f" · mag {mag:.1f}"
        draw.text((tx, y + 38), sub, font=f_xs, fill=MUTED)

        # How high it gets and which way to face, from the declination in the
        # report: 90 - |lat - dec|. Only the MERIDIAN transit gives the time -
        # the antimeridian one is the object's LOWEST point, and for circumpolar
        # targets it is often the only one published.
        dec = o.get("declination")
        if dec is not None and lat is not None:
            alt, face = peak(dec, lat)
            line = f"peaks {alt:.0f}° {face}"
            when = ut_dt(str(o.get("meridian transit", "")))
            if when is not None:
                line += f"   at {when.strftime('%H:%M')}"
            draw.text((tx, y + 66), line, font=f_xs, fill=WHITE)

        # foto = fraction of astronomical darkness the object stays observable,
        # named by the column heading above.
        bx, bw = bar_x, bar_w
        frac = max(0.0, min(1.0, _f(o.get("foto"))))
        draw.rectangle([bx, y + 68, bx + bw, y + 82], fill=BG, outline=STEEL)
        if frac > 0:
            # Same threshold convention as the conditions bars: short of the
            # mark is hollow. One rule on both pages rather than two.
            box = [bx + 1, y + 69, bx + 1 + frac * (bw - 2), y + 81]
            if frac >= 0.75:
                draw.rectangle(box, fill=NOMINAL)
            else:
                draw.rectangle(box, outline=NOMINAL, width=2)
        y += tile + gap


def _panorama_marks(bodies, comets, obs):
    """(az, alt, name, colour, magnitude) for everything the plot shows."""
    marks = []
    for b in bodies:
        ra, dec = b.get("right ascension"), b.get("declination")
        if ra is None or dec is None:
            continue
        alt, az = alt_az(obs, ra, dec)
        name = str(b.get("target name", "?"))
        # MUTED keeps the planets clearly apart from the ivory Moon (ΔE 22.9)
        # and from the OBJECT green the comets carry.
        col = MOON if name.lower() == "moon" else MUTED
        marks.append((az, alt, name, col, _f(b.get("visual magnitude"), 5)))
    for c in comets:
        ra, dec = c.get("right ascension"), c.get("declination")
        if ra is None or dec is None:
            continue
        alt, az = alt_az(obs, ra, dec)
        marks.append((az, alt, str(c.get("target name", "?")), OBJECT,
                      _f(c.get("visual magnitude"), 8)))
    return marks


def _draw_below_horizon(draw, marks, bodies, obs, f_xs):
    """Name the bodies the panorama dropped, and when they rise.

    The plot shows nothing below the horizon, which leaves no way to tell "no
    planets tonight" from "none of them has risen yet" - and the two look
    identical exactly when the plot is emptiest. Soonest first, because the next
    body to rise is the one worth waiting for.

    Comets are left out, as they are on the 10" build: their rise times would
    come from the report's frozen coordinates rather than an ephemeris.
    """
    pos = {str(b.get("target name", "?")):
           (b.get("right ascension"), b.get("declination")) for b in bodies}
    below = [(name, next_rise(obs, name, *pos[name]))
             for _, alt, name, _, _ in marks if alt < 0 and name in pos]
    if not below:
        return
    # A body that never rises carries no time rather than a guess, and sorts last.
    below.sort(key=lambda r: (r[1] is None, r[1]))
    parts = [f"{n} {t:%H:%M}" if t else n for n, t in below]

    # The left column is 584px against the 10" build's full 1200, so this line
    # is the one place the two layouts cannot share a rule: four bodies would
    # run into the divider. Entries are dropped from the far end - the latest to
    # rise, i.e. the least actionable - until the line fits its own column.
    label, sep = "Below the horizon:   ", "   ·   "
    avail = PAN_X1 - MARGIN

    def line(k):
        s = sep.join(parts[:k])
        if k < len(parts):
            s += f"{sep}+{len(parts) - k} more"
        return label + s

    shown = len(parts)
    while shown > 1 and draw.textlength(line(shown), font=f_xs) > avail:
        shown -= 1
    # MUTED, not DIM: DIM is for rules and ticks, and these are rise times
    # someone acts on.
    draw.text((MARGIN, PAN_BELOW_Y), line(shown), font=f_xs, fill=MUTED)


def render_targets(states, targets, images, lat=None, offset=0):
    """One screenful of page 2, or None when UpTonight has produced nothing.

    `offset` is the first card's place in the ranking. Unlike the 10" build the
    panorama does NOT follow it: this layout keeps the objects off the plot
    entirely - they and the planets do not share a scale in the vertical room
    available - so there is no second view of the same six to keep in step.
    """
    objects = targets.get("objects") or []
    bodies  = targets.get("bodies") or []
    comets  = targets.get("comets") or []
    if not (objects or bodies):
        return None

    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    f_title = font("IBMPlexSans-Bold.ttf", 46)
    f_med   = font("IBMPlexSans-SemiBold.ttf", 36)
    f_sm    = font("IBMPlexSans-Regular.ttf", 26)
    f_xs    = font("IBMPlexSans-Regular.ttf", 22)

    draw.text((MARGIN, 22), "TONIGHT'S TARGETS", font=f_title, fill=WHITE)
    draw.line([(0, HLINE1), (W, HLINE1)], fill=DIM)
    _draw_timeline(draw, states, 128, f_xs)

    draw.line([(P2_DIV_X, 190), (P2_DIV_X, 664)], fill=DIM)
    draw.text((MARGIN, 182), "WHERE TO LOOK", font=f_sm, fill=NOMINAL)
    # Say what the column is actually showing. On a dark night the cap lets 40
    # objects through against four cards, so "(40 up)" alone was misleading.
    page_objects = rank_objects(objects)[offset:offset + P2_CARDS]
    count = (f"all {len(objects)}" if len(objects) <= P2_CARDS
             else f"{offset + 1}-{offset + len(page_objects)} of {len(objects)}")
    draw.text((P2_DIV_X + 24, 182), f"DEEP SKY  ({count})", font=f_sm, fill=NOMINAL)
    # One instant, computed here: the report files are sampled hours apart.
    when, when_label = plot_instant(night_window(states))
    obs = observer(lat or 0.0, LON or 0.0,
                   when=when.astimezone(timezone.utc).replace(tzinfo=None))
    marks = _panorama_marks(bodies, comets, obs)
    _draw_panorama(draw, marks, when_label, f_sm, f_xs)
    _draw_below_horizon(draw, marks, bodies, obs, f_xs)

    _draw_cards(img, draw, page_objects, images, lat, f_med, f_sm, f_xs)

    # No "+N more": it dangled an object the page never shows, and the column
    # heading already carries the total.
    if comets:
        c = comets[0]
        draw.text((MARGIN, 656),
                  f"Comet {c.get('target name', '?')} - "
                  f"alt {_f(c.get('altitude')):.0f}°, az {_f(c.get('azimuth')):.0f}°",
                  font=f_xs, fill=MUTED)
    # The credit was at (60, 66, 86) - about 1.9:1, which is barely visible. An
    # attribution nobody can read is not much of an attribution, and CDS ask for
    # this one. DIM keeps it recessive without hiding it.
    draw.text((MARGIN, 688), "Sky imagery: DSS2 / CDS Strasbourg", font=f_xs, fill=DIM)
    return img


def draw_clock(draw):
    """Stamp the header date and time onto a composed frame.

    Drawn per frame rather than into the cached dashboard overlay, so the minute
    advances live and the date rolls over at midnight. It is one short text draw
    over transparent sky, which the 20 fps loop does not notice.
    """
    f_sm    = font("IBMPlexSans-Regular.ttf", 32)
    now_str = datetime.now().strftime("%a %d %b  %H:%M")
    ts_w    = int(draw.textlength(now_str, font=f_sm))
    # Secondary ink: at full white it carried the same weight as the title and
    # the two competed for the header.
    draw.text((W - ts_w - MARGIN, 28), now_str, fill=MUTED, font=f_sm)


def refresh_stars():
    """Point the starfield at the real sky for right now.

    Recomputed on a timer rather than per frame: the sky turns a quarter of a
    degree a minute, so once a minute is imperceptibly smooth, and the result is
    handed to Sky in the format draw_stars already takes, so the frame cost is
    unchanged.

    Meteor radiants are refreshed here and nowhere else, so switching the real
    sky off also returns meteors to arbitrary directions. That is deliberate: a
    correct radiant over an invented starfield is false precision, and the two
    should be real together or not at all.
    """
    if not REAL_STARS:
        return None
    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    obs = observer(LAT or 0.0, LON or 0.0, when=utc)
    stars = project(obs, W, H, CAMERA_AZ, CAMERA_ALT, CAMERA_FOV,
                    limit=LIMITING_MAG, bands=SIZE_BANDS_SPARSE,
                    ratio=SPARSE_RATIO, floor=SPARSE_FLOOR)
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

    core.sky spawns meteors on a fixed cadence scaled only by cloud, so a clear
    night in March showed the same shower as the Perseid peak. The rate now
    comes from the shower table: activity by solar longitude, cut by radiant
    altitude, cloud and moonlight.

    NOTHING ACTIVE MEANS NO METEORS. That matters more here than it did before
    the starfield became real - invented meteors falling through a real sky are
    the same class of error as showing yesterday's Moon.

    The rate is TIME-COMPRESSED, a stated convention rather than a fudge: three
    an hour is honest and makes an animated sky look broken, so the panel runs
    meteors as though watching for `meteor_compression` minutes per minute. It
    scales what is there and cannot manufacture what is not.
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


def target_pages(states, targets, lat):
    """Every screenful of page 2, as a Paged run, or empty if there is nothing.

    All of them are rendered here because stepping between them happens on the
    render loop, which can afford neither a re-render nor the cutout fetches
    behind one. Cutouts are therefore fetched for the whole list rather than the
    first screenful; they are cached on disk, so it is a one-off cost per object.

    This build shows four at a time against the 10" build's six, so a list of
    forty runs to ten screenfuls here and seven there.
    """
    objects = targets.get("objects") or []
    n = max(1, -(-len(objects) // P2_CARDS))   # ceiling division
    images = load_cutouts(targets, len(objects) or P2_CARDS)
    out = Paged()
    for i in range(n):
        page = render_targets(states, targets, images, lat, i * P2_CARDS)
        if page is None:      # no objects and no bodies: there is no page at all
            return Paged()
        out.append(page)
    return out


def build_pages(states, targets, lat, moon_ring=False):
    """Both dashboard pages as RGBA overlays.

    Data thread only: this fetches the hour's lunar frame and any deep-sky
    cutouts not already cached.
    """
    # The 5" layout has no room for the accompanying facts, so it takes the
    # frame and drops them; the 10" build shows them.
    pages = [render_foreground(states, moon_image()[0], moon_ring)]
    # The targets page joins the rotation only when there is something on it -
    # better a single page than a dead one before UpTonight's first run. It
    # carries every object UpTonight passed, as a Paged run stepped by its own
    # button; four cards against a list of forty is the case that most needs it.
    page2 = target_pages(states, targets, lat)
    if page2:
        pages.append(page2)
    return pages


def compose(frame, overlay, labels=None):
    """Dashboard, clock and control strip over a painted sky frame.

    This puts the clouds BEHIND the moon disc, which looks wrong and is not.
    Cloud is a few kilometres up and the Moon is 384,000 km away, so in the sky
    cloud always crosses in front - but the disc here is a card, not a view.
    The sky layer runs about 10 px per degree on this panel, where the real Moon
    is roughly 5 px across; the card draws it many times that, at a fixed place
    in the layout rather than where the Moon is. Cloud drifting across it would
    assert the Moon really is there, that big, in that direction, which is the
    class of claim the starfield and the meteor radiants were changed to stop
    making. Do not "fix" this by compositing the moon into the sky frame without
    also solving the size and the position.
    """
    frame.paste(overlay, (0, 0), overlay)
    d = ImageDraw.Draw(frame)
    draw_clock(d)
    # Drawn per frame alongside the clock rather than into the cached overlay:
    # they change on their own timers, and the overlay only changes when the
    # data does.
    if labels:
        strip.draw(d, labels, font("IBMPlexSans-SemiBold.ttf", 26))
    return frame


# ── Run modes ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Touch Display 2 stargazing display")
    parser.add_argument("--save", metavar="PATH", help="Save a single composited frame and exit")
    parser.add_argument("--once", action="store_true", help="Render one frame to the panel and exit")
    parser.add_argument("--no-night", action="store_true",
                        help="Save in the daylight palette whatever the hour "
                             "(for documentation; the panel is unaffected)")
    parser.add_argument("--demo", action="store_true", help="Force vivid clear-sky animation (ignore conditions)")
    parser.add_argument("--compare", action="store_true",
                        help="Fetch from both weather sources and print a per-value diff")
    args = parser.parse_args()

    global LAT, LON, LIMITING_MAG, REAL_STARS, CAMERA_AZ, CAMERA_ALT, CAMERA_FOV, METEOR_COMPRESSION
    config = load_config(CONFIG_PATH)
    out_dir = config.get("uptonight", {}).get("out_dir", "")
    lat    = config.get("location", {}).get("latitude")
    LON    = config.get("location", {}).get("longitude")
    LAT    = lat
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
    disp   = config.get("display", {})
    mode   = disp.get("mode", "animated")
    fps    = float(disp.get("fps", 12))
    refresh_min = float(disp.get("data_refresh_min", 15))
    page_seconds = float(disp.get("page_seconds", 20))
    night = disp.get("night_mode", "off")
    night_dim = int(disp.get("night_dim", 45))
    if night not in NIGHT_CYCLE:
        raise ValueError(f'display.night_mode is "{night}"; '
                         'expected "off", "dim" or "red"')
    moon_ring = bool(disp.get("moon_ring", False))
    METEOR_COMPRESSION = float(disp.get("meteor_compression", METEOR_COMPRESSION))
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
        targets = read_targets(out_dir)
        params = sky_params(states)
        pages = build_pages(states, targets, lat, moon_ring)
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
            apply_night(frames[0], now_mode, night_dim).save(args.save)
            log.info("Saved %s", args.save)
            if len(frames) > 1:
                p = Path(args.save)
                # The first screenful keeps the plain _targets name the README
                # refers to; the rest are numbered after it.
                for i, frame in enumerate(frames[1:], 1):
                    stem = p.stem + "_targets" + ("" if i == 1 else f"_{i}")
                    out = str(p.with_name(stem + p.suffix))
                    apply_night(frame, now_mode, night_dim).save(out)
                    log.info("Saved %s", out)
            else:
                log.warning("No UpTonight reports in %s - targets page skipped.", out_dir)
        else:
            with fb.open() as out:
                out.write(fb.to_bytes(frames[0], now_mode, night_dim))
            log.info("Done. v%s", FIRMWARE_VERSION)
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
