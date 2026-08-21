"""Which meteor showers are running tonight, and what you would actually see.

There is no free meteor-shower API because there is nothing to serve. A shower
is the Earth crossing a debris stream on a known orbit, so the parameters are
constants: a radiant, a peak and a rate. This is the whole dataset.

⇒ PEAKS ARE STORED AS SOLAR LONGITUDE, NOT DATES. Earth crosses each stream at a
fixed angular position in its orbit; the peak appears to wobble by a day between
years only because the Gregorian year (365 d) runs against the tropical year
(365.2422 d), so the same solar longitude slips about six hours a year until a
leap day resets it. That wobble is a property of the calendar, not of the shower.
Stored this way the table is self-correcting forever and needs no maintenance.

SOURCE: the IMO Working List of Visual Meteor Showers
(https://www.imo.net/members/imo_showers/working_shower_list), checked
2026-08-05. Peak solar longitudes, radiants (J2000) and ZHRs are taken from it
directly; the activity limits are the IMO's published activity DATES converted
to solar longitude here, so nothing in this table is stored as a date.

SOURCE for the falloff B: Jenniskens P., 1994, "Meteor stream activity I. The
annual streams", Astronomy and Astrophysics 287, 990-1013, checked 2026-08-06
against the Dutch Meteor Society's abridged datalist. The IMO list cannot supply
this: it publishes the population index r, which describes a shower's MAGNITUDE
distribution, not how its rate rises and falls with solar longitude. Jenniskens
fits exactly the form used here, ZHR = ZHRmax * 10^(-B|lambda - lambda_max|).

Two of the eleven are estimates rather than published values, and are marked
below: Jenniskens gives the Lyrids and the Leonids as "rev." (under revision at
the time of publication). His generic value for high-inclination streams,
B = 0.19 +- 0.08, is not used for them because both are sharply peaked and 0.19
would spread them over roughly three days. Everything else in the B column is
his measured value.

Radiants and ZHRs stay with the IMO even where Jenniskens also publishes them:
his are equinox 1950.0 and drawn from 1980s-90s observations, so mixing the two
sources within a row would combine different epochs.

Radiants drift roughly a degree a day through a shower's activity period, as the
Earth's vantage point moves. That is ignored here; the IMO publishes drift rates
if it ever matters.
"""
import math

import ephem

# name, peak solar longitude, active from/to (solar longitude), radiant RA/Dec
# (J2000, degrees), zenithal hourly rate at peak, then the falloff B BEFORE the
# peak and AFTER it, per degree of solar longitude.
#
# The two Bs are separate because a stream is not obliged to be symmetric: the
# Geminids build gradually and cut off sharply, which a single slope cannot
# express, and using only the ascending value made the shower appear to persist
# almost twice as long after maximum as it does.
SHOWERS = [
    # Jenniskens lists the Quadrantids as the Bootids: single-curve fit B = 1.8,
    # with a 2.5 main peak over a shallower background if the two-curve form is
    # wanted. The single-curve value is what this one-slope model can carry.
    ("Quadrantids",           283.2, 274.1, 291.4, 230.0,  49.0, 120, 1.8,   1.8),
    # ESTIMATE - "rev." in Jenniskens. Set to keep the shower about as narrow as
    # the IMO's activity dates imply.
    ("Lyrids",                 32.3,  25.7,  34.4, 271.0,  34.0,  18, 0.22,  0.22),
    ("η-Aquariids",            45.5,  28.6,  66.3, 338.0,  -1.0,  40, 0.080, 0.080),
    ("Southern δ-Aquariids",  127.0, 109.3, 149.5, 340.0, -16.0,  25, 0.091, 0.091),
    ("Perseids",              140.0, 114.1, 150.5,  48.0,  58.0, 150, 0.20,  0.20),
    # Jenniskens fits the Taurids as one stream with a twin radiant, so both
    # branches take the same slope.
    ("Southern Taurids",      197.0, 166.9, 237.3,  32.0,   9.0,   5, 0.026, 0.026),
    ("Orionids",              208.0, 188.5, 224.2,  95.0,  16.0,  15, 0.12,  0.12),
    ("Northern Taurids",      230.0, 206.2, 257.6,  58.0,  22.0,   5, 0.026, 0.026),
    # ESTIMATE - "rev." in Jenniskens, revised only in his later outburst work.
    ("Leonids",               235.3, 223.2, 247.4, 152.0,  22.0,  15, 0.55,  0.55),
    # The asymmetric one. Gradual rise, rapid decline after maximum - long noted
    # in the observational literature, which is what fixes which branch is which.
    ("Geminids",              262.2, 251.5, 267.7, 112.0,  33.0, 120, 0.39,  0.72),
    # The IMO gives the Ursids' ZHR as "var". 10 is not a guess: it is
    # Jenniskens' main-peak fit, ZHRmax = 10 +- 3 with B = 0.9 +- 0.4.
    ("Ursids",                270.7, 264.7, 273.8, 217.0,  76.0,  10, 0.90,  0.90),
]

# A dark clear sky still shows a handful of meteors belonging to no shower at
# all. Quoting shower rates alone implies zero on an ordinary night, which is
# wrong, so the page carries this as its floor.
SPORADIC_ZHR = 8

# Below this a shower is not worth naming, and the page stops listing it.
#
# WHY A FRACTION OF THE FLOOR RATHER THAN A NUMBER OF DAYS. The activity windows
# in SHOWERS are per-shower and vary twentyfold - the Lyrids leave 2.1 days past
# maximum, the Southern Taurids 40.9 - so a fixed span would just be that table
# rewritten. The floor above is already this page's own statement of what an
# ordinary night gives, which makes it the natural thing to be measured against.
#
# The case that set the value: on 2026-08-11 the page named the Southern
# δ-Aquariids at about 1/hr, twelve days past their peak, four lines above a
# sporadic background of 6/hr. A named row implies the shower is what to watch
# for, and at a sixth of the unnamed background it was not.
#
# Compared in ZHR, not in the observed rate, so the decision does not move with
# latitude or with the radiant's altitude on the night. This is a DISPLAY
# judgement and belongs to the page: active() keeps reporting these showers,
# because they are still falling and the animated sky is still entitled to them.
#
# THE FLOOR IS NOT WHAT KEEPS A NAMED ROW ABOVE THE SPORADIC LINE ON THE PAGE,
# and it was asked to be on 2026-08-21, when the Perseids printed ~0/hr four
# lines above a sporadic background of ~1/hr. Measured, the shower was at 37% of
# the sporadic rate all night - the printed pair was rounding, not ranking, and
# the fix was to print a decimal rather than to move this floor. A second gate
# in observed rate was measured and rejected: at any fraction that would have
# caught that night it cost more than half the nights the page runs at all.
NAMED_SHOWER_FLOOR = 0.25 * SPORADIC_ZHR

# Above this fraction of its own peak rate, a shower is described as peaking.
#
# WHY A RATE AND NOT A NUMBER OF DAYS. The obvious test is "within half a degree
# of maximum", and that was the original one. It is wrong because it measures
# time while the label makes a claim about the rate printed beside it, and the
# two are related by B, which spans a factor of 70 across this table. At half a
# degree the Taurids still hold 97% of their peak and the Quadrantids 13%, so
# one window announced a shower at its best and another at an eighth of it.
#
# Measured against strength the window derives itself: about 5.6 hours either
# side for the Perseids, 0.6 for the Quadrantids, 43 for the Taurids. A shower
# that genuinely sustains its rate for two days is peaking for two days.
#
# The case that set the value: on 2026-08-12, the Perseid peak, the page read
# "peaking now" beside ~100/hr under a headline ZHR of 150, which looks like a
# contradiction and was not - the shower was at 73% and climbing.
PEAKING_STRENGTH = 0.9


def solar_longitude(when):
    """The Earth's angular position in its orbit, in degrees."""
    sun = ephem.Sun(ephem.Date(when))
    return math.degrees(ephem.Ecliptic(sun).lon) % 360.0


def _wrapped(value, lo, hi):
    """True if value lies in [lo, hi], allowing the range to cross 360."""
    if lo <= hi:
        return lo <= value <= hi
    return value >= lo or value <= hi


def active(when):
    """Showers running at this instant, as dicts, strongest first.

    `strength` is the fraction of the shower's peak rate expected now, from the
    standard 10^(-B|dlambda|) falloff, taking the slope for whichever side of
    the peak the Earth is currently on.
    """
    lam = solar_longitude(when)
    out = []
    for name, peak, lo, hi, ra, dec, zhr, b_rise, b_fall in SHOWERS:
        if not _wrapped(lam, lo, hi):
            continue
        # Signed first: past the peak the shower is declining, and for an
        # asymmetric stream that is a different slope from the approach.
        signed = (lam - peak + 180.0) % 360.0 - 180.0
        b = b_fall if signed > 0 else b_rise
        d = abs(signed)
        out.append({
            "name": name, "ra": ra, "dec": dec, "zhr": zhr,
            "peak_lambda": peak, "delta_lambda": d,
            "strength": 10.0 ** (-b * d),
        })
    return sorted(out, key=lambda s: -s["zhr"] * s["strength"])


def visible_rate(zhr, strength, radiant_alt, cloud_pct=0.0, moon_illum=0.0):
    """Meteors an observer would actually count per hour, roughly.

    The headline ZHR is a zenith rate under a perfect sky and is never what
    anybody sees. Three things cut it, all of which this display already knows:
    the radiant's altitude (the observed rate falls off with its sine, and a
    radiant below the horizon correctly gives nothing), cloud, and moonlight.

    Deliberately approximate, and presented as such: the point is to be honest
    about tonight rather than to quote a number that only holds in a desert at
    the zenith with no Moon.
    """
    if radiant_alt <= 0:
        return 0.0
    rate = zhr * strength * math.sin(math.radians(radiant_alt))
    rate *= max(0.0, 1.0 - cloud_pct / 100.0)
    # Full moon costs most of the faint end; a thin crescent barely registers.
    rate *= 1.0 - 0.75 * max(0.0, min(1.0, moon_illum))
    return rate


# Below this an hourly rate is printed to a decimal place.
#
# WHY THE PAGE CANNOT PRINT WHOLE NUMBERS ALL THE WAY DOWN. Observed rates are
# low single digits on most nights and cloud divides them again, so the
# interesting end of the range sits under 1/hr - where a whole number has
# exactly two values and one of them is zero. On 2026-08-21 a named Perseid row
# printed ~0/hr four lines above a sporadic background of ~1/hr: a shower the
# page had chosen to name, reporting that nothing was falling, above a rate it
# was at 37% of. Under a clear sky the same night reads ~2/hr against ~6/hr and
# is unremarkable. The pair was rounding, not ranking.
#
# The threshold is where the decimal stops being needed rather than a tuned
# value: at and above 1/hr the whole number already separates the rows, and a
# trailing ".0" on every clear-night figure would claim precision this page does
# not have.
RATE_DECIMAL_BELOW = 1.0
# And below this even a decimal rounds to zero, so the figure is given as a
# bound instead - the same defect one decimal place further down.
RATE_BOUND_BELOW = 0.1


def rate_text(rate):
    """An hourly meteor rate, printed so that it never reads as nothing.

    Zero itself is kept as a whole number, because there it is the answer rather
    than a rounded one: a radiant below the horizon really does deliver none.

    Formatting lives here, next to visible_rate, because the honest way to state
    one of these numbers is a fact about the number and not about the layout -
    and because every figure it is compared against on the page has to be
    printed the same way or the comparison the page invites does not hold.
    """
    if rate <= 0:
        return "~0/hr"
    if rate < RATE_BOUND_BELOW:
        return f"<{RATE_BOUND_BELOW:.1f}/hr"
    if rate < RATE_DECIMAL_BELOW:
        return f"~{rate:.1f}/hr"
    return f"~{rate:.0f}/hr"


def upcoming(when, exclude=(), within_days=200, limit=5):
    """[(name, days away, zhr)] for the next peaks, soonest first.

    Same search as next_shower and the same rule about units - solar longitude
    throughout, days only at the end - but it returns the run of them rather
    than the first, because the space a page has for this is exactly the space
    the active showers left, and that varies from night to night.

    `exclude` is the showers already being reported as active: a shower can be
    running AND have its peak ahead of it, and it already says so in its own
    row, so repeating it under "coming up" would be the same fact twice in two
    different formats.
    """
    lam = solar_longitude(when)
    out = []
    for name, peak, _lo, _hi, _ra, _dec, zhr, *_ in SHOWERS:
        if name in exclude:
            continue
        days = ((peak - lam) % 360.0) / 0.9856
        if days <= within_days:
            out.append((name, days, zhr))
    return sorted(out, key=lambda r: r[1])[:limit]


def next_shower(when, exclude=(), within_days=120):
    """(name, days away) for the next shower peak, or None.

    Uses solar longitude for the search and converts to days only at the end,
    which is the only place a calendar belongs.

    `exclude` carries the same meaning as in upcoming(), and for the same
    reason: a shower can be running AND have its peak ahead of it, so without
    it this reported "next peak: Perseids in 2 hours" directly beneath a
    Perseid row reading "peaking now". Both statements were true and the pair
    was a contradiction. upcoming() had the argument from the start; this
    function was written alongside it and did not.
    """
    lam = solar_longitude(when)
    best = None
    for name, peak, *_ in SHOWERS:
        if name in exclude:
            continue
        ahead = (peak - lam) % 360.0
        if best is None or ahead < best[1]:
            best = (name, ahead)
    if best is None:
        return None
    # The Earth covers a little under a degree of solar longitude per day.
    days = best[1] / 0.9856
    return (best[0], days) if days <= within_days else None
