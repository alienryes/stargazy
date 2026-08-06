"""The real sky, projected onto the canvas from a chosen direction.

The panel has no idea which way it is facing and never will, so the direction is
a setting rather than something to infer: pick where the "window" points and the
stars behind the dashboard are then the ones actually in that part of the sky,
turning as the Earth turns rather than drifting because a constant says so.

Projection is linear in azimuth and altitude - the same convention as the
targets page's plot, and honest at these fields of view. It is not a gnomonic
camera and does not pretend to be: the point is a recognisable sky, not an
astrometric one.

Catalogue: Yale Bright Star Catalogue (VizieR V/50, Hoffleit & Warren) via CDS
Strasbourg, trimmed to magnitude 6.5 - the naked-eye limit under a genuinely
dark sky, and therefore the honest cut for a display about dark skies. A first
attempt stopped at 5.6, which put only ~170 stars in a field and read as a
half-empty sky rather than a real one.
"""
import math
import random
from pathlib import Path

from core.positions import alt_az

CATALOGUE = Path(__file__).resolve().parent / "data" / "stars.tsv"

# Brightest and faintest the renderer maps between. Sirius is -1.46 and the
# catalogue stops at 5.6; anchoring to fixed values rather than to the data
# means one faint star dropping out cannot re-scale the whole sky.
MAG_BRIGHT, MAG_FAINT = -1.5, 6.5

_CATALOGUE = None


def catalogue():
    """[(ra_deg, dec_deg, mag)], loaded once."""
    global _CATALOGUE
    if _CATALOGUE is None:
        rows = []
        for line in CATALOGUE.read_text().splitlines():
            if not line.strip():
                continue
            ra, dec, mag = line.split("\t")
            rows.append((float(ra), float(dec), float(mag)))
        _CATALOGUE = rows
    return _CATALOGUE


def _appearance(mag, min_size=1):
    """(base brightness, drawn size) for a magnitude.

    `min_size` raises the floor for a panel whose pixels are physically coarser
    or which is read from further away. It is a property of the hardware, not of
    the sky: the size bands below were calibrated on the 5" panel at 0.088mm per
    pixel, and the same bands on the 10.1" at 0.113mm draw a sky with a fifth of
    the lit area per megapixel, because a portrait aspect narrows the field to
    56 degrees and spreads a third fewer stars over 2.5x the pixels. Widening
    the field cannot close that honestly - it would need 242 degrees of azimuth
    in one flat window - so the drawn area per star is the lever that is left.

    NOT linear in magnitude. Magnitude is already logarithmic and the catalogue
    is overwhelmingly faint - two thirds of it is dimmer than magnitude 4.5 - so
    a linear map put almost every star near the floor, where the conditions gain
    and the twinkle then pushed it under the cull threshold and the sky rendered
    empty. This is the recurring trap in this project: an effect that disappears
    in the very conditions it is meant to represent.

    A per-magnitude ratio keeps the ordering honest (Sirius still dominates)
    while leaving the faint majority visible, and the floor guarantees a star
    that is in the sky is on the panel.
    """
    # Calibrated by MEASUREMENT against the seeded field this replaces, which
    # drew from uniform(0.35, 1.0) for a mean of about 0.67. A real catalogue is
    # overwhelmingly faint, so steeper ratios piled most stars onto the floor:
    # counting lit pixels in a fixed strip of sky gave 117 against the old
    # field's 257, i.e. a sky half as present. This ratio and floor put the mean
    # back around 0.65 while keeping the ordering - Sirius still dominates.
    base = max(0.55, min(1.0, 0.93 ** (mag - MAG_BRIGHT)))
    # Size bands are set for a magnitude 6.5 catalogue, where a 3.0 cut left
    # 99% of stars as single pixels and the sky lost half its drawn area
    # (measured: 121 lit pixels against the old field's 257 in the same strip).
    # It is not only a rendering convenience - a brighter star really does read
    # as larger to the eye, through glare - but the honest limit is that a
    # single pixel is 0.11mm on this panel and simply is not visible from across
    # a room, so the faint majority is carried by brightness rather than size.
    if mag < 1.5:
        size = 3
    elif mag < 4.0:
        size = 2
    else:
        size = 1
    return base, max(size, min_size)


def project_point(az, alt, w, h, az_centre=180.0, alt_centre=45.0, fov_vertical=90.0):
    """One alt-az direction as (x, y, inside_view) canvas coordinates.

    Shared by the starfield and by the meteor radiants, so a radiant lands where
    the stars around it land and the two cannot drift apart.

    The coordinates are returned whether or not the direction is in view, and
    the caller decides what that means. A star outside the view is not drawn; a
    radiant outside it still governs its meteors, because the shower is
    overhead either way - the window simply is not pointed at it.
    """
    fov_h = fov_vertical * (w / h)
    # Signed angular distance from the centre of view, wrapped to +-180.
    daz = (az - az_centre + 180.0) % 360.0 - 180.0
    dalt = alt - alt_centre
    x = w / 2.0 + (daz / fov_h) * w
    y = h / 2.0 - (dalt / fov_vertical) * h
    inside = abs(daz) <= fov_h / 2.0 and abs(dalt) <= fov_vertical / 2.0
    return x, y, inside


def project(obs, w, h, az_centre=180.0, alt_centre=45.0, fov_vertical=90.0,
            min_size=1):
    """Stars currently above the horizon and inside the view, in Sky's format.

    Returns (x, y, base, twinkle phase, twinkle speed, size) tuples, which is
    exactly what Sky.draw_stars already consumes - so the drawing, the twinkle
    and the conditions-reactive gain are all unchanged and only the source of
    the positions is different.

    The twinkle phases come from a dedicated random stream keyed by catalogue
    index, NOT the global one: they must be stable as stars enter and leave the
    view, and nothing here may disturb the sequence the clouds and meteors draw
    from.
    """
    stars = []
    for i, (ra, dec, mag) in enumerate(catalogue()):
        alt, az = alt_az(obs, ra, dec)
        if alt <= 0.0:
            continue                      # below the horizon: genuinely not there
        x, y, inside = project_point(az, alt, w, h,
                                     az_centre, alt_centre, fov_vertical)
        if not inside:
            continue
        base, size = _appearance(mag, min_size)
        rng = random.Random(i)
        stars.append((int(x), int(y), base,
                      rng.uniform(0.0, 2 * math.pi), rng.uniform(0.4, 2.6), size))
    return stars
