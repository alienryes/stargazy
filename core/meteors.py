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

The falloff B is NOT from the IMO list, which publishes the population index r
instead. These are conventional values and only shape the curve BETWEEN the
published activity limits - the limits and the peak, which decide whether a
shower appears at all, are the IMO's.

Radiants drift roughly a degree a day through a shower's activity period, as the
Earth's vantage point moves. That is ignored here; the IMO publishes drift rates
if it ever matters.
"""
import math

import ephem

# name, peak solar longitude, active from/to (solar longitude), radiant RA/Dec
# (J2000, degrees), zenithal hourly rate at peak, falloff B (per degree of solar
# longitude either side of the peak).
SHOWERS = [
    ("Quadrantids",           283.2, 274.1, 291.4, 230.0,  49.0, 120, 2.20),
    ("Lyrids",                 32.3,  25.7,  34.4, 271.0,  34.0,  18, 0.22),
    ("η-Aquariids",            45.5,  28.6,  66.3, 338.0,  -1.0,  40, 0.08),
    ("Southern δ-Aquariids",  127.0, 109.3, 149.5, 340.0, -16.0,  25, 0.09),
    ("Perseids",              140.0, 114.1, 150.5,  48.0,  58.0, 150, 0.20),
    ("Southern Taurids",      197.0, 166.9, 237.3,  32.0,   9.0,   5, 0.026),
    ("Orionids",              208.0, 188.5, 224.2,  95.0,  16.0,  15, 0.12),
    ("Northern Taurids",      230.0, 206.2, 257.6,  58.0,  22.0,   5, 0.026),
    ("Leonids",               235.3, 223.2, 247.4, 152.0,  22.0,  15, 0.55),
    ("Geminids",              262.2, 251.5, 267.7, 112.0,  33.0, 120, 0.39),
    # The IMO gives the Ursids' ZHR as "var"; 10 is the usual quiet-year figure
    # and the only invented number in this table.
    ("Ursids",                270.7, 264.7, 273.8, 217.0,  76.0,  10, 0.90),
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
    standard 10^(-B|dlambda|) falloff either side of the peak.
    """
    lam = solar_longitude(when)
    out = []
    for name, peak, lo, hi, ra, dec, zhr, b in SHOWERS:
        if not _wrapped(lam, lo, hi):
            continue
        d = abs((lam - peak + 180.0) % 360.0 - 180.0)
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
