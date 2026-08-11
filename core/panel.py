"""The panel itself: framebuffer packing, backlight, and the touch control strip.

Geometry is passed in rather than read from globals, so one engine drives panels
of different sizes.
"""
import fcntl
import glob
import logging
import time
from pathlib import Path

import numpy as np
from PIL import Image

from core.night import (
    NIGHT_CYCLE,
    inside_window,
    night_filter,
    night_mode_now,
    red_luma_img,
)
from core.palette import BG, STEEL, WHITE

log = logging.getLogger(__name__)

FB_DEV = "/dev/fb0"

# RGB565 for every possible luma value, for the red night mode's 16bpp pack.
# See Framebuffer._pack565_luma for where the fields come from.
_LUMA_LEVELS = np.arange(256, dtype=np.uint16)
_LUT565_LUMA = ((((_LUMA_LEVELS >> 3) << 11)
                 | ((_LUMA_LEVELS >> 6) << 5)).astype("<u2"))

# Degrees to PIL's constants, so a build can carry ONE rotation figure and hand
# it to both the framebuffer and the touch reader. They have to agree: the
# touchscreen reports in the panel's frame whatever the renderer does, so a
# rotation applied to the image and not to the taps puts every press somewhere
# else on the screen.
PIL_ROTATION = {0: None, 90: Image.ROTATE_90,
                180: Image.ROTATE_180, 270: Image.ROTATE_270}

# linux/fb.h. Unblanking needs no privilege beyond write access to the device,
# which the daemon already has through the video group.
FBIOBLANK = 0x4611
FB_BLANK_UNBLANK = 0


def _fb_attr(dev, name):
    """One sysfs attribute of a framebuffer device, or None if unreadable.

    Absent on a host with no framebuffer at all, which is the normal case when
    --save renders a preview on a development machine.
    """
    try:
        return int((Path("/sys/class/graphics") / Path(dev).name / name).read_text())
    except (OSError, ValueError):
        return None


class Framebuffer:
    """Rotation, night transform and pixel packing for one panel.

    Two pixel formats are supported, and the depth is READ FROM THE DEVICE
    rather than assumed, because the two panels genuinely differ: the 5" Touch
    Display 2 on a Pi 4 presents 16bpp RGB565, while the 10.1" on a Pi 5
    presents 32bpp XRGB8888 - byte order B,G,R,X in memory.

    Neither is fixed by the hardware: the 5" panel's 16bpp is the vc4 KMS
    framebuffer emulation's choice, and a `video=` line in cmdline.txt overrides
    it to 32 - see the README. That is one more reason to read the depth rather
    than infer it from which panel is attached.

    An earlier 16bpp reading from the Pi 5 was taken with no panel attached, so
    it measured a phantom HDMI framebuffer rather than the display. Hardcoding
    that would have failed loudly rather than subtly: a 565 pack emits half the
    bytes a 32bpp panel expects, so the result is garbage, not a tinted image.
    Reading the device costs one file read at startup and cannot go stale.
    """

    def __init__(self, w, h, fb_w, fb_h, rotate=Image.ROTATE_90, dev=FB_DEV, bpp=None):
        self.w, self.h = w, h
        self.fb_w, self.fb_h = fb_w, fb_h
        self.rotate = rotate
        self.dev = dev
        # 16 when there is no device to ask. That path never writes a
        # framebuffer, so the fallback only has to be harmless, not correct.
        self.bpp = bpp or _fb_attr(dev, "bits_per_pixel") or 16

    @staticmethod
    def _pack565(rgb):
        """RGB565 little-endian from an HxWx3 uint8 array.

        One uint16 accumulator rather than an HxWx3 uint16 intermediate. The
        general path widens all three channels first - 2.7 million values on the
        5" panel - and then reads them straight back out to pack, and the pack
        is 71% of that build's frame.

        r>>3 lands in bits 11-15, g>>2 in 5-10, b>>3 in 0-4, which is what the
        two accumulating shifts below build up.
        """
        out = (rgb[:, :, 0] >> 3).astype(np.uint16)
        out <<= 6
        out |= rgb[:, :, 1] >> 2
        out <<= 5
        out |= rgb[:, :, 2] >> 3
        return out.astype("<u2", copy=False).tobytes()

    @staticmethod
    def _pack565_luma(lum):
        """RGB565 from a single luma plane, for the red night mode.

        A 256-entry lookup, because luma is 8-bit and the output is one uint16
        per pixel: the whole transform fits in a table and the pack becomes a
        single gather. DERIVED from the general path, not invented, and the
        table is built from the same expression it replaces - night_filter
        writes lum, lum>>4 and lum>>5 into R, G and B, and the 565 pack takes
        r>>3, g>>2 and b>>3, so the fields are lum>>3, lum>>6 and lum>>8. Luma
        is 8-bit, so the blue field is always zero.

        The table does NOT pay off at 32bpp, where it gathers four bytes per
        pixel instead of two: measured on the 10" panel it was 57.7 ms against
        29.1 for the three broadcast writes that path uses instead.
        """
        return _LUT565_LUMA[lum].tobytes()

    def to_bytes(self, img, night="off", dim=45):
        # rotate is None for a build drawn in the panel's native portrait, which
        # is a straight write with no transpose at all.
        rot = img if self.rotate is None else img.transpose(self.rotate)
        if rot.size != (self.fb_w, self.fb_h):
            rot = rot.resize((self.fb_w, self.fb_h))
        # XRGB8888 on a little-endian machine, so the bytes go down in the order
        # B, G, R, unused - not R, G, B. Four shortcuts, two per depth, avoid
        # building an HxWx3 intermediate that is then read straight back out
        # again; all four were checked byte for byte against the general path
        # below, and the checks live in tools/check_fb_paths.py.
        #
        # The two night modes are not the same cost. On the 10.1" panel the
        # general path took 98 ms a frame in red against an 83 ms budget at
        # 12 fps, so the configured rate was unreachable between dusk and dawn,
        # which is when the display is red and when meteors are drawn.
        if self.bpp == 32:
            if night == "off":
                # PIL does the channel swap and the pad byte in its own C loop.
                src = rot if rot.mode == "RGB" else rot.convert("RGB")
                return src.tobytes("raw", "BGRX")
            if night == "red":
                lum = red_luma_img(rot)
                out = np.empty((self.fb_h, self.fb_w, 4), np.uint8)
                out[:, :, 0] = lum >> 5
                out[:, :, 1] = lum >> 4
                out[:, :, 2] = lum
                out[:, :, 3] = 0
                return out.tobytes()

        if self.bpp == 16:
            # The same two cases at 16bpp, and they mattered more here: before
            # these paths existed the frame was 76.9 ms in off and 118.1 ms in
            # red, 13.0 and 8.5 fps against a configured 20, with to_bytes 71%
            # of it in both modes. It is now 51 and 43.
            #
            # PIL cannot help with the PACK at this depth the way it does at 32:
            # there is no 565 packer, and both `BGR;16` and `RGB;16` raise "No
            # packer found". So the saving here comes from not building
            # intermediates rather than from handing the loop to C. The red
            # path's LUMA is a different matter and does go to C - see
            # red_luma_img, which is where most of that mode's cost was.
            if night == "off":
                return self._pack565(np.asarray(rot))
            if night == "red":
                return self._pack565_luma(red_luma_img(rot))

        arr = np.asarray(rot, dtype=np.uint16)
        # Filtered here rather than in the compositor: this array already
        # exists, so night mode costs no extra conversion on the animated path.
        arr = night_filter(arr, night, dim)
        if self.bpp == 32:
            out = np.empty((self.fb_h, self.fb_w, 4), np.uint8)
            out[:, :, 0] = arr[:, :, 2]
            out[:, :, 1] = arr[:, :, 1]
            out[:, :, 2] = arr[:, :, 0]
            out[:, :, 3] = 0
            return out.tobytes()
        packed = (((arr[:, :, 0] >> 3) << 11)
                  | ((arr[:, :, 1] >> 2) << 5)
                  | (arr[:, :, 2] >> 3))
        return packed.astype("<u2").tobytes()

    def dark_frame(self):
        return b"\x00" * (self.fb_w * self.fb_h * self.bpp // 8)

    def open(self):
        """Open and wake the framebuffer, refusing a geometry it cannot fill.

        A stride wider than the visible line means padding between rows, which a
        flat write smears diagonally down the panel. Neither supported panel
        pads, so this guards a board that has not been seen rather than one that
        has - but the whole reason this method now checks anything is that an
        unstated framebuffer assumption already cost a debugging session, and
        failing at startup beats rendering garbage for as long as the daemon runs.
        """
        want = self.fb_w * self.bpp // 8
        stride = _fb_attr(self.dev, "stride")
        if stride is not None and stride != want:
            raise RuntimeError(
                f"{self.dev} stride is {stride}, expected {want} for "
                f"{self.fb_w}px at {self.bpp}bpp: padded framebuffers are not supported")
        log.info("Framebuffer %s: %dx%d at %dbpp.",
                 self.dev, self.fb_w, self.fb_h, self.bpp)
        fh = open(self.dev, "wb")
        # Wake the panel before the first frame. fbcon=map:2 keeps the text
        # console off this framebuffer, so on a board whose firmware does not
        # set up a mode either - a Pi 5 with disable_fw_kms_setup=1 - nothing
        # ever enables the CRTC, and the daemon renders perfectly into a buffer
        # that is never scanned out. The symptom is a dark panel with a healthy
        # service, which reads as a rendering bug and is not one. Where
        # something else already enabled the display this is a no-op, so both
        # builds do it unconditionally.
        try:
            fcntl.ioctl(fh, FBIOBLANK, FB_BLANK_UNBLANK)
        except OSError as e:
            # Not fatal: a panel that is already lit stays lit. Worth a line in
            # the journal, because a dark screen after this is a different fault.
            log.warning("Could not unblank %s: %s", self.dev, e)
        return fh


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
        self.next_cards     = False
        self.blanked        = False
        self.shown_until    = 0.0
        self.max_brightness = read_brightness("max_brightness")
        self.brightness     = read_brightness() or self.max_brightness

    @property
    def visible(self):
        return time.time() < self.shown_until

    def show(self):
        self.shown_until = time.time() + self.strip_seconds

    def labels(self, window=None, paged=False):
        """Button captions. Every one names what pressing it will DO.

        `paged` adds a seventh button, and only the targets page passes it: the
        other pages hold one screenful, so a More there would either lie or do
        nothing. The strip divides its width by the number of captions, so the
        button count changing between pages moves every button - which is safe
        only because the loop holds the page still while the strip is up.

        The night button used to name the mode in force, which read as state
        beside five buttons naming actions - and was not even the mode in
        force, since it showed the configured value while `night_now` returns
        "off" in daylight whatever the config says. It now names the mode the
        press will select, the way Pause and Resume name the state being moved
        to rather than the one being left.

        The panel already shows which mode is active by being that colour, so
        nothing is lost by labelling the destination instead.
        """
        cur = self.night_now(window)
        nxt = NIGHT_CYCLE[(NIGHT_CYCLE.index(cur) + 1) % len(NIGHT_CYCLE)]
        return [f"Night → {nxt}",
                "Resume" if self.paused else "Pause",
                "Next", "Dimmer", "Brighter", "Blank"] + (["More"] if paged else [])

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

    def take_next_cards(self):
        """True once after the More button is pressed."""
        stepped, self.next_cards = self.next_cards, False
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

    def touched(self, x, y, window, paged=False):
        """Handle one tap, in render coordinates.

        `paged` must be the value the strip was DRAWN with, or the hit test
        divides the width into a different number of cells than the user is
        looking at and every button is offset.
        """
        if self.blanked:
            self.wake()
            return
        if not self.visible:
            # First tap only reveals the controls. Nothing on an ambient
            # display should fire from a tap whose target was not visible.
            self.show()
            return
        self.show()
        idx = self.strip.at(x, y, len(self.labels(window, paged)))
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
        elif idx == 6:
            self.next_cards = True
