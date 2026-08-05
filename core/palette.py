"""The display's colours, and the two mappings from a value to one of them.

Conditions run on a cool-to-warm ramp: a clear night reads cold and blue, a
washed-out one warm. Amber is reserved for the moon and for cautions.

Contrast was computed against every background the sky actually paints - the
night gradient (6,8,20 -> 15,17,42) and the twilight one (22,32,62 -> 44,60,100)
- using the lightest of each for light ink. Colour is never the sole carrier of
a reading, which is also what makes red night mode viable.
"""
BG       = (10, 12, 28)      # opaque fills (bar troughs) — matches the night sky
WHITE    = (230, 232, 240)   # data text
ICE      = (165, 243, 252)   # #A5F3FC — best conditions
ELECTRIC = (56, 189, 248)    # #38BDF8 — good conditions, bar fills
AMBER    = (245, 158, 11)    # #F59E0B — fair/caution. STATUS ONLY.
# The moon is an object, not a state, and it used to share AMBER with the FAIR
# verdict - so on a fair night the two matched and implied a link that is not
# there. Ivory rather than gold: every warm gold tested came out under the
# ΔE 15 normal-vision floor against AMBER, i.e. hard to tell from it even with
# full colour vision. Ivory is warm AND very light, so it clears amber, and it
# is what the Moon actually looks like.
MOON     = (240, 226, 196)   # #F0E2C4 — the moon, wherever it appears
ROSE     = (244, 63, 94)     # #F43F5E — poor conditions
STEEL    = (29, 94, 128)     # muted electric — bar trough frame
MOON_DARK = (27, 36, 64)     # unlit lunar disc, just above the sky navy
MUTED    = (150, 158, 180)   # secondary TEXT — present, but not competing
# Rules, ticks and frames - plus the two deliberately recessive marginal notes,
# the version stamp and the imagery credit. NEVER content: at 3.2:1 on the
# night sky and 1.8:1 on the twilight one it is below WCAG AA wherever it is
# legible at all, and until v3.2.2 it was carrying axis labels, dusk/dawn times
# and the card subtitles. Lines are graphical objects, whose bar is 3:1, so it
# is the right colour for what it is used for now and was the wrong one before.
DIM      = (90, 98, 120)     # divider lines / subtle rules
STAR_COLOUR = (232, 234, 248)


def verdict(score):
    """(label, colour) for a deep-sky forecast score 0-100."""
    if score >= 75:
        return "EXCELLENT", ICE
    if score >= 50:
        return "GOOD", ELECTRIC
    if score >= 25:
        return "FAIR", AMBER
    if score > 0:
        return "POOR", ROSE
    return "NONE", ROSE


def bar_colour(value, good, warn):
    if value >= good:
        return ELECTRIC
    if value >= warn:
        return AMBER
    return ROSE
