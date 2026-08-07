"""Prove the framebuffer fast paths emit exactly the shipped bytes.

`Framebuffer.to_bytes` short-circuits two cases at 32bpp - "off" through PIL's
raw BGRX writer, "red" through a fused luma pack - because the general path
cost 98 ms a frame on the 10.1" panel against an 83 ms budget. A faster path
that changes a pixel is not a faster path, so both are checked here against a
frozen copy of the original implementation.

Both depths are covered. The 5" build is 16bpp and takes none of the
shortcuts, but it shares this file, so "unchanged" has to be demonstrated
there rather than argued.

    python tools/check_fb_paths.py
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.night import night_filter  # noqa: E402
from core.panel import Framebuffer  # noqa: E402

MODES = ("off", "dim", "red")
DIM = 45


def original(img, rotate, fb_w, fb_h, bpp, night, dim):
    """The implementation as it stood before the fast paths, verbatim."""
    rot = img if rotate is None else img.transpose(rotate)
    if rot.size != (fb_w, fb_h):
        rot = rot.resize((fb_w, fb_h))
    arr = np.asarray(rot, dtype=np.uint16)
    arr = night_filter(arr, night, dim)
    if bpp == 32:
        out = np.empty((fb_h, fb_w, 4), np.uint8)
        out[:, :, 0] = arr[:, :, 2]
        out[:, :, 1] = arr[:, :, 1]
        out[:, :, 2] = arr[:, :, 0]
        out[:, :, 3] = 0
        return out.tobytes()
    packed = (((arr[:, :, 0] >> 3) << 11)
              | ((arr[:, :, 1] >> 2) << 5)
              | (arr[:, :, 2] >> 3))
    return packed.astype("<u2").tobytes()


def sample(w, h):
    """Content chosen so a channel swap cannot pass by accident.

    A grey or symmetric image survives getting R and B the wrong way round,
    which is the single most likely way for this to break. Every channel here
    varies independently, and the corners are saturated primaries.
    """
    x = np.linspace(0, 255, w, dtype=np.uint16)[None, :]
    y = np.linspace(0, 255, h, dtype=np.uint16)[:, None]
    arr = np.zeros((h, w, 3), np.uint8)
    arr[:, :, 0] = (x + y) % 256
    arr[:, :, 1] = (x * 2 + y // 3) % 256
    arr[:, :, 2] = (x // 5 + y * 3) % 256
    arr[:8, :8] = (255, 0, 0)
    arr[:8, -8:] = (0, 255, 0)
    arr[-8:, :8] = (0, 0, 255)
    arr[-8:, -8:] = (255, 255, 255)
    return Image.fromarray(arr, "RGB")


def main():
    cases = [
        # name, canvas, framebuffer, rotate, bpp   - the two real builds
        ("build10 portrait 32bpp", (1200, 1920), (1200, 1920), None, 32),
        ("build5 landscape 16bpp", (1280, 720), (720, 1280), Image.ROTATE_90, 16),
        # and 16bpp unrotated, so a rotate of None is not what carries the pass
        ("16bpp, no rotation", (400, 300), (400, 300), None, 16),
    ]
    fails = 0
    checked = 0
    for name, (w, h), (fw, fh), rot, bpp in cases:
        img = sample(w, h)
        fb = Framebuffer(w, h, fw, fh, rotate=rot, dev="/nonexistent", bpp=bpp)
        for mode in MODES:
            want = original(img, rot, fw, fh, bpp, mode, DIM)
            got = fb.to_bytes(img, mode, DIM)
            checked += 1
            if got == want:
                print(f"  PASS  {name:<24} {mode:<4} "
                      f"{len(got):>9} bytes  identical")
                continue
            fails += 1
            a = np.frombuffer(got, np.uint8).astype(np.int16)
            b = np.frombuffer(want, np.uint8).astype(np.int16)
            if a.size != b.size:
                print(f"  FAIL  {name:<24} {mode:<4} "
                      f"length {a.size} != {b.size}")
            else:
                d = np.abs(a - b)
                print(f"  FAIL  {name:<24} {mode:<4} "
                      f"max {int(d.max())} LSB on {int((d > 0).sum())} bytes")

    # An expected-size check, because a pack that emits half the bytes a panel
    # wants is the failure this file exists to make loud.
    for name, (w, h), (fw, fh), rot, bpp in cases:
        fb = Framebuffer(w, h, fw, fh, rotate=rot, dev="/nonexistent", bpp=bpp)
        want = fw * fh * bpp // 8
        got = len(fb.to_bytes(sample(w, h), "off", DIM))
        checked += 1
        if got != want:
            fails += 1
            print(f"  FAIL  {name:<24} size {got} != {want}")
        else:
            print(f"  PASS  {name:<24} size {got} bytes as the panel expects")

    print(f"\n  {checked} checks, "
          + ("ALL PASSED" if not fails else f"{fails} FAILED"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
