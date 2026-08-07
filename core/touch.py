#!/usr/bin/env python3
"""Touch input for the Raspberry Pi Touch Display 2, read straight from evdev.

The display draws to the framebuffer with no X and no Wayland, so there is no
input stack to ask - but there does not need to be one. The panel's touch
controller is an ordinary evdev device and a tap is a handful of fixed-size
records, so this reads /dev/input/eventN directly and the project stays
dependency-free.

Run it on its own to check the coordinate mapping:

    python3 touch.py        # prints raw and mapped coordinates for each tap
"""

import fcntl
import glob
import logging
import os
import queue
import struct
import threading

log = logging.getLogger(__name__)

# linux/input.h: a timeval (two longs on 64-bit) followed by type, code, value.
EVENT_FMT  = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FMT)

EV_KEY, EV_ABS = 0x01, 0x03
BTN_TOUCH    = 0x14A
ABS_X, ABS_Y = 0x00, 0x01
# Multitouch position. The 10.1" panel's controller reports through these and
# never emits ABS_X/ABS_Y at all, while still DECLARING absinfo for them - so it
# is found by find_device() and then appears dead, because no coordinate ever
# arrives. Both spellings are accepted; a device only ever uses one.
ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 0x35, 0x36


def _abs_max(fd, axis):
    """Upper bound of an absolute axis, or 0 if the device has not got one."""
    # EVIOCGABS(axis) is _IOR('E', 0x40 + axis, struct input_absinfo), and
    # input_absinfo is six int32: value, minimum, maximum, fuzz, flat, resolution.
    buf = bytearray(24)
    nr  = 0x40 + axis
    try:
        fcntl.ioctl(fd, (2 << 30) | (24 << 16) | (ord("E") << 8) | nr, buf)
    except OSError:
        return 0
    return struct.unpack("6i", buf)[2]


def find_device():
    """The first evdev device with both absolute axes: the touchscreen.

    Matched on capability rather than on /dev/input/event0, which is not a
    stable name on someone else's Pi, or on the controller's model name, which
    is not the same on every Touch Display 2. Returns (path, max_x, max_y).

    Note that declaring these axes is not the same as reporting through them:
    the 10.1" panel answers the absinfo query with its full 1199x1919 range and
    then sends every coordinate as ABS_MT_POSITION_*. Finding the device says
    nothing about which events it will emit.
    """
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            mx, my = _abs_max(fd, ABS_X), _abs_max(fd, ABS_Y)
        finally:
            os.close(fd)
        if mx and my:
            return path, mx, my
    return None, 0, 0


class TouchReader:
    """Taps from the panel, mapped into the landscape render space.

    The blocking read lives on its own thread and taps are handed over a queue,
    so an idle or chattering touchscreen can never hold up the frame loop.
    """

    def __init__(self, w, h, fb_w, fb_h, rotate_deg=0):
        self.w, self.h = w, h
        self.fb_w, self.fb_h = fb_w, fb_h
        # Degrees rather than a PIL constant: this module reads evdev records
        # and nothing else, and it is worth keeping it that way. The build owns
        # the single figure and hands the same one to the framebuffer.
        self.rotate_deg = rotate_deg % 360
        self.taps = queue.Queue()
        self.path, self._mx, self._my = find_device()

    def start(self):
        """Begin reading. False (and a warning) if there is no touchscreen."""
        if not self.path:
            log.warning("No touchscreen found; touch controls are off.")
            return False
        threading.Thread(target=self._run, daemon=True).start()
        log.info("Touch on %s (%d x %d).", self.path, self._mx, self._my)
        return True

    def get(self):
        """The next tap as (x, y) in render coordinates, or None."""
        try:
            return self.taps.get_nowait()
        except queue.Empty:
            return None

    def _map(self, tx, ty):
        """Controller coordinates -> render coordinates.

        The touchscreen always reports in the panel's native portrait frame,
        whatever the build draws, so this undoes exactly the rotation the frame
        took on its way to the framebuffer. Get it wrong and every tap lands
        somewhere else - a quarter turn away at 90 degrees, diagonally opposite
        at 180.

        The 180 case is the 10.1" build, whose panel is mounted upside down
        because that is the only orientation its stand fits. Note that the DSI
        overlay's own invx/invy would do the same job in the driver - do not
        set both, or they cancel and touch comes back inverted.

        Verify by tapping four corners rather than by reasoning about it - axis
        inversion is the classic bug here and it is cheap to check.
        """
        px = tx / self._mx * (self.fb_w - 1)
        py = ty / self._my * (self.fb_h - 1)
        if self.rotate_deg == 90:
            return int(self.w - 1 - py), int(px)
        if self.rotate_deg == 180:
            return int(self.w - 1 - px), int(self.h - 1 - py)
        if self.rotate_deg == 270:
            return int(py), int(self.h - 1 - px)
        return int(px), int(py)

    def _run(self):
        x = y = None
        with open(self.path, "rb", buffering=0) as dev:
            while True:
                data = dev.read(EVENT_SIZE)
                if not data:
                    return
                _, _, etype, code, value = struct.unpack(EVENT_FMT, data)
                if etype == EV_ABS and code in (ABS_X, ABS_MT_POSITION_X):
                    x = value
                elif etype == EV_ABS and code in (ABS_Y, ABS_MT_POSITION_Y):
                    y = value
                elif etype == EV_KEY and code == BTN_TOUCH and value == 0:
                    # Fired on release rather than press, so that resting a
                    # finger on the panel does nothing until it is lifted.
                    if x is not None and y is not None:
                        log.debug("tap raw=(%d, %d) -> %s", x, y, self._map(x, y))
                        self.taps.put(self._map(x, y))
                    x = y = None


if __name__ == "__main__":
    import time

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    reader = TouchReader(1280, 720, 720, 1280, rotate_deg=90)
    if reader.start():
        log.info("Tap the corners; Ctrl-C to stop.")
        while True:
            time.sleep(0.05)
