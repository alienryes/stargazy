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
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from core.daemon import install_signal_handlers, run_daemon
from core.fonts import font
from core.imagery import moon_image, paste_moon
from core.night import NIGHT_CYCLE, apply_night, night_mode_now, night_window
from core.palette import (
    AMBER,
    BG,
    DIM,
    MOON,
    MOON_DARK,
    MUTED,
    STEEL,
    WHITE,
    bar_colour,
    verdict,
)
from core.panel import Framebuffer, Strip
from core.sky import Sky, sky_params
from core.targets import read_targets
from core.touch import TouchReader
from core.values import _dt, _f, _i, _phrase, load_config
from core.weather import KMH_TO_MPH, compare_sources, make_fetcher

VERSION = "0.1.0"

# The largest image this program legitimately opens is a 730x730 moon frame.
# PIL's default decompression-bomb threshold (~178M pixels) would let a hostile
# response balloon to a ~500MB decode before tripping. Cap it far above anything
# real and far below anything dangerous.
Image.MAX_IMAGE_PIXELS = 3_000 * 3_000

CONFIG_PATH = Path(__file__).parent / "config.toml"
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

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
HLINE3 = 1200               # moon bottom
HLINE4 = 1576               # conditions bottom

MOON_CY = 700               # centre of the lunar disc
MOON_R = 300                # 600px across
# Three captions hang below the disc. Measured against their own line heights,
# not eyeballed: the first preview put the constellation line through HLINE3 and
# pushed the moon dates behind the condition bars entirely.
MOON_CAP1, MOON_CAP2, MOON_CAP3 = 24, 86, 140   # offsets below the disc edge

BAR_Y0, BAR_GAP = 1240, 88
BAR_LBLW, BAR_W, BAR_H = 300, 620, 40

FOOT_Y0, FOOT_GAP = 1616, 56

# Touch control strip. Hidden until the panel is tapped, because this is an
# ambient display and permanent on-screen buttons would cost content space on
# every one of the thousands of frames nobody is touching.
STRIP_H = 80
STRIP_Y = H - STRIP_H - 24
BTN_GAP = 10

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


def render_conditions(states, moon_photo=None, moon_ring=False):
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
        v_text, v_colour = "NO DARK SKY", AMBER
        v_sub = f"Next dark night: {next_dark.strftime('%d %b') if next_dark else 'unknown'}"
    else:
        v_text, v_colour = verdict(dsky_today)
        v_sub = f"Deep sky: {dsky_today}%  -  {dsky_today_desc}"
    # Optical, not metric: heavy display type reads as indented beside regular
    # text even when the stems are flush, so it gets a small pull left.
    draw.text((MARGIN - 5, 146), v_text, fill=v_colour, font=f["xl"])
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
    draw.line([(0, HLINE3), (W, HLINE3)], fill=DIM, width=2)

    # ── Conditions ────────────────────────────────────────────────────
    if no_dark and next_dark:
        days = max(0, (next_dark.date() - datetime.now().date()).days)
        big, sub = ("Tonight", "dark sky returns") if days == 0 else (str(days), "days until dark sky")
        _centre(draw, big, BAR_Y0 + 20, AMBER, f["xl"])
        _centre(draw, sub, BAR_Y0 + 170, WHITE, f["sm"])
    else:
        barx = MARGIN + BAR_LBLW
        valx = barx + BAR_W + 20
        # (label, value, good, warn) - the thresholds are drawn as ticks as well
        # as driving the colour. Without them the fill changes hue at an
        # invisible boundary, and the colour reads as decoration.
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
            draw.rectangle([barx, y + 4, barx + max(2, int(BAR_W * value / 100)),
                            y + BAR_H + 4], fill=bar_colour(value, good, warn))
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
              f"({dsky_tmrw}%)", fill=verdict(dsky_tmrw)[1], font=f["sm"])

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

    # wind_spd is km/h internally; the footer is the only place it is converted.
    y += FOOT_GAP
    draw.text((MARGIN, y), f"Temp {temp:.1f}°C  -  Dew {dew:.1f}°C  -  RH {humidity}%",
              fill=WHITE, font=f["sm"])
    y += FOOT_GAP
    draw.text((MARGIN, y), f"Wind {wind_dir} {wind_spd * KMH_TO_MPH:.1f} mph",
              fill=WHITE, font=f["sm"])

    _right(draw, f"v{VERSION}", H - 44, DIM, f["xs"])
    return img


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
    return [render_conditions(states, moon_image(), moon_ring)]


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

    config = load_config(CONFIG_PATH)
    out_dir = config.get("uptonight", {}).get("out_dir", "")
    lat    = config.get("location", {}).get("latitude")
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
    tch = config.get("touch", {})

    if args.compare:
        return compare_sources(config)

    fetch = make_fetcher(config)

    if args.save or args.once:
        log.info("Fetching conditions...")
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
