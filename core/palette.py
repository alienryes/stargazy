"""The display's colours, and the rule that decides which one anything gets.

⇒ COLOUR MARKS REAL OBJECTS. STATE IS NEUTRAL.

If something on this panel is coloured it is a thing that is actually up there -
the Moon, a planet, a comet, a photograph of a nebula. If it is a judgement
about tonight - a verdict, a reading, a threshold - it is the same neutral
blue-white as everything else, and its meaning is carried by size, by length,
by position, or by the word itself.

This replaces a four-step cool-to-warm ramp, which was over-constrained rather
than badly chosen. Four ordinal steps encoded in hue, on a blue background, two
of them necessarily blue, each clearing WCAG AA against two different sky
gradients, each separated by ΔE 15, and still ordered by luminance once red
night mode discards the hue: there is no solution. Every attempt failed one of
those - the original fell to 2.95:1 at the POOR end, and a plausible
replacement put EXCELLENT and GOOD ΔE 6.8 apart.

The ramp was also redundant. A bar already encodes its magnitude by length, the
number is printed beside it, and the verdict is spelled out in 90px letters.
Colour was a fourth copy of information the panel already carried three times,
and it was the copy that cost the design. What remains is a single threshold,
carried by form: a reading below its warning mark is drawn hollow rather than
filled. That reads at a glance, survives the red night filter untouched because
form has no hue, and it satisfies "colour is never the sole carrier" outright
rather than approximately.

Contrast is computed against every background the sky actually paints - the
night gradient (6,8,20 -> 15,17,42) and the twilight one (22,32,62 -> 44,60,100)
- using the lightest of each for light ink.
"""
BG       = (10, 12, 28)      # opaque fills (bar troughs) — matches the night sky
WHITE    = (230, 232, 240)   # data text
# Every state, everywhere: verdicts, bar fills, section headings, data bands.
# One colour, because none of them is a different KIND of thing.
NOMINAL  = (169, 188, 224)   # #A9BCE0 — 8.1:1 on night, 4.7:1 on twilight
# Objects beyond the Moon and planets - comets, deep-sky marks, and the drawn
# stand-ins used when a real cutout cannot be fetched. Cool and pale so it sits
# with the sky rather than shouting over it, and well clear of both NOMINAL and
# MUTED. Comet against deep sky is not a distinction the eye needs at a glance,
# and every mark carries its name, so one colour covers both.
OBJECT   = (168, 216, 208)   # #A8D8D0
# The moon is an object, not a state - it used to share a colour with the FAIR
# verdict, so on a fair night the two matched and implied a link that is not
# there. Ivory because it is what the Moon actually looks like.
MOON     = (240, 226, 196)   # #F0E2C4 — the moon, wherever it appears
# Bar trough frame and plot axes. Was 2.61:1 on the night sky, below the 3:1
# bar for graphical objects; 3.30:1 now. Clearing 3:1 on the TWILIGHT gradient
# as well would need it light enough to compete with NOMINAL, which would make
# a frame louder than the thing it frames - so it is knowingly short there.
# It has to stay a clear BLUE: a first attempt lifted the luminance without
# changing the hue and landed ΔE 13.1 from DIM, so the trough frame and the
# ticks inside it became hard to tell apart. ΔE 28.9 now.
STEEL    = (68, 102, 172)    # #4466AC
MOON_DARK = (27, 36, 64)     # unlit lunar disc, just above the sky navy
# Secondary TEXT, and the planets on the alt-az plot. A true neutral, which is
# both the point and the fix: grey is what "not an object" looks like next to a
# blue NOMINAL, and the previous blue-grey sat ΔE 13.3 from it - close enough
# that a heading and a caption read as the same ink.
MUTED    = (162, 162, 163)   # #A2A2A3
# Rules, ticks and frames - plus the two deliberately recessive marginal notes,
# the version stamp and the imagery credit. NEVER content: at 3.2:1 on the
# night sky and 1.8:1 on the twilight one it is below WCAG AA wherever it is
# legible at all, and until v3.2.2 it was carrying axis labels, dusk/dawn times
# and the card subtitles. Lines are graphical objects, whose bar is 3:1, so it
# is the right colour for what it is used for now and was the wrong one before.
DIM      = (90, 98, 120)     # divider lines / subtle rules
STAR_COLOUR = (232, 234, 248)


# Aurora, and a deliberate exception to everything above: these are NATURALISTIC
# rather than part of the state scheme, in the same position as the lunar
# photograph and the DSS2 cutouts. Which one is drawn follows emission height -
# the green line sits around 100-150 km and is what an observer under the oval
# sees, while the red comes from 200 km and up and is the part that clears a
# distant horizon first, which is why southern England reports red glow where
# Tromso gets green. Neither carries meaning on its own: between dusk and dawn
# the whole panel collapses to red luma, so this is naturalism, not encoding.
# SAMPLED from an unprocessed RAW aurora photograph, not chosen. Both hues came
# out well away from the obvious guess: the green is a YELLOW-green at hue 77
# (10th-90th percentile 67-88 across 10,102 core pixels), not the spring green
# it is usually drawn as, and the upper colour is MAGENTA at hue 324 (314-330),
# not scarlet - which is right, since it is 630nm oxygen mixed with N2+ violet.
#
# Hue and relative saturation come from the photograph; absolute brightness does
# not. That picture is a dim night scene while these are drawn at an opacity
# carrying the storm's probability, so copying its luminance would render a
# severe storm as faintly as a real one photographs. Saturation is taken to
# about twice the photograph's, which puts the blended green at (118,145,63)
# against the photograph's own (118,130,87) - the same colour, brighter.
AURORA_GREEN = (208, 255, 86)
AURORA_RED   = (255, 78, 183)


def verdict(score):
    """The label for a deep-sky forecast score 0-100.

    A label only. It used to return a colour alongside, which is what made the
    verdict a fifth encoding of a number already shown as a percentage; the word
    at 90px says it better than a hue ever did.
    """
    if score >= 75:
        return "EXCELLENT"
    if score >= 50:
        return "GOOD"
    if score >= 25:
        return "FAIR"
    if score > 0:
        return "POOR"
    return "NONE"
