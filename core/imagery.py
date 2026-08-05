"""Real pictures of real things: deep-sky cutouts and the current lunar frame.

Both render on black, so they composite onto the animated night sky with no
panel edges. Both are network calls and belong on the data thread; neither may
be called from a render loop.
"""
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter

from core.palette import MOON

log = logging.getLogger(__name__)

# Beside the entry point, not beside this file: a build's display.py and core/
# are siblings in the install directory, so this keeps the cache where it has
# always been rather than burying it inside the engine.
CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache"

# Real sky cutouts from the CDS hips2fits service, which resolves the object
# name itself and renders the actual patch of sky. That beats an image-library
# search: coverage is total (NGC and LBN designations work as well as Messier)
# and it cannot return a confidently-wrong picture of something else. DSS2
# colour renders on black, so the tiles composite onto the night sky cleanly.
CACHE_DIR = CACHE_ROOT / "dso"
HIPS_URL = "https://alasky.cds.unistra.fr/hips-image-services/hips2fits"

# Real lunar imagery from NASA's Scientific Visualization Studio (Ernie Wright's
# Dial-a-Moon). The API resolves the frame for a given hour, so the phase, the
# libration and the terminator are all as they actually are that night -
# including WHICH LIMB IS LIT, which is why nothing here mirrors anything.
MOON_CACHE = CACHE_ROOT / "moon"
DIALAMOON_URL = "https://svs.gsfc.nasa.gov/api/dialamoon/"
MOON_CACHE_KEEP = 4
# The disc is 658px across, centred, in a 730px frame. Scaling by the frame
# rather than by a measured bounding box keeps the Moon's real change of
# apparent size with distance - and a thin crescent has no bounding box worth
# measuring anyway, since most of the disc is only lit by earthshine.
MOON_DISC_FRAC = 658 / 730


def cutout(obj_id, size_arcmin, px=200):
    """Cached DSS2 colour cutout for an object, or None. NETWORK - background
    thread only; never call this from the render loop."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / (re.sub(r"[^A-Za-z0-9]+", "_", obj_id).strip("_") + ".jpg")
    if path.exists():
        try:
            return Image.open(path).convert("RGB")
        except Exception:
            path.unlink(missing_ok=True)
    # Frame the object rather than the pixel grid: catalogue size in arcmin,
    # with margin, clamped so a tiny galaxy is not a dot and M31 is not a smear.
    fov = min(max(size_arcmin * 1.8, 12.0), 50.0) / 60.0
    try:
        r = requests.get(HIPS_URL, timeout=25, params={
            "hips": "CDS/P/DSS2/color", "object": obj_id, "fov": f"{fov:.4f}",
            "width": px, "height": px, "format": "jpg"})
        r.raise_for_status()
        path.write_bytes(r.content)
        img = Image.open(path).convert("RGB")
        log.info("Cutout fetched for %s (fov %.1f')", obj_id, fov * 60)
        return img
    except Exception as e:
        log.warning("Cutout for %s failed: %s", obj_id, e)
        return None


def _prune(d, keep):
    files = sorted(d.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[keep:]:
        p.unlink(missing_ok=True)


def moon_image():
    """(image, facts) for the Moon as it actually looks this hour, or (None, {}).

    NETWORK - background thread only; never call this from the render loop.

    Deliberately does NOT fall back to a cached older frame: the phase moves
    about 12 degrees a day, so yesterday's picture would be wrong. Returning
    None instead selects the parametric drawing, which is computed from current
    data and therefore correct, if simpler.

    The same response carries age, distance, apparent diameter and the
    sub-earth point (libration) - all of it already paid for by the request that
    fetches the picture, and all of it discarded until now.
    """
    MOON_CACHE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:00")
    try:
        meta = requests.get(DIALAMOON_URL + stamp, timeout=20)
        meta.raise_for_status()
        facts = meta.json()
        url  = facts["image"]["url"]
        # The filename comes from a network response, so constrain it to
        # known-safe characters: anything a path could be built from is
        # stripped ("\" would traverse on Windows, and a bare ".." names the
        # cache directory itself).
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", url.rsplit("/", 1)[-1])
        if not name.strip("._-"):
            name = "frame.jpg"
        path = MOON_CACHE / name
        if not path.exists():
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            path.write_bytes(r.content)
            log.info("Moon frame fetched: %s", path.name)
            _prune(MOON_CACHE, MOON_CACHE_KEEP)
        return Image.open(path).convert("RGB"), facts
    except Exception as e:
        log.warning("Moon frame unavailable (%s); drawing the phase instead.", e)
        return None, {}


def paste_moon(img, photo, cx, cy, r, ring=True):
    """Composite a Dial-a-Moon frame as the moon disc.

    The mask edge is feathered because the disc does not always fill it: the
    Moon is nearer at perigee than at apogee by about 4%, and a hard edge would
    show that as a black rim against the navy sky on the far weeks.
    """
    d     = int(2 * r / MOON_DISC_FRAC)
    disc  = photo.resize((d, d), Image.LANCZOS)
    mask  = Image.new("L", (d, d), 0)
    inset = (d - 2 * r) // 2
    ImageDraw.Draw(mask).ellipse([inset, inset, d - inset, d - inset], fill=255)
    mask  = mask.filter(ImageFilter.GaussianBlur(2))
    img.paste(disc, (cx - d // 2, cy - d // 2), mask)
    if ring:
        ImageDraw.Draw(img).ellipse([cx - r, cy - r, cx + r, cy + r],
                                    outline=MOON, width=3)
