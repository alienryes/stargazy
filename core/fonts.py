"""Font loading, with two fallbacks.

IBM Plex Sans (OFL, Debian's fonts-ibm-plex). Drawn for technical material,
holds up at a distance, and its figures are tabular so nothing shifts as the
numbers change. It runs about 11% narrower than DejaVu at the same nominal size,
which is why the sizes each build chooses are larger than a DejaVu original
would be - the aim is to match the OPTICAL size, not the point size.
"""
from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path("/usr/share/fonts/truetype/ibm-plex")
FONT_FALLBACK_DIR = Path("/usr/share/fonts/truetype/dejavu")

_DEJAVU = {"IBMPlexSans-Regular.ttf": "DejaVuSans.ttf",
           "IBMPlexSans-SemiBold.ttf": "DejaVuSans-Bold.ttf",
           "IBMPlexSans-Bold.ttf": "DejaVuSans-Bold.ttf"}


def font(name, size):
    """Plex, falling back to DejaVu, falling back to whatever Pillow has.

    Plex arrives via setup.sh rather than with the OS, so an install that
    skipped it would otherwise drop to Pillow's default bitmap face and render
    a dashboard nobody could read from across a room. DejaVu is on every
    Raspberry Pi OS image, so the middle rung always exists.
    """
    for path in (FONT_DIR / name, FONT_FALLBACK_DIR / _DEJAVU[name]):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default()
