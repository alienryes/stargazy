"""A continuous cloud field, generated once and scrolled, replacing the sprites.

WHY NOT SPRITES. Seven pre-rendered blobs cannot cover a sky. Each obscures
about a tenth of it, so total overcast drew seven puffs with stars between them,
and a uniform sheet had to be blended behind them to make up the difference -
one flat tone across the whole panel, which is the "haze" this replaces. The
sprites also took their size from each axis of the canvas separately, so their
shape inherited the panel's: 2.3:1 and cloud-like on the 1280x720 build, 0.8:1
and vertically elongated on the 1200x1920 one. Cloud shape is a property of
cloud, not of the panel it is drawn on.

The field fixes both at the root. It is one image, so cover has no ceiling; it
is generated at a stated feature size and aspect, so it looks the same on any
canvas; and it has structure at every scale, so overcast is cloud rather than a
wash.

HOW IT IS BUILT. Low-pass-filtered white noise on a torus: FFT the noise,
multiply the spectrum by a radial power law, invert. Periodic in both axes by
construction, which is what makes it scrollable without a seam - a lattice noise
implementation would need its wraparound arranged by hand. The power law rather
than a Gaussian is what gives structure at every scale instead of one size of
blob.

COVER IS SOLVED FOR, NOT DERIVED. The field is rank-normalised to a uniform
distribution, then a threshold is found by bisection such that the mean alpha
equals the reported cover exactly. The previous arithmetic estimated what n
sprites obscured and blended a sheet to cover the shortfall, which had to be
kept in step with the sprite size and count by hand.
"""
import math

import numpy as np

# Feature height as a fraction of the canvas's SHORTER side, and how much wider
# than tall a cloud is. The aspect is applied in pixels, so it is the same on
# every panel - which is the whole point, the previous sprites having taken one
# fraction per axis and so inherited whatever shape the canvas was.
#
# The fraction was chosen by rendering the sweep: 0.26 puts so many features on
# the canvas that 60% cover reads as an unbroken mat rather than as broken
# cloud, and the gaps that make it legible as weather disappear.
FEATURE_FRACTION = 0.5
FEATURE_ASPECT = 2.4

# Spectral slope. Governs how much fine detail survives the low-pass: lower is
# wispier and more fractal, higher is smoother and more blob-like. 2.2 sits near
# the measured slope of real cloud fields.
SPECTRAL_BETA = 2.2

# Width of the ramp from clear to opaque, in field units. The field is uniform
# on [0, 1), so this is directly the fraction of the sky occupied by cloud edge
# at moderate cover. Too small gives cut-out shapes with hard rims; too large
# gives the soft everywhere-at-once wash the sheet already produced.
EDGE_SOFTNESS = 0.22

# Cloud tone, and how far it swings with the field. The swing is what keeps
# overcast from being a single flat colour: at full cover every pixel is opaque,
# so all the remaining variation has to come from the colour itself.
CLOUD_COLOUR = (48, 53, 72)
TONE_SWING = 0.5

# How many canvas widths the field spans before it repeats.
#
# ONE IS NOT ENOUGH, AND THE 10" BUILD PROVES IT. The field is periodic over its
# own width, so at a width of one canvas whatever leaves the right edge IS what
# enters the left. A feature is 0.5 x 1200 x 2.4 = 1440 px wide there against a
# 1200 px canvas, so every cloud was visibly on both edges at once. The 5" build
# hid it: 864 px of feature on a 1280 px canvas is narrow enough to clear one
# edge before reaching the other.
#
# Four puts 3600 px of scroll between a feature leaving and returning on the
# 10", which is several minutes at any speed the display uses.
FIELD_WIDTHS = 4


def make_field(w, h, ref, seed=7):
    """A cloud field on (h, w), periodic in both axes, uniform on [0, 1).

    `ref` is the length feature size is taken from, and is the CANVAS's shorter
    side - not the field's. The field is several canvases wide, so deriving it
    from this array would make the clouds grow with FIELD_WIDTHS: exactly the
    mistake the per-axis sprite fractions made, one level up.

    Uniform because the caller solves a threshold against it: a known
    distribution makes that solve well behaved and independent of which noise
    realisation was drawn.
    """
    rng = np.random.default_rng(seed)
    # float32 throughout. The spectrum of a several-canvas field is the largest
    # array this program builds, and float64 doubles both it and the noise it
    # comes from for precision nothing here can use.
    spec = np.fft.rfft2(rng.standard_normal((h, w), dtype=np.float32))

    # Cycles per pixel along each axis. fx is multiplied by the aspect so that a
    # given horizontal frequency is attenuated as though it were higher than it
    # is, which removes horizontal detail faster than vertical and leaves
    # features wider than they are tall.
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.rfftfreq(w)[None, :]
    r = np.hypot(fx * FEATURE_ASPECT, fy)

    # Corner frequency from the feature size. Below it the response is flat, so
    # nothing larger than a feature dominates the field; above it the power law
    # takes over and supplies the finer structure.
    r0 = 1.0 / (FEATURE_FRACTION * ref)
    with np.errstate(divide="ignore"):
        gain = 1.0 / (1.0 + (r / r0) ** SPECTRAL_BETA)
    gain[0, 0] = 0.0  # drop DC: the mean is set by the threshold, not the noise

    field = np.fft.irfft2(spec * gain, s=(h, w))

    # Rank-normalise. Flattening the histogram costs one sort, once, and buys an
    # exact relationship between threshold and covered area - see solve_threshold.
    order = np.argsort(field, axis=None)
    ranks = np.empty(field.size, dtype=np.float32)
    ranks[order] = np.arange(field.size, dtype=np.float32) / field.size
    return ranks.reshape(h, w)


# Roughly how many pixels the solve reads. The field is rank-normalised, so any
# large subsample carries the same distribution and the threshold comes out the
# same; this only avoids forty passes over the whole field while the render loop
# is waiting. Stated as a COUNT rather than a stride so that widening the field
# does not make every cover change proportionally slower. The error against the
# full field is measured rather than assumed - see the cover check.
SOLVE_SAMPLES = 200_000


def solve_threshold(field, cover):
    """Threshold at which the field's mean alpha equals `cover`.

    Bisection rather than the closed form. For a uniform field the mean is
    1 - t - EDGE_SOFTNESS/2 while the ramp lies wholly inside [0, 1], and that
    expression is used as a check in the tests - but it stops holding once the
    ramp runs off either end, which is exactly the overcast and near-clear cases
    the display has to get right. Bisection is correct everywhere.
    """
    stride = max(1, int(math.sqrt(field.size / SOLVE_SAMPLES)))
    sample = field[::stride, ::stride]
    lo, hi = -EDGE_SOFTNESS, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if alpha_from(sample, mid).mean() > cover:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def alpha_from(field, threshold):
    """Alpha in [0, 1]: clear below the threshold, opaque a ramp above it."""
    return np.clip((field - threshold) / EDGE_SOFTNESS, 0.0, 1.0)


def make_tone_rgb(field):
    """The cloud's own colour over the whole field, before any cover is applied.

    Cover changes four times an hour and this does not depend on it - tone
    tracks the field, which is generated once. Measured at 192 ms of a 615 ms
    cover change on the 10" geometry before it was lifted out, which was the
    single largest item in a stall the render loop takes in one piece.

    The swing is what keeps overcast from being one flat colour: at full cover
    every pixel is opaque, so all the remaining variation has to come from here.
    """
    tone = (1.0 - TONE_SWING / 2.0) + TONE_SWING * field
    rgb = np.array(CLOUD_COLOUR, dtype=np.float32) * tone[..., None]
    return np.clip(rgb, 0, 255).astype(np.uint8)


def alpha_for(field, cover):
    """Alpha covering `cover` (0-1) of the field, as uint8."""
    return (alpha_from(field, solve_threshold(field, cover)) * 255.0).astype(np.uint8)
