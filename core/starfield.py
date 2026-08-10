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

# Drawn size per magnitude, as (fainter-than, size) with the last entry the
# catch-all. A tuple rather than an if-ladder because the two panels need
# different tables and because the drawn area it implies is the thing that gets
# measured - see tools/star_field.py.
#
# SIZE_BANDS_DENSE is the original, and pairs with drawing the whole catalogue.
# SIZE_BANDS_SPARSE pairs with a limiting magnitude near what a real suburban
# sky reaches. Measured over the 5" field of view, the catalogue puts 1204 stars
# on the panel, of which 983 - 82% - are fainter than magnitude 5 and so are not
# visible to the naked eye from the site at all. They carried 56% of the lit
# area, and they are what made a real sky look like noise: the sixteen stars
# that actually form the patterns were 1.3% of what was drawn.
SIZE_BANDS_DENSE = ((1.5, 3), (4.0, 2), (None, 1))
# Paired with a limiting magnitude near what a real suburban sky reaches, and
# with the steeper brightness ratio below - the three only work together.
#
# Cutting at magnitude 5 removes 82% of the stars; the recorded failure mode
# here is a sky that loses its drawn area and reads as empty rather than dark,
# so the survivors are enlarged to keep the panel's presence. Measured on the
# composited frame: 233 stars against 1237, and 2051 lit pixels against 1503.
SIZE_BANDS_SPARSE = ((1.0, 5), (2.0, 4), (3.0, 3), (4.0, 2), (None, 1))

# The same idea on the 10.1" panel, which needs its own numbers rather than
# these. It shows a NARROWER window of sky (56 x 90 degrees against 124 x 70)
# magnified over 2.5x the pixels, so the same honest limiting magnitude puts
# roughly a fifth as many stars per megapixel on it. Everything is therefore a
# size larger, and the catch-all is 3 rather than 2.
#
# It also has a defect these fix. Its min_size=2 floor put EVERY star at 3x3 -
# measured, 1060 of 1060 - so drawn area tracked star count and not magnitude,
# and the ordering that makes a sky recognisable was absent altogether. With a
# catch-all of 3 that floor no longer binds on anything.
SIZE_BANDS_SPARSE_10 = ((1.0, 6), (2.0, 5), (3.0, 4), (4.0, 3), (None, 2))

# Brightness ratio per magnitude, and the floor, for each profile.
#
# THE FLAT DEFAULT EXISTS TO PROTECT STARS THE SPARSE PROFILE NO LONGER DRAWS.
# 0.93 with a 0.55 floor spans 1.78:1 - 0.63 magnitudes - for a sky spanning
# eight, because a steeper map piled the faint majority onto the floor and the
# sky rendered half as present. Once the catalogue is cut at magnitude 5 there
# is no faint majority to protect, and the compression only flattens the
# ordering that makes a sky recognisable: every star came out the same grey and
# differed only in width. 0.81 with a 0.25 floor spans 1.48 magnitudes.
DENSE_RATIO, DENSE_FLOOR = 0.93, 0.55
SPARSE_RATIO, SPARSE_FLOOR = 0.81, 0.25

# The magnitude that renders at FULL brightness.
#
# MAG_BRIGHT is Sirius, and anchoring there wastes the top of the scale on a
# star that is not in the sky. Sirius sits at declination -16 and is a winter
# object from 51 N; on an August evening the brightest thing in view is around
# magnitude 0, which rendered at 72% and came out mid grey. Every star actually
# on the panel was crowded into the bottom half of the range, which is what made
# them look flat and dim rather than like points of light.
#
# Anchoring at 0 spends the range on what is really there. Sirius and Vega both
# clamp to full when Sirius IS up, which loses one distinction at the very top -
# both are brilliant, and that is the correct thing to lose.
SPARSE_BRIGHT = 0.0

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


def _appearance(mag, min_size=1, bands=SIZE_BANDS_DENSE,
                ratio=DENSE_RATIO, floor=DENSE_FLOOR, bright=MAG_BRIGHT):
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
    base = max(floor, min(1.0, ratio ** (mag - bright)))
    # Size, not brightness, is what carries the magnitude ordering: the drawn
    # brightness range above spans 1.78:1, which is 0.63 magnitudes for a sky
    # that spans eight. It is not only a rendering convenience - a brighter star
    # really does read as larger to the eye, through glare - and a single pixel
    # is 0.11mm on this panel, so the faintest stars are at the edge of being
    # visible from across a room whatever brightness they are given.
    size = bands[-1][1]
    for limit, value in bands[:-1]:
        if mag < limit:
            size = value
            break
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

    Returns 1.0 at the zenith, rising towards the horizon. The twinkle is not
    one number because a star overhead is seen through the least atmosphere
    available and sits very nearly steady, while one low down is seen through
    several times as much and shimmers noticeably. A single amplitude across
    the whole field overstates the zenith and understates the horizon.
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
            min_size=1, limit=MAG_FAINT, bands=SIZE_BANDS_DENSE,
            ratio=DENSE_RATIO, floor=DENSE_FLOOR, bright=MAG_BRIGHT):
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
        if mag > limit:
            # Fainter than the site can actually see. Drawing it is not extra
            # fidelity: the catalogue reaches 6.5 and a suburban sky reaches
            # about 5, so these are stars nobody at the panel could ever pick
            # out, and in bulk they bury the ones that make the sky recognisable.
            continue
        alt, az = alt_az(obs, ra, dec)
        if alt <= 0.0:
            continue                      # below the horizon: genuinely not there
        x, y, inside = project_point(az, alt, w, h,
                                     az_centre, alt_centre, fov_vertical)
        if not inside:
            continue
        base, size = _appearance(mag, min_size, bands, ratio, floor, bright)
        rng = random.Random(i)
        stars.append((int(x), int(y), base,
                      rng.uniform(0.0, 2 * math.pi),
                      rng.uniform(*TWINKLE_SPEED), size,
                      scintillation(alt)))
    return stars
