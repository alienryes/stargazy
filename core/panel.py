"""The panel itself: framebuffer packing, backlight, and the touch control strip.

Geometry is passed in rather than read from globals, so one engine drives panels
of different sizes.
"""
import glob
import logging
import time
from pathlib import Path

import numpy as np
from PIL import Image

from core.night import NIGHT_CYCLE, inside_window, night_filter, night_mode_now
from core.palette import BG, STEEL, WHITE

log = logging.getLogger(__name__)

FB_DEV = "/dev/fb0"


class Framebuffer:
    """Rotation, night transform and RGB565 packing for one panel.

    RGB565 is assumed, which is what both Touch Display 2 panels present -
    including on a Pi 5, where /dev/fb0 comes from DRM's fbdev emulation and was
    measured at 16bpp rather than the 32bpp that emulation often defaults to.
    Confirm bits_per_pixel on a new board before trusting this; a 32bpp panel
    needs a second packing branch, not a resize.
    """

    def __init__(self, w, h, fb_w, fb_h, rotate=Image.ROTATE_90, dev=FB_DEV):
        self.w, self.h = w, h
        self.fb_w, self.fb_h = fb_w, fb_h
        self.rotate = rotate
        self.dev = dev

    def to_bytes(self, img, night="off", dim=45):
        # rotate is None for a build drawn in the panel's native portrait, which
        # is a straight write with no transpose at all.
        rot = img if self.rotate is None else img.transpose(self.rotate)
        if rot.size != (self.fb_w, self.fb_h):
            rot = rot.resize((self.fb_w, self.fb_h))
        arr = np.asarray(rot, dtype=np.uint16)
        # Filtered here rather than in the compositor: this array already
        # exists, so night mode costs no extra conversion on the animated path.
        arr = night_filter(arr, night, dim)
        packed = (((arr[:, :, 0] >> 3) << 11)
                  | ((arr[:, :, 1] >> 2) << 5)
                  | (arr[:, :, 2] >> 3))
        return packed.astype("<u2").tobytes()

    def dark_frame(self):
        return b"\x00" * (self.fb_w * self.fb_h * 2)

    def open(self):
        return open(self.dev, "wb")


def _backlight(name):
    """Path to a backlight sysfs attribute, or None if the panel has none."""
    dirs = sorted(glob.glob("/sys/class/backlight/*"))
    return Path(dirs[0]) / name if dirs else None


def read_brightness(name="brightness"):
    p = _backlight(name)
    try:
        return int(p.read_text()) if p else 0
    except OSError:
        return 0


def set_brightness(value):
    """Set the panel backlight. Does nothing, loudly, if it is not writable.

    bl_power would be the natural way to blank the panel, but on this kernel it
    is root-only while brightness is writable by group video - which the daemon
    is already in - so brightness 0 is what blanking uses.
    """
    p = _backlight("brightness")
    if not p:
        return
    try:
        p.write_text(str(value))
    except OSError as e:
        log.warning("Backlight not writable: %s", e)


class Strip:
    """Geometry and painting for the hidden control strip.

    It is hidden until the panel is tapped, because this is an ambient display
    and permanent on-screen buttons would cost content space on every one of the
    thousands of frames nobody is touching.
    """

    def __init__(self, w, margin, y, h, gap=8, text_dy=16):
        self.w, self.margin, self.y, self.h = w, margin, y, h
        self.gap, self.text_dy = gap, text_dy

    def rects(self, n):
        """The n buttons, left to right, as (x0, y0, x1, y1)."""
        bw = (self.w - 2 * self.margin - (n - 1) * self.gap) // n
        return [(self.margin + i * (bw + self.gap), self.y,
                 self.margin + i * (bw + self.gap) + bw, self.y + self.h)
                for i in range(n)]

    def at(self, x, y, n):
        """Index of the button under a tap, or None."""
        for i, (x0, y0, x1, y1) in enumerate(self.rects(n)):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
        return None

    def draw(self, draw, labels, font):
        """Stamp the control strip over a composed frame."""
        for (x0, y0, x1, y1), label in zip(self.rects(len(labels)), labels):
            draw.rounded_rectangle((x0, y0, x1, y1), radius=10,
                                   fill=BG, outline=STEEL, width=2)
            tw = int(draw.textlength(label, font=font))
            draw.text(((x0 + x1 - tw) // 2, y0 + self.text_dy), label,
                      fill=WHITE, font=font)


class Controls:
    """What the control strip shows, and what a tap on it does.

    None of this is persisted: config.toml stays the source of truth for the
    defaults, so a restart always comes back to a known state rather than to
    whatever was last poked at in the dark.
    """

    def __init__(self, night, strip_seconds, strip):
        self.config_night   = night
        self.strip_seconds  = strip_seconds
        self.strip          = strip
        self.override       = None   # night mode chosen by hand, or None
        self.override_dark  = None   # dusk-to-dawn state when it was chosen
        self.paused         = False
        self.next_page      = False
        self.blanked        = False
        self.shown_until    = 0.0
        self.max_brightness = read_brightness("max_brightness")
        self.brightness     = read_brightness() or self.max_brightness

    @property
    def visible(self):
        return time.time() < self.shown_until

    def show(self):
        self.shown_until = time.time() + self.strip_seconds

    def labels(self):
        return [f"Night: {self.override or self.config_night}",
                "Resume" if self.paused else "Pause",
                "Next", "Dimmer", "Brighter", "Blank"]

    def night_now(self, window):
        """The night mode to apply right now, honouring a manual override.

        An override applies immediately whatever the hour - being able to see
        red mode in the afternoon is most of the point of a button - but it
        lapses the next time the sky crosses dusk or dawn. It is a change of
        mind about tonight, not a second schedule competing with the real one.
        """
        dark = inside_window(window)
        if self.override is not None and dark != self.override_dark:
            self.override = None
        if self.override is not None:
            return self.override
        return night_mode_now(self.config_night, window)

    def take_next(self):
        """True once after the Next button is pressed."""
        stepped, self.next_page = self.next_page, False
        return stepped

    def _step_brightness(self, direction):
        # Never down to 0: going fully dark is what Blank is for, and the strip
        # must stay visible for the change to be reversible.
        step = max(1, self.max_brightness // 8)
        self.brightness = max(1, min(self.max_brightness,
                                     self.brightness + direction * step))
        set_brightness(self.brightness)

    def blank(self):
        self.blanked = True
        self.shown_until = 0.0
        set_brightness(0)

    def wake(self):
        self.blanked = False
        set_brightness(self.brightness)

    def touched(self, x, y, window):
        """Handle one tap, in render coordinates."""
        if self.blanked:
            self.wake()
            return
        if not self.visible:
            # First tap only reveals the controls. Nothing on an ambient
            # display should fire from a tap whose target was not visible.
            self.show()
            return
        self.show()
        idx = self.strip.at(x, y, len(self.labels()))
        if idx == 0:
            cur = self.night_now(window)
            self.override = NIGHT_CYCLE[(NIGHT_CYCLE.index(cur) + 1) % len(NIGHT_CYCLE)]
            self.override_dark = inside_window(window)
        elif idx == 1:
            self.paused = not self.paused
        elif idx == 2:
            self.next_page = True
        elif idx == 3:
            self._step_brightness(-1)
        elif idx == 4:
            self._step_brightness(+1)
        elif idx == 5:
            self.blank()
