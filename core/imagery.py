"""Real pictures of real things: deep-sky cutouts, the lunar frame, the Sun.

All three render on black, so they composite onto the animated sky with no
panel edges. All three are network calls and belong on the data thread; none
may be called from a render loop.
"""
import email.utils
import io
import logging
import os
import re
from datetime import datetime, timedelta, timezone
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


# Real solar imagery from SDO's HMI instrument - the continuum frame, which is
# the white-light view and therefore the one with the sunspots actually in it.
# The direct analogue of the Dial-a-Moon frame above: disc centred on black,
# ready to composite.
#
# ⇒ THE 1024 FRAME, FOR A MEASURED REASON. All three published sizes carry a
# caption strip along the bottom. At 1024 and 2048 a disc-sized circular mask
# removes it outright - zero caption pixels survive - but at 512 the caption is
# proportionally larger and the disc sits 10 px high, leaving 832 of them inside
# the mask. The 2048 frame is 38 px off centre and four times the bytes. Only
# the 1024 frame is both centred and self-cleaning.
#
# ⇒ THE PHOTOGRAPH REPLACED A DRAWN DISC, AND FIXED IT. Marks plotted from
# SWPC's regional report sat consistently EAST of the real spots, because that
# report is a daily snapshot and rotation carries a group about 13.2 degrees a
# day - up to 110 px at this scale by the time the next one is issued. A
# photograph has no such lag: it shows the spots where they were at its own
# timestamp. This was found by overlaying the computed positions on the frame,
# which no check of the projection could have revealed, because the projection
# was right and its input was stale.
SUN_CACHE = CACHE_ROOT / "sun"
SDO_URL = "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_HMIIC.jpg"
SUN_FRAME = SUN_CACHE / "continuum.jpg"
# Measured, and stable from 5% to 20% of peak brightness: 940 px across a 1024
# frame, centred to within half a pixel. Higher thresholds read smaller because
# of limb darkening, not because the disc is.
SUN_DISC_FRAC = 940 / 1024
SUN_REFRESH_MINUTES = 30
# Spots drift about 0.55 degrees an hour, which at a 250 px radius is roughly
# 2 px. So a frame a few hours old is honest, and unlike the Moon there is no
# phase to get wrong - the refusal here is about a picture that has stopped
# describing today, not one that is subtly mistimed.
SUN_MAX_AGE_HOURS = 12


def _http_date(value):
    """A Last-Modified header as an aware UTC datetime, or None."""
    try:
        return email.utils.parsedate_to_datetime(value).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def sun_image():
    """(image, observed_at) for the Sun's disc as photographed, or (None, None).

    NETWORK - background thread only; never call this from the render loop.

    ⇒ THE CACHED FILE'S MTIME IS SET TO THE FRAME'S OWN TIMESTAMP, not to when
    it was fetched. The age that matters is the picture's, not the download's,
    and keeping one number rather than a file plus a sidecar means the two
    cannot disagree.

    Returns None rather than an old frame past the age limit, so a caller falls
    back to something computed from current data instead of showing a disc that
    has rotated on. Same rule as moon_image, for the same reason.
    """
    SUN_CACHE.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    def cached(limit):
        if not SUN_FRAME.exists():
            return None, None
        seen = datetime.fromtimestamp(SUN_FRAME.stat().st_mtime, timezone.utc)
        if now - seen > limit:
            return None, None
        try:
            return Image.open(SUN_FRAME).convert("RGB"), seen
        except Exception:
            return None, None

    fresh, seen = cached(timedelta(minutes=SUN_REFRESH_MINUTES))
    if fresh is not None:
        return fresh, seen

    try:
        r = requests.get(SDO_URL, timeout=30)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        SUN_FRAME.write_bytes(r.content)
        observed = _http_date(r.headers.get("last-modified")) or now
        os.utime(SUN_FRAME, (observed.timestamp(), observed.timestamp()))
        log.info("Solar frame fetched, observed %s.", observed.strftime("%H:%M UTC"))
        return img, observed
    except Exception as e:
        log.warning("Solar frame unavailable (%s).", e)
        return cached(timedelta(hours=SUN_MAX_AGE_HOURS))


def paste_sun(img, photo, cx, cy, r):
    """Composite an SDO continuum frame as the solar disc.

    The mask is what removes the caption strip SDO prints along the bottom of
    every frame, so it is load-bearing rather than cosmetic. Feathered like the
    lunar one because the disc's size in the frame moves with the Earth-Sun
    distance - about 1.7% either way over a year - and a hard edge would show
    that as a black rim in January.
    """
    d = int(2 * r / SUN_DISC_FRAC)
    disc = photo.resize((d, d), Image.LANCZOS)
    mask = Image.new("L", (d, d), 0)
    inset = (d - 2 * r) // 2
    ImageDraw.Draw(mask).ellipse([inset, inset, d - inset, d - inset], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2))
    img.paste(disc, (cx - d // 2, cy - d // 2), mask)


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
