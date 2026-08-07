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


# Twinkle period, as an angular speed in radians per second of wall clock.
# 0.2-1.3 gives 4.8-31 s a cycle. Real scintillation is tens of hertz and
# cannot be drawn at 12 fps at all - it would alias - so this is stylised
# whatever it is set to, and the useful question is only whether the field
# looks alive or looks like it is breathing. The earlier 0.4-2.6 read as the
# latter, especially once the field got denser.
TWINKLE_SPEED = (0.2, 1.3)

# Scintillation grows with the airmass the light crosses, as roughly
# airmass^1.75 (Young). Airmass is close enough to 1/sin(alt) well above the
# horizon and runs away below it, so the factor is clamped: by the clamp a star
# is already twinkling eight times as hard as one overhead, and the difference
# between that and eighty is not something a panel can show.
SCINT_EXP = 1.75
SCINT_MAX = 8.0


def scintillation(alt):
    """How much harder a star at this altitude twinkles than one overhead.

    Returns 1.0 at the zenith, rising towards the horizon. This is why the
    twinkle is not one number: a star overhead is seen through the least
    atmosphere there is and sits very nearly steady, while one low down is
    seen through several times as much and genuinely shimmers. Applying a
    single amplitude to the whole field makes the zenith restless and the
    horizon tame, which is backwards on both counts.
    """
    return min(SCINT_MAX, (1.0 / math.sin(math.radians(max(alt, 1.0)))) ** SCINT_EXP)


def px_per_degree(h, fov_vertical):
    """Canvas pixels per degree at the CENTRE of the view.

    Gnomonic scale grows away from the axis, roughly as 1/cos^2 of the angle
    off it, so no single number describes the whole field. This is the value at
    the axis, and it is what the meteor code wants: that converts a pixel
    distance from the radiant into an angle only to shorten trails pointing
    towards the observer, which is a soft effect rather than a measurement.

    It lives here so it cannot drift from the projection it describes.
    """
    return math.radians(1.0) * (h / 2.0) / math.tan(math.radians(fov_vertical) / 2.0)


def project_point(az, alt, w, h, az_centre=180.0, alt_centre=45.0, fov_vertical=90.0):
    """One alt-az direction as (x, y, inside_view) canvas coordinates.

    GNOMONIC, about the camera axis - the tangent-plane projection a lens
    records. The obvious alternative, and what this used to do, is to map
    azimuth and altitude straight onto x and y. That is a plate carree, and it
    is wrong in a way that is easy to miss because it looks fine near the
    horizon: one degree of AZIMUTH is only cos(alt) degrees of sky, so
    horizontal distances come out exaggerated by 1/cos(alt) - 1.41x at 45
    degrees altitude, 3.9x at 75, without limit at the zenith. Constellations
    overhead were smeared sideways, and a star passing near the zenith crossed
    the whole panel in a minute because azimuth is degenerate there.

    Gnomonic has no such pole: it is defined relative to where the camera
    points, so the zenith is an ordinary direction. Scale still varies across
    the field - every flat map of a sphere distorts something - but it varies
    smoothly with distance from the axis instead of blowing up along a line the
    sky happens to sweep through.

    Shared by the starfield and by the meteor radiants, so a radiant lands
    where the stars around it land and the two cannot drift apart.

    The coordinates are returned whether or not the direction is in view, and
    the caller decides what that means. A star outside the view is not drawn; a
    radiant outside it still governs its meteors, because the shower is
    overhead either way - the window simply is not pointed at it.
    """
    a, e = math.radians(az), math.radians(alt)
    a0, e0 = math.radians(az_centre), math.radians(alt_centre)
    sa, ca, se, ce = math.sin(a), math.cos(a), math.sin(e), math.cos(e)
    sa0, ca0, se0, ce0 = math.sin(a0), math.cos(a0), math.sin(e0), math.cos(e0)

    # East, North, Up. `right` is the direction of increasing azimuth at the
    # axis and `up` that of increasing altitude, so the screen keeps the same
    # handedness the plate carree had: x grows eastward, y grows downward.
    vx, vy, vz = sa * ce, ca * ce, se
    axis = (sa0 * ce0, ca0 * ce0, se0)
    right = (ca0, -sa0, 0.0)
    up = (-sa0 * se0, -ca0 * se0, ce0)

    cosc = vx * axis[0] + vy * axis[1] + vz * axis[2]
    xr = vx * right[0] + vy * right[1] + vz * right[2]
    yu = vx * up[0] + vy * up[1] + vz * up[2]
    scale = (h / 2.0) / math.tan(math.radians(fov_vertical) / 2.0)

    if cosc <= 1e-6:
        # At or behind the tangent plane there is no finite projection. A
        # radiant there still has a bearing, though, and its meteors have to
        # sweep in from the right edge, so it is placed far off-canvas along
        # that bearing rather than being given a wrapped position that would
        # point them the wrong way. Never in view.
        n = math.hypot(xr, yu) or 1.0
        k = 10.0 * max(w, h)
        return w / 2.0 + xr / n * k, h / 2.0 - yu / n * k, False

    x = w / 2.0 + (xr / cosc) * scale
    y = h / 2.0 - (yu / cosc) * scale
    return x, y, (0.0 <= x < w and 0.0 <= y < h)


def project(obs, w, h, az_centre=180.0, alt_centre=45.0, fov_vertical=90.0,
            min_size=1):
    """Stars currently above the horizon and inside the view, in Sky's format.

    Returns (x, y, base, twinkle phase, twinkle speed, size, scintillation)
    tuples, which is what Sky.draw_stars consumes - so the drawing and the
    conditions-reactive gain are unchanged and only the source of the positions
    is different. The last field is the per-star twinkle scaling from its
    altitude; Sky turns it into an amplitude, so both knobs stay in one place.

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
                      rng.uniform(0.0, 2 * math.pi),
                      rng.uniform(*TWINKLE_SPEED), size,
                      scintillation(alt)))
    return stars
