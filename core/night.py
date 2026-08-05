"""Night mode, and the dusk-to-dawn window that governs it.

The transform is applied to the FINISHED frame rather than by swapping the
palette. A palette swap would have left the DSS2 photographs and the lunar
frame glowing white, and would have meant threading a theme through every colour
reference in a build's layout.
"""
from datetime import datetime, timedelta

import numpy as np
from PIL import Image

from core.values import _dt

NIGHT_CYCLE = ("off", "dim", "red")


def night_filter(arr, mode, dim):
    """Night transform over an HxWx3 uint16 array. The transform lives here
    once; both the framebuffer path and --save go through it."""
    if mode == "dim":
        return (arr * dim) // 100
    if mode == "red":
        # Rec.601 luma, then everything onto the red channel. Red is what
        # observers use because long wavelengths leave scotopic vision alone;
        # a trace of green and blue keeps it from looking like a fault.
        lum = (arr[:, :, 0] * 54 + arr[:, :, 1] * 183 + arr[:, :, 2] * 19) >> 8
        out = np.zeros_like(arr)
        out[:, :, 0] = lum
        out[:, :, 1] = lum >> 4
        out[:, :, 2] = lum >> 5
        return out
    return arr


def apply_night(img, mode, dim):
    """Same transform, for the paths that want a PIL image back (--save)."""
    if mode == "off":
        return img
    arr = night_filter(np.asarray(img, dtype=np.uint16), mode, dim)
    return Image.fromarray(arr.astype(np.uint8))


def night_window(states):
    """Tonight's civil dusk -> dawn.

    The sun_next_* sensors roll to TOMORROW as soon as the event passes, so
    after sunset next_setting is tomorrow's and the window inverts. That used to
    blank the entire timeline every night from sunset onward - i.e. whenever the
    display was actually worth looking at.
    """
    dusk = _dt(states.get("sensor.astroweather_backyard_sun_next_setting"))
    dawn = _dt(states.get("sensor.astroweather_backyard_sun_next_rising"))
    if dusk is None or dawn is None:
        return None, None
    if dusk >= dawn:
        dusk -= timedelta(days=1)     # sunset already happened; this is tonight
    return dusk, dawn


def tonight(t, end):
    """Step a 'next event' back a day when it points past tonight's window."""
    return t - timedelta(days=1) if (t is not None and t > end) else t


def inside_window(window):
    """True when the clock is between real dusk and dawn."""
    if not window:
        return False
    dusk, dawn = window
    if dusk is None or dawn is None:
        return False
    return dusk <= datetime.now().astimezone() <= dawn


def night_mode_now(mode, window):
    """The mode to apply right now - "off" outside the dusk-to-dawn window.

    Tied to real dusk and dawn rather than a clock schedule, because the whole
    point is to stop the panel wrecking dark adaptation, and that starts when
    the sky does.
    """
    return mode if mode != "off" and inside_window(window) else "off"
