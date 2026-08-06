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


def next_shower(when, within_days=120):
    """(name, days away) for the next shower peak, or None.

    Uses solar longitude for the search and converts to days only at the end,
    which is the only place a calendar belongs.
    """
    lam = solar_longitude(when)
    best = None
    for name, peak, *_ in SHOWERS:
        ahead = (peak - lam) % 360.0
        if best is None or ahead < best[1]:
            best = (name, ahead)
    if best is None:
        return None
    # The Earth covers a little under a degree of solar longitude per day.
    days = best[1] / 0.9856
    return (best[0], days) if days <= within_days else None
