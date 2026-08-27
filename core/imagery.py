"""Real pictures of real things: deep-sky cutouts, the lunar frame, the Sun.

All three render on black, so they composite onto the animated sky with no
panel edges. All three are network calls and belong on the data thread; none
may be called from a render loop.
"""
import email.utils
import io
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFilter

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

# Objects whose cutout has already failed and been warned about.
#
# ⇒ BECAUSE SUCCESS IS CACHED TO DISK AND FAILURE IS NOT. A fetched image makes
# later refreshes return at path.exists() and log nothing, which is why the
# objects that work go quiet after their first fetch. A failure writes nothing,
# so a name the HiPS resolver cannot resolve is re-requested every refresh - a
# quarter of an hour apart, for the life of the process - and warned about every
# time. Measured over 24 h on the 10.1" panel, two such objects accounted for
# 188 warnings and nothing else warned at all.
#
# ⚠ THIS SHAPE FITS THIS CALL AND NO OTHER ONE IN core/. The moon frame is keyed
# on an hourly stamp so its URL moves on; the solar frame has its own time-based
# cache and falls back; aurora, Kp, weather and CelesTrak are whole-feed fetches
# where a repeated warning means "this feed is still down", which is information.
# Do not widen it.
#
# The request still goes out every refresh and success still logs, so a name
# that starts resolving announces itself. Suppressing the repeat costs no signal.
_CUTOUT_WARNED = set()

# Real lunar imagery from NASA's Scientific Visualization Studio (Ernie Wright's
# Dial-a-Moon). The API resolves the frame for a given hour, so the phase, the
# libration and the terminator are all as they actually are that night -
# including WHICH LIMB IS LIT, which is why nothing here mirrors anything.
MOON_CACHE = CACHE_ROOT / "moon"
DIALAMOON_URL = "https://svs.gsfc.nasa.gov/api/dialamoon/"
MOON_CACHE_KEEP = 4
# The disc is 658px across, centred, in a 730px frame. SCALING by the frame
# rather than by a measured bounding box is deliberate and stays: it keeps the
# Moon's real change of apparent size with distance, about 4% between perigee
# and apogee.
#
# ⚠ BUT THE MASK MUST NOT BE SIZED FROM IT. That is the same number used two
# ways - how big to draw the frame, and where the disc ends inside it - and only
# the first is constant. On 2026-08-17 the disc measured 0.865 of the frame
# against the 0.901 here, so a ring of the frame's black surround 12 px wide sat
# inside an opaque mask. Against the navy sky that is invisible; against bright
# cloud it read as a black halo, which is how it was found. See _disc_radius.
MOON_DISC_FRAC = 658 / 730

# A pixel counts as disc when it is this fraction of the frame's own peak
# brightness, with an absolute floor under it.
#
# ⇒ RELATIVE TO THE FRAME, BECAUSE A FIXED CUT CANNOT SERVE BOTH. Measured at
# their true limbs: the Sun lights 100% of the ring down to r=468 and only 37%
# at 470, where its edge is already falling away; the Moon lights about half,
# since the illuminated limb of a crescent is a semicircle at any phase. Any
# fixed fraction-of-ring rule that trims the Sun therefore crops the Moon. What
# separates them is that the surround is a true zero while a real limb is a
# large fraction of the disc's own brightness, whatever shape the lit part is.
DISC_EDGE_FRAC = 0.30
DISC_LIT = 24
# What fraction of a ring must be lit before that radius counts as disc.
#
# ⇒ HALF, BECAUSE OF THE GEOMETRY, AND THIS IS THE PART THAT MAKES IT ROBUST.
# The illuminated limb of a crescent is a SEMICIRCLE whatever the phase - the
# terminator is the inner boundary of the lit region, never the outer one - so
# any lit disc lights about half of the ring at its true edge, from new moon to
# full. The Sun lights all of it. Outside the limb the figure collapses to
# nearly nothing.
#
# ⚠ A COUNT OF PIXELS IS NOT A SUBSTITUTE. The first version took three lit
# pixels as proof, which JPEG ringing around a hard bright limb clears easily:
# on the solar frame it measured the disc as 299 px of a possible 300 and
# trimmed nothing at all.
DISC_MIN_LIT = 0.15
# Refuse a measurement below this fraction of the geometric circle. Detection
# failing open to a slightly large mask restores the old black rim; failing open
# to a small one would crop the Moon, which is worse and less obvious.
DISC_MIN_FRAC = 0.80

# Pull the mask this many frame pixels inside the measured limb.
#
# ⇒ BECAUSE THE EDGE IS A GRADIENT, NOT A LINE. Both feeds fall off over about
# three pixels - the solar frame runs 70, 20, 3 across r=468..471 - so the
# outermost radius that still counts as disc is already half sky, and a mask cut
# there compositing that gradient IS the dark rim. Cutting inside it costs two
# pixels of real disc on a body drawn 600 across, which is not visible, and
# removes the rim on both.
#
# Applied after detection rather than folded into the threshold because the
# alternative needed a statistic behaving identically on a fully lit disc and on
# a crescent, and there is none: at its true limb the Sun lights every sample
# and the Moon about half.
DISC_INSET = 3


def _disc_radius(photo, disc_frac):
    """Radius of the imaged disc, in the ORIGINAL frame's own pixels.

    ⚠ MEASURED FROM THE OUTERMOST LIT PIXEL, NOT BY KEYING OUT THE DARK. Keying
    on brightness across the whole disc looks like the obvious approach and does
    not work: the unlit part of a crescent reaches a true zero in these frames,
    so a darkness key punches holes in the Moon. Only the outer EDGE of the lit
    region is a reliable limb, and a crescent's lit edge is the limb, however
    thin the crescent.

    ⚠ AND MEASURED BEFORE THE RESIZE, NOT AFTER. Reducing a hard bright limb
    rings, and the overshoot sits just outside the true edge where a brightness
    search reads it as disc. Measured on the resized solar frame this returned
    the search limit unchanged and trimmed nothing, leaving the rim it exists to
    remove.

    The search starts at the nominal disc edge and never goes beyond it, which
    is what keeps SDO's corner caption out of the answer.
    """
    limit = disc_frac * min(photo.size) / 2.0
    grey = photo.convert("L")
    lit_above = max(DISC_LIT, DISC_EDGE_FRAC * grey.getextrema()[1])
    px = grey.load()
    w, h = photo.size
    cx, cy = w / 2.0, h / 2.0
    for r in range(int(limit), int(limit * DISC_MIN_FRAC), -1):
        lit = 0
        # Roughly one sample per pixel of circumference: dense enough that a
        # crescent's lit edge cannot be stepped over.
        steps = max(8, int(r * 6))
        for i in range(steps):
            a = 2.0 * math.pi * i / steps
            x, y = int(cx + r * math.cos(a)), int(cy + r * math.sin(a))
            if 0 <= x < w and 0 <= y < h and px[x, y] > lit_above:
                lit += 1
        if lit >= DISC_MIN_LIT * steps:
            return float(r - DISC_INSET)
    log.warning("No disc edge found within %d px; using the frame's nominal size.",
                int(limit))
    return float(limit)


def _mask_radius(photo, disc_frac, d, r):
    """The measured limb, expressed in the resized frame's pixels and capped.

    Capped at `r` because that circle is what excludes SDO's caption; a
    measurement may only ever shrink the mask.
    """
    return min(r, int(_disc_radius(photo, disc_frac) * d / photo.width))


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
        # So a name that fails again later is reported again rather than
        # silenced by a success it has since lost.
        _CUTOUT_WARNED.discard(obj_id)
        return img
    except Exception as e:
        # The repeats are still logged, at debug: the retry is worth being able
        # to see, and reporting a state change at the level of the state it
        # leaves is what keeps a recovery from being hidden by its own failure.
        log.log(logging.DEBUG if obj_id in _CUTOUT_WARNED else logging.WARNING,
                "Cutout for %s failed: %s", obj_id, e)
        _CUTOUT_WARNED.add(obj_id)
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

    The mask is what removes the caption strip SDO prints in the corners of
    every frame, so it is load-bearing rather than cosmetic. Its radius is
    MEASURED from the frame rather than taken from SUN_DISC_FRAC: the disc's
    size moves with the Earth-Sun distance, about 1.7% either way over a year,
    and the difference between the constant and the truth is drawn as a rim of
    the frame's own black surround.
    """
    d = int(2 * r / SUN_DISC_FRAC)
    disc = photo.resize((d, d), Image.LANCZOS)
    mask = Image.new("L", (d, d), 0)
    mr = _mask_radius(photo, SUN_DISC_FRAC, d, r)
    ImageDraw.Draw(mask).ellipse([d // 2 - mr, d // 2 - mr, d // 2 + mr, d // 2 + mr],
                                 fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(2))
    img.paste(disc, (cx - d // 2, cy - d // 2), mask)


def paste_moon(img, photo, cx, cy, r, ring=True):
    """Composite a Dial-a-Moon frame as the moon disc.

    The mask radius is MEASURED from the frame rather than taken from
    MOON_DISC_FRAC. The Moon is nearer at perigee than at apogee by about 4%, so
    the disc does not always fill the circle that constant describes, and
    whatever it does not fill is drawn as a rim of the frame's black surround.
    The edge is feathered on top of that, against the last pixel of rounding.

    The drawn disc still CHANGES SIZE with distance, which is the point of
    scaling by the frame: measuring the mask crops the surround without
    normalising the Moon to a constant size on the panel.
    """
    d     = int(2 * r / MOON_DISC_FRAC)
    disc  = photo.resize((d, d), Image.LANCZOS)
    mask  = Image.new("L", (d, d), 0)
    mr    = _mask_radius(photo, MOON_DISC_FRAC, d, r)
    ImageDraw.Draw(mask).ellipse([d // 2 - mr, d // 2 - mr, d // 2 + mr, d // 2 + mr],
                                 fill=255)
    mask  = mask.filter(ImageFilter.GaussianBlur(2))
    img.paste(disc, (cx - d // 2, cy - d // 2), mask)
    if ring:
        # On the measured limb, not on r: the outline exists to edge the disc,
        # and at apogee r is a dozen pixels clear of it.
        ImageDraw.Draw(img).ellipse([cx - mr, cy - mr, cx + mr, cy + mr],
                                    outline=MOON, width=3)
    # The MEASURED limb, for the same reason the ring uses it: an eclipse shadow
    # clipped to r rather than to this would spill past the drawn disc onto the
    # frame's black surround, most visibly at apogee.
    return mr


# Earth's umbra is not black. Sunlight refracted through the whole ring of
# Earth's atmosphere fills it, reddened by the same scattering that reddens a
# sunset, so a totally eclipsed Moon is a dim copper rather than absent. The
# colour is representative, not photometric: the true brightness ratio between
# umbra and full Moon is several thousand to one, and drawing that would render
# the eclipsed part invisible on a panel viewed in a lit room.
UMBRA_RGB = (78, 26, 14)
# Short of opaque, so the maria stay faintly readable through the shadow the way
# they do in a photograph of a real eclipse.
UMBRA_ALPHA = 0.88
# The umbral edge is genuinely soft - Earth's atmosphere has no sharp boundary
# and the penumbra grades into it - so a hard edge reads as drawn rather than
# cast. In units of the lunar radius, so both builds get the same softness.
UMBRA_SOFTNESS = 0.045
# ⇒ SUPERSAMPLED BECAUSE PIL ANTIALIASES NOTHING. An ellipse drawn straight into
# a mask has hard stair-stepped edges, and this one is a long shallow arc across
# a 600px disc, which is the worst case for it. Drawn at 4x into an L mask and
# reduced by area, per the same rule the starfield and the moon mask follow.
UMBRA_SUPERSAMPLE = 4


def shade_umbra(img, cx, cy, r, geom, limb=None):
    """Lay Earth's umbra over a moon disc already drawn at (cx, cy, r).

    `geom` is core.lunar.umbra_geometry(), whose offsets and radii are in units
    of the Moon's radius; `limb` is the measured limb from paste_moon, which is
    what the shadow is clipped to. Without one the drawn radius is used, which
    is right for the parametric fallback where the disc really is r across.

    Only the UMBRA is drawn. The penumbra dims the Moon by an amount that is
    imperceptible until it is nearly the umbra - a penumbral eclipse is famously
    hard to notice at all - so shading it would put a visible mark on the panel
    where an observer would see nothing.
    """
    limb = int(limb or r)
    n = 2 * limb * UMBRA_SUPERSAMPLE
    if n <= 0:
        return

    # The umbra, drawn as its own disc in supersampled pixels. Its centre is
    # offset from the Moon's by geom["dx"], geom["dy"] lunar radii - and it is
    # scaled by `limb` rather than r so that shadow and disc share one scale.
    ur = geom["umbra"] * limb * UMBRA_SUPERSAMPLE
    ux = n / 2.0 + geom["dx"] * limb * UMBRA_SUPERSAMPLE
    uy = n / 2.0 + geom["dy"] * limb * UMBRA_SUPERSAMPLE
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).ellipse([ux - ur, uy - ur, ux + ur, uy + ur],
                                 fill=int(255 * UMBRA_ALPHA))
    mask = mask.filter(ImageFilter.GaussianBlur(
        UMBRA_SOFTNESS * limb * UMBRA_SUPERSAMPLE))

    # Clipped to the lunar disc AFTER the blur, so the shadow's own edge is soft
    # while the limb stays crisp. Blurring the two together would fray the limb
    # and make the Moon look out of focus on the shadowed side only.
    disc = Image.new("L", (n, n), 0)
    ImageDraw.Draw(disc).ellipse([0, 0, n - 1, n - 1], fill=255)
    mask = ImageChops.multiply(mask, disc)
    mask = mask.resize((2 * limb, 2 * limb), Image.BOX)

    img.paste(Image.new("RGBA", (2 * limb, 2 * limb), UMBRA_RGB + (255,)),
              (cx - limb, cy - limb), mask)
