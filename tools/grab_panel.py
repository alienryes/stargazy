"""Capture what the panel is ACTUALLY showing, straight off /dev/fb0.

Every other picture of this display is a re-render: `display.py --save` runs the
draw path again and shows what the code *would* produce. That is the right tool
for documenting a layout, and the wrong one for answering "what is on the screen
right now" - it cannot show the control strip, the live night filter, the page
the rotation happens to be on, or anything that has drifted between the running
build and the working tree.

This reads the framebuffer instead, so the answer comes from the panel.

    python tools/grab_panel.py --out /tmp/panel.png            # 10.1 inch
    python tools/grab_panel.py --rotate 270 --out /tmp/panel.png   # 5 inch

WHY --rotate: the framebuffer holds the image in the panel's own orientation,
not the one a person reads. The 5" build renders 1280x720 landscape and writes
it transposed, so 270 turns it back. The 10.1" build renders portrait but turns
the image 180 in the render path, the panel being mounted upside down, so 180
undoes that. Neither value can be detected from the framebuffer.

THE PIXEL FORMAT IS DERIVED, NOT GUESSED. `Framebuffer.to_bytes` packs 16bpp as
RGB565 little-endian and 32bpp as B,G,R,X, so the inverses are `BGR;16` and
`BGRX`. This matters more than it looks: `RGBX` also parses 32bpp data without
complaint and yields a picture that looks plausible while red and blue are
swapped. Measured against the palette, `BGRX` matched NOMINAL on 48,466 pixels
and `RGBX` on none. Do not pick a mode by trying them until one works.

Pillow can only read these formats, not write them - there is no 565 packer at
all - which is why `core/panel.py` packs by hand.

A read is not atomic against a daemon writing at 12 fps, so a capture may hold
parts of two frames. The dashboard is static enough that this rarely shows;
the sky layer behind it can tear.
"""
import argparse
from pathlib import Path

from PIL import Image

FB_DEV = "/dev/fb0"
SYS = "/sys/class/graphics/fb0"

# Inverse of Framebuffer.to_bytes, keyed by depth.
RAW_MODE = {16: "BGR;16", 32: "BGRX"}

ROTATION = {90: Image.ROTATE_90, 180: Image.ROTATE_180, 270: Image.ROTATE_270}


def _attr(name):
    return Path(SYS, name).read_text().strip()


def grab(dev=FB_DEV, rotate=0):
    """The framebuffer as a PIL image, in reading orientation."""
    w, h = (int(v) for v in _attr("virtual_size").split(","))
    bpp = int(_attr("bits_per_pixel"))
    if bpp not in RAW_MODE:
        raise SystemExit(f"{bpp}bpp framebuffers are not supported; "
                         f"known depths are {sorted(RAW_MODE)}")
    data = Path(dev).read_bytes()
    want = w * h * bpp // 8
    if len(data) < want:
        raise SystemExit(f"{dev} gave {len(data)} bytes, expected {want} "
                         f"for {w}x{h} at {bpp}bpp")
    img = Image.frombytes("RGB", (w, h), data[:want], "raw", RAW_MODE[bpp])
    return img if not rotate else img.transpose(ROTATION[rotate])


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default="panel.png", help="where to write the PNG")
    p.add_argument("--rotate", type=int, default=0, choices=sorted(ROTATION),
                   help="turn the capture into reading orientation "
                        "(5 inch: 270, 10.1 inch: 180)")
    p.add_argument("--dev", default=FB_DEV)
    args = p.parse_args()

    img = grab(args.dev, args.rotate)
    img.save(args.out)
    print(f"{args.dev} {_attr('virtual_size')} at {_attr('bits_per_pixel')}bpp "
          f"-> {args.out} {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
