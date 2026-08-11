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


# Rec.709: 54/183/19 over 256 is 0.211/0.715/0.074. (This was described as
# Rec.601 for a while, which would be 0.299/0.587/0.114 - a different
# transform, and the numbers were always the 709 ones.)
RED_LUMA_MATRIX = (54 / 256, 183 / 256, 19 / 256, 0)


def red_luma_img(img):
    """Luma as a uint8 HxW array, from a PIL image, for the red night mode.

    PIL applies the matrix in its own C loop. The equivalent numpy is three
    multiplies over an HxWx3 array widened to uint16 first, and that widening
    alone is 2.7 million values on the 5" panel; measured against this, the
    numpy version was 13.6 ms a frame slower there and 19.6 ms on the 10".
    Red is the mode the display runs in from dusk to dawn, so it is the one
    worth the C loop.

    PIL rounds where the integer expression floored, so luma can land one level
    off what this returned before 2026-08-11. That is a step of 1 in 255 on a
    monochrome frame.
    """
    return np.asarray(img.convert("L", RED_LUMA_MATRIX))


def red_luma(arr):
    """The same luma for callers holding an array rather than an image.

    ONE implementation, deliberately: night_filter stacks the result back into
    an HxWx3 array for --save, while the framebuffer packs it straight into its
    output buffer and never builds that array at all. Both must agree by
    construction, not by being kept in step - so this routes through the image
    path rather than reimplementing the coefficients.
    """
    return red_luma_img(Image.fromarray(arr.astype(np.uint8), "RGB"))


def night_filter(arr, mode, dim):
    """Night transform over an HxWx3 uint16 array. The transform lives here
    once; both the framebuffer path and --save go through it."""
    if mode == "dim":
        return (arr * dim) // 100
    if mode == "red":
        # Everything onto the red channel. Red is what observers use because
        # long wavelengths leave scotopic vision alone; a trace of green and
        # blue keeps it from looking like a fault.
        lum = red_luma(arr).astype(arr.dtype)
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
