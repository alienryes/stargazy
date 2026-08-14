"""What the Sun is doing today: spots, flares, an inbound CME, and eclipses.

⇒ THIS IS THE FIRST DAYLIGHT SUBJECT THE DISPLAY HAS HAD. Every other gated page
here exists only while it is dark - aurora and meteors are conditions of the
night sky, and a page about either is worthless at noon. The Sun inverts that
exactly, and it fills the hours in which the rest of the panel has least to say.

⇒ AN ECLIPSE IS AN APPOINTMENT, THE REST ARE CONDITIONS, AND THEY ARE FETCHED
DIFFERENTLY FOR THAT REASON. Spots and flares are feeds sampled every few
minutes; an eclipse is a dated event computed from ephem alone with no network
at all, which makes it the one thing on this display that works offline. It is
also rare enough locally - the next partial visible from 51.4N is in August 2027
- that it is cached until it has passed rather than recomputed per refresh.

⚠ NOTHING RETURNED HERE MAY BE PHRASED AS AN INSTRUCTION TO LOOK AT THE SUN. The
figures are safe to print; the act is not. A caller drawing them must attach the
filter caveat to the figure itself rather than footnoting it.

⚠ MAGNITUDE IS NOT OBSCURATION and both are returned, separately named.
Magnitude is the fraction of the solar DIAMETER covered; obscuration is the
fraction of its AREA. At the 2026-08-12 partial they read 0.935 and 0.926, and
at a deeper eclipse they diverge by 0.10. Printing one under the other's label
is the same class of error as quoting a shower's ZHR as an observed rate.

Sources: NOAA SWPC for the live conditions, and DONKI's CME model runs served by
CCMC. Both are keyless and unregistered, so this adds no new kind of dependency.
"""
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ephem
import requests

log = logging.getLogger(__name__)

REGIONS_URL = "https://services.swpc.noaa.gov/json/solar_regions.json"
XRAY_URL = "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json"
F107_URL = "https://services.swpc.noaa.gov/products/summary/10cm-flux.json"

# ⚠ THE ENDPOINT NAMED FOR ANALYSES IS THE WRONG ONE. DONKI's `CMEAnalysis`
# returns the analyses stripped of their model runs - 0 ENLIL runs over 45 days
# on the probe that established this - while the same analyses reached through
# the `CME` records carried 285 over 60 days. The arrival time this module
# exists to report lives at CME.cmeAnalyses[].enlilList and nowhere else.
DONKI_CME_URL = "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/CME"

HEADERS = {"User-Agent": "stargazy (github.com/alienryes)"}

CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache"
ACTIVITY_CACHE = CACHE_ROOT / "solar.json"
ECLIPSE_CACHE = CACHE_ROOT / "eclipse.json"

# The feeds update every few minutes and the page turns every thirty seconds, so
# the refresh interval is set by what is worth redrawing rather than by what is
# available. Past the hard age the cached figures are refused outright: a flare
# level six hours old is not a weaker claim about now, it is a claim about then.
REFRESH_MINUTES = 30
MAX_AGE_HOURS = 6
FETCH_COOLDOWN_MINUTES = 30
_last_failure = None

# Flare classes are decade bands of the long-band flux in W/m^2.
FLARE_BANDS = (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7), ("A", 1e-8))

# ⇒ THE C/M/X CLASSIFICATION IS DEFINED ON THE LONG BAND ONLY. Both bands arrive
# interleaved in one array, so reading it unfiltered mixes two physically
# different quantities and roughly halves every count.
LONG_BAND = "0.1-0.8nm"

# How far ahead a CME arrival is worth reporting. Beyond about four days the
# model run is superseded by the next one before the shock lands.
CME_LOOKAHEAD_DAYS = 4
CME_WINDOW_DAYS = 7

# An eclipse is searched for over this many days ahead. Two years spans the
# roughly annual local recurrence with room for the gap after one passes.
ECLIPSE_HORIZON_DAYS = 730
# Coarse pass then fine. An eclipse lasts a couple of hours, so ten-minute steps
# cannot step over one; the minute pass is only run on a day already known to
# hold one, which is what keeps a two-year search affordable on a Pi.
ECLIPSE_COARSE_MIN = 10
ECLIPSE_FINE_MIN = 1


def _get(url, params=None, timeout=20):
    r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _cache_age(path):
    if not path.exists():
        return None
    return datetime.now(timezone.utc) - datetime.fromtimestamp(
        path.stat().st_mtime, timezone.utc)


def flare_class(flux):
    """A long-band flux in W/m^2 as its letter class, or None below A."""
    if not flux or flux <= 0:
        return None
    for letter, base in FLARE_BANDS:
        if flux >= base:
            return f"{letter}{flux / base:.1f}"
    return None


def _location(text):
    """("S17W54") -> (-17.0, -54.0) in degrees, north and east positive.

    East positive, so a group's longitude DECREASES as solar rotation carries it
    from the east limb towards the west over about thirteen days.

    Returns (None, None) for anything unparseable - a region without a
    measurable position is a normal state, not an error.
    """
    if not text or len(text) < 4:
        return None, None
    try:
        ns, ew = text[0].upper(), text[3].upper()
        lat, lon = float(text[1:3]), float(text[4:])
    except (ValueError, IndexError):
        return None, None
    if ns not in "NS" or ew not in "EW":
        return None, None
    return (lat if ns == "N" else -lat), (lon if ew == "E" else -lon)


def solar_b0(when=None):
    """Heliographic latitude of the disc centre, in degrees.

    The Sun's rotation axis is tilted 7.25 degrees to the ecliptic, so the disc
    centre is not the solar equator: it runs from -7.25 in early March to +7.25
    in early September. Drawing spots without it puts a group up to seven
    degrees out of place, which near the limb is most of the way to the edge.

    Standard reduction from the ascending node of the solar equator. Verified
    against the seasonal extremes rather than against another implementation -
    the zeros in early June and December and the turning points in March and
    September are what the figure has to reproduce.
    """
    obs = ephem.Observer()
    obs.date = _ephem_date(when)
    sun = ephem.Sun()
    sun.compute(obs)
    jd = ephem.julian_date(obs.date)
    # Ascending node of the solar equator on the ecliptic, precessing slowly.
    node = math.radians(73.6667 + 1.3958333 * (jd - 2396758.0) / 36525.0)
    # The Sun's apparent geocentric longitude is the Earth's heliocentric one
    # turned through half a circle.
    lam = float(sun.hlon) + math.pi
    return math.degrees(math.asin(math.sin(lam - node) * math.sin(math.radians(7.25))))


def project_spot(lat, lon, b0):
    """A heliographic position as (x, y, front) on a unit disc, north up.

    Orthographic, which is what a disc seen from 150 million kilometres is. y is
    positive DOWNWARD to match image coordinates. `front` is False for a
    position rotated onto the far side, where nothing should be drawn - the
    projection alone would fold it back onto the visible half and put a group
    that has set on the wrong limb.

    ⇒ SOLAR WEST IS TO THE RIGHT, which is the orientation every published solar
    image uses and the direction rotation carries a group. Since longitude here
    is east-positive the sine is negated to get it, and a caller drawing this
    should label the limbs rather than leave a reader to assume either way.
    """
    la, lo = math.radians(lat), math.radians(lon)
    b = math.radians(b0)
    x = -math.cos(la) * math.sin(lo)
    y = (math.sin(la) * math.cos(b)
         - math.cos(la) * math.cos(lo) * math.sin(b))
    front = (math.sin(la) * math.sin(b)
             + math.cos(la) * math.cos(lo) * math.cos(b)) > 0
    return x, -y, front


def fetch_regions():
    """Today's sunspot regions, their spot count and the day's flare odds.

    ⚠ THE ARRAY IS NEWEST-FIRST AND NOT SORTED, so neither end is safe by
    assumption: on the probe run rows[-1] was dated a month back and rows[0] was
    today, while `dates == sorted(dates)` was False. The observed date is taken
    as the maximum and everything else discarded - 194 of 200 rows on that run.

    Flare probabilities are per region and come as percentages. The page wants
    one number for the day, and the honest reduction is the maximum rather than
    a sum: the regions are not independent trials and adding them can exceed
    100% while describing a quiet Sun.

    ⚠⚠ A ZERO PROBABILITY IS NOT ALWAYS A FORECAST OF CALM. The day's region
    list is published BEFORE the classification and flare forecast are attached
    to it, and in that state every region carries spot_class None and every
    probability reads 0. Printed as a forecast that is a claim of near-certainty
    that nothing will happen, made at the exact moment nobody has said anything.
    Observed 2026-08-13: six regions, all spot_class None, all probabilities 0,
    against a fully classified previous day reading C 35% / M 5% / X 1%.

    ⚠ THE REPORT FILLS IN PROGRESSIVELY, AND spot_class IS THE WRONG MARKER.
    That was the first attempt, and the feed disproved it within the hour: by
    then four of six regions had a spot_class while every probability was still
    exactly 0. The decisive observation is region 4507, classified 'Dso' on both
    2026-08-12 and 2026-08-13, carrying C 35% on the first day and C 0% on the
    second - the same region at the same classification does not go 35% to 0%
    overnight, so the zeros are an absence rather than a forecast.

    `forecast_issued` therefore keys on any probability being non-zero. Across
    all 31 report dates in the file, every fully issued day carries at least one
    non-zero probability, and a physical argument agrees: a D-class bipolar
    group always carries some chance of a C flare. A genuinely all-quiet day
    would be reported here as "not yet issued", which is the conservative
    failure - saying nothing is known when the answer is "almost certainly
    nothing", rather than asserting calm nobody forecast.

    *This is the rows[-1] trap for the third time on this host: establish what a
    field MEANS before taking it at face value - and check again when the first
    answer was a guess about someone else's publishing pipeline.*
    """
    rows = _get(REGIONS_URL)
    if not rows:
        return None
    newest = max(r["observed_date"] for r in rows)
    today = [r for r in rows if r["observed_date"] == newest]
    log.debug("solar_regions: %d rows, %d on %s, %d discarded as older",
              len(rows), len(today), newest, len(rows) - len(today))

    # Positions for a caller drawing the disc. Heliographic latitude and
    # longitude are read from the `location` string ("S17W54") rather than the
    # numeric fields, because that spelling states its own hemispheres and the
    # sign convention on `longitude` has to be inferred. A region with neither
    # is carried without a position rather than dropped: it still counts.
    groups = []
    for r in today:
        lat, lon = _location(r.get("location"))
        groups.append({
            "region": r.get("region"),
            "spots": r.get("number_spots") or 0,
            "area": r.get("area") or 0,
            "spot_class": r.get("spot_class"),
            "latitude": lat,
            "longitude": lon,
        })
    return {
        "groups": sorted(groups, key=lambda g: g["area"], reverse=True),
        "forecast_issued": any((r.get("c_flare_probability") or 0)
                               or (r.get("m_flare_probability") or 0)
                               or (r.get("x_flare_probability") or 0)
                               for r in today),
        "date": newest,
        "regions": len(today),
        "spots": sum((r.get("number_spots") or 0) for r in today),
        "area": sum((r.get("area") or 0) for r in today),
        "c_probability": max((r.get("c_flare_probability") or 0) for r in today),
        "m_probability": max((r.get("m_flare_probability") or 0) for r in today),
        "x_probability": max((r.get("x_flare_probability") or 0) for r in today),
        # The largest group is what an observer with a filtered telescope would
        # actually be looking at, so it is worth naming.
        "largest": max(today, key=lambda r: r.get("area") or 0).get("region"),
    }


def fetch_xray():
    """The day's peak flare and the current level, from the long band.

    ⇒ PEAK-OVER-A-DAY AND LATEST-SAMPLE ARE DIFFERENT CLAIMS and differ by a
    class routinely, so both are returned and a caller must say which it is
    printing.

    ⚠ THE CONTAMINATION FLAG IS NOT THE GUARD IT LOOKS LIKE. SWPC's own
    misspelled `electron_contaminaton` (do not correct it - it is the wire
    format) is set on the SHORT band and effectively never on the long one:
    8,343 of 10,078 short-band rows carried it over a week against 0 of 10,078
    long-band rows, on both satellites. It is dropped here anyway because it
    costs nothing and the era could change, but the band filter above is what
    actually does the work, and a check asserting this gate rejects something
    will fail on clean data.
    """
    rows = _get(XRAY_URL)
    long_band = [r for r in rows if r.get("energy") == LONG_BAND]
    clean = [r for r in long_band
             if not r.get("electron_contaminaton") and r.get("flux")]
    log.debug("xrays: %d rows, %d long band, %d after contamination",
              len(rows), len(long_band), len(clean))
    if not clean:
        return None
    peak = max(clean, key=lambda r: r["flux"])
    latest = clean[-1]
    return {
        "peak_class": flare_class(peak["flux"]),
        "peak_time": peak["time_tag"],
        "latest_class": flare_class(latest["flux"]),
        "latest_time": latest["time_tag"],
    }


def fetch_f107():
    """The 10.7 cm radio flux, the standard one-number index of solar activity.

    ⚠ `/json/f107_cm_radio_flux.json` 404s; the working path is the products
    summary, which answers with a single-row list.
    """
    rows = _get(F107_URL)
    if not rows:
        return None
    return rows[0].get("flux")


def _donki_time(value):
    """A DONKI timestamp as an aware UTC datetime, or None.

    They arrive as `2026-07-02T18:24Z` - a trailing Z and no seconds - which
    fromisoformat accepts only on newer Pythons. Normalised here so the module
    does not depend on which one the Pi is running.
    """
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    log.debug("Unparsed DONKI time %r", value)
    return None


def fetch_cme(now=None):
    """The soonest modelled CME arrival still ahead of us, or None.

    ⇒ THIS IS THE HONEST UPSTREAM OF THE AURORA PAGE. All three geomagnetic
    storms in the probe's sixty-day window traced back to a linked CME carrying
    a predicted Kp, so an arrival with a Kp attached is a real statement about
    what the sky may do in a day or two - not a second guess at the aurora
    model, which speaks only about now.

    ⚠ A GLANCING BLOW IS REPORTED AS SUCH. `isEarthGB` distinguishes a flank
    encounter from a direct hit, and the two are not worth the same sentence.

    Only the analyses DONKI marks most accurate are considered. A single CME
    routinely carries several, made at different times from different
    instruments, and averaging them would invent a run that nobody modelled.
    """
    now = now or datetime.now(timezone.utc)
    end = now.date() + timedelta(days=1)
    rows = _get(DONKI_CME_URL, {"startDate": str(end - timedelta(days=CME_WINDOW_DAYS)),
                                "endDate": str(end)}, timeout=30)
    horizon = now + timedelta(days=CME_LOOKAHEAD_DAYS)
    best = None
    for cme in rows:
        for analysis in cme.get("cmeAnalyses") or []:
            if not analysis.get("isMostAccurate"):
                continue
            for run in analysis.get("enlilList") or []:
                arrival = _donki_time(run.get("estimatedShockArrivalTime"))
                if arrival is None or not (now < arrival <= horizon):
                    continue
                # The predicted Kp comes as three figures from one run. The
                # maximum is quoted because it is the one that decides whether
                # anything is visible, and a caller cannot usefully print three.
                kp = max((run.get(k) or 0)
                         for k in ("kp_90", "kp_135", "kp_180")) or None
                entry = {
                    "arrival": arrival,
                    "speed_kms": analysis.get("speed"),
                    "kp": kp,
                    "glancing": bool(run.get("isEarthGB")),
                    "source": cme.get("sourceLocation"),
                    "started": _donki_time(cme.get("startTime")),
                }
                if best is None or entry["arrival"] < best["arrival"]:
                    best = entry
    return best


def _serialise(data):
    """Datetimes to ISO strings, for the disk cache."""
    out = dict(data)
    for key, value in out.items():
        if isinstance(value, dict):
            out[key] = _serialise(value)
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
    return out


def _revive(data, keys):
    for key in keys:
        if isinstance(data.get(key), str):
            try:
                data[key] = datetime.fromisoformat(data[key])
            except ValueError:
                data[key] = None
    return data


def activity(now=None):
    """Spots, flares, radio flux and any inbound CME, or None.

    NETWORK on a cache miss, at most one round per refresh interval and none at
    all while a failure cooldown runs - the shape core.satellites uses, and for
    the same reason: a display whose cache has expired would otherwise retry on
    every data refresh.

    A partial answer is still an answer. Four independent feeds sit behind this
    and one of them failing should cost its own line rather than the page, so
    each is caught separately and its absence returned as None.
    """
    global _last_failure

    age = _cache_age(ACTIVITY_CACHE)
    if age is not None and age < timedelta(minutes=REFRESH_MINUTES):
        return json.loads(ACTIVITY_CACHE.read_text(encoding="utf-8"))

    def cached_or_none():
        # Degrade to correct rather than to stale: past the hard age these
        # figures describe a Sun that has moved on.
        if age is None:
            return None
        if age < timedelta(hours=MAX_AGE_HOURS):
            return json.loads(ACTIVITY_CACHE.read_text(encoding="utf-8"))
        log.warning("Cached solar conditions are %s old; refusing them.", age)
        return None

    if _last_failure is not None:
        if datetime.now(timezone.utc) - _last_failure < timedelta(
                minutes=FETCH_COOLDOWN_MINUTES):
            return cached_or_none()

    # ⇒ "NOTHING TO REPORT" AND "COULD NOT ASK" ARE RECORDED SEPARATELY. Both
    # leave the value empty, and a caller that cannot tell them apart has to
    # either stay silent about a quiet Sun or claim quiet when it simply failed
    # to look. This matters most for the CME, whose normal state IS absence:
    # without the distinction a page saying "none expected" would say it just as
    # confidently with the network down.
    feeds = (("regions", fetch_regions), ("xray", fetch_xray),
             ("f107", fetch_f107), ("cme", lambda: fetch_cme(now)))
    out, failures = {"unavailable": []}, 0
    for key, fn in feeds:
        try:
            out[key] = fn()
        except Exception as e:
            log.warning("Solar feed %s unavailable (%s).", key, e)
            out[key] = None
            out["unavailable"].append(key)
            failures += 1

    # Counted from the feed list rather than written as a literal: a fifth feed
    # added above would otherwise leave this comparing against four forever, and
    # the cooldown that protects a throttled endpoint would silently stop firing
    # - a failure that shows up as extra traffic, not as an error.
    if failures == len(feeds):
        _last_failure = datetime.now(timezone.utc)
        return cached_or_none()

    out["fetched"] = datetime.now(timezone.utc).isoformat()
    _last_failure = None
    ACTIVITY_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVITY_CACHE.write_text(json.dumps(_serialise(out), default=str),
                              encoding="utf-8")
    return json.loads(json.dumps(_serialise(out), default=str))


# ------------------------------------------------------------------ eclipses

def _discs(obs, when):
    """(separation, solar radius, lunar radius, sun altitude), all in degrees.

    ⚠ `body.size` IS IN ARCSECONDS, so dividing by 3600 already gives degrees.
    Passing that through math.degrees as well inflates both radii by a factor of
    57 and reports an eclipse at every new moon - which is what the first probe
    did, and what the empty-case control caught.

    Topocentric because the observer is set: lunar parallax is nearly a degree
    and is the whole reason an eclipse is partial in one town and total in the
    next, so it cannot be left out.
    """
    obs.date = when
    sun, moon = ephem.Sun(), ephem.Moon()
    sun.compute(obs)
    moon.compute(obs)
    return (math.degrees(float(ephem.separation(sun, moon))),
            sun.size / 3600.0 / 2.0,
            moon.size / 3600.0 / 2.0,
            math.degrees(sun.alt))


def obscuration(sep, r_sun, r_moon):
    """Fraction of the solar disc AREA covered. NOT the magnitude.

    The lens-shaped overlap of two circles. Total and annular phases are the
    degenerate cases where one disc sits wholly inside the other.
    """
    if sep >= r_sun + r_moon:
        return 0.0
    if sep <= abs(r_moon - r_sun):
        return min(1.0, (r_moon / r_sun) ** 2)
    d2, s2, m2 = sep * sep, r_sun * r_sun, r_moon * r_moon
    a1 = math.acos(max(-1.0, min(1.0, (d2 + s2 - m2) / (2 * sep * r_sun))))
    a2 = math.acos(max(-1.0, min(1.0, (d2 + m2 - s2) / (2 * sep * r_moon))))
    return (s2 * (a1 - math.sin(2 * a1) / 2)
            + m2 * (a2 - math.sin(2 * a2) / 2)) / (math.pi * s2)


def _observer(lat, lon, elevation=0.0):
    obs = ephem.Observer()
    obs.lat, obs.lon, obs.elevation = str(lat), str(lon), elevation
    return obs


def _ephem_date(when):
    """A datetime as an ephem date, in UTC.

    ⚠ `ephem.Date` IGNORES tzinfo AND TREATS EVERYTHING AS UTC, so handing it an
    aware local datetime silently shifts every result by the offset - an hour
    through British summer time, more elsewhere. Everything reaching this module
    from a page is aware, because core.satellites made that its contract after
    the opposite convention crashed a render, so the conversion belongs here
    rather than at each call.
    """
    if when is None:
        return ephem.now()
    if isinstance(when, datetime):
        if when.tzinfo is not None:
            when = when.astimezone(timezone.utc).replace(tzinfo=None)
        return ephem.Date(when)
    return ephem.Date(when)


def _scan_day(obs, day, step_min):
    """Deepest eclipse over one UTC day WHILE THE SUN IS UP, or None.

    ⇒ THE HORIZON GATE IS PART OF THE MEASUREMENT, not a filter applied after
    it. The page describes what can be seen from this site, and an eclipse
    reaching its maximum below the horizon is a different event here from the
    one the almanacs list - the sweep found one on 2028-01-26 whose maximum sits
    0.4 degrees under it. Taking the deepest moment the Sun is actually visible
    reports the local circumstance rather than someone else's.
    """
    best = None
    start = ephem.Date(day)
    for i in range(0, 24 * 60, step_min):
        when = ephem.Date(start + i * ephem.minute)
        sep, r_sun, r_moon, alt = _discs(obs, when)
        if alt <= 0.0 or sep >= r_sun + r_moon:
            continue
        magnitude = (r_sun + r_moon - sep) / (2.0 * r_sun)
        if best is None or magnitude > best["magnitude"]:
            best = {"when": when, "magnitude": magnitude, "sun_altitude": alt,
                    "obscuration": obscuration(sep, r_sun, r_moon)}
    return best


def _contact(obs, centre, direction, limit_min=240):
    """When the discs first touch, searched outward from the maximum.

    Minute steps rather than a bisection: the quantity is monotonic either side
    of the maximum, four hours is a hard bound on any partial phase, and a
    minute is finer than a page that prints times to the minute can show.
    """
    for i in range(1, limit_min):
        when = ephem.Date(centre + direction * i * ephem.minute)
        sep, r_sun, r_moon, alt = _discs(obs, when)
        if sep >= r_sun + r_moon or alt <= 0.0:
            return when
    return None


def _compute_eclipse(lat, lon, elevation, now, horizon_days):
    """The next eclipse visible from here, searched new moon by new moon.

    A solar eclipse can only happen at new moon, so the search steps lunation by
    lunation rather than day by day - about 25 candidate days over two years
    instead of 730. Each candidate is scanned either side of the new moon
    because it can fall on either side of midnight UT.
    """
    obs = _observer(lat, lon, elevation)
    start = _ephem_date(now)
    end = float(start) + horizon_days
    when = start
    while float(when) < end:
        new_moon = ephem.next_new_moon(when)
        for offset in (-1, 0, 1):
            day = ephem.Date(math.floor(float(new_moon) - 0.5) + 0.5 + offset)
            if float(day) + 1 < float(start):
                continue
            if _scan_day(obs, day, ECLIPSE_COARSE_MIN) is None:
                continue
            hit = _scan_day(obs, day, ECLIPSE_FINE_MIN)
            if hit is None:
                continue
            begins = _contact(obs, hit["when"], -1)
            ends = _contact(obs, hit["when"], +1)
            return {
                "maximum": ephem.localtime(hit["when"]).astimezone(),
                "begins": ephem.localtime(begins).astimezone() if begins else None,
                "ends": ephem.localtime(ends).astimezone() if ends else None,
                "magnitude": hit["magnitude"],
                "obscuration": hit["obscuration"],
                "sun_altitude": hit["sun_altitude"],
            }
        when = ephem.Date(new_moon + 1)
    return None


def next_eclipse(lat, lon, elevation=0.0, now=None,
                 horizon_days=ECLIPSE_HORIZON_DAYS):
    """The next solar eclipse visible from this site, or None within the horizon.

    ⇒ CACHED UNTIL IT HAS PASSED, not for a duration. The answer changes exactly
    once - when the event ends - so an age-based cache would either recompute a
    two-year search needlessly or hold an event that is over. The site is stored
    with it, because a cached eclipse is a property of the place it was computed
    for and a caller may move.

    Needs NO NETWORK. This is the only thing on the display that does not, and
    it is what makes an eclipse the one event the panel can still announce with
    the internet down.
    """
    now = now or datetime.now().astimezone()
    if ECLIPSE_CACHE.exists():
        try:
            cached = json.loads(ECLIPSE_CACHE.read_text(encoding="utf-8"))
            same_site = (abs(cached.get("lat", 999) - lat) < 1e-6
                         and abs(cached.get("lon", 999) - lon) < 1e-6)
            event = cached.get("event")
            if same_site and event is None:
                return None
            if same_site and event:
                event = _revive(dict(event), ("maximum", "begins", "ends"))
                if event["ends"] and event["ends"] > now:
                    return event
        except (ValueError, TypeError) as e:
            log.warning("Unusable eclipse cache (%s); recomputing.", e)

    event = _compute_eclipse(lat, lon, elevation, now, horizon_days)
    ECLIPSE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ECLIPSE_CACHE.write_text(
        json.dumps({"lat": lat, "lon": lon,
                    "event": _serialise(event) if event else None}),
        encoding="utf-8")
    return event


def sun_up(lat, lon, elevation=0.0, now=None):
    """Whether the Sun is above the horizon here, which is this page's gate.

    Computed rather than read from the weather feed's sunrise sensors: the page
    must be able to appear on a panel whose Home Assistant is unreachable, and
    the arithmetic is free.
    """
    obs = _observer(lat, lon, elevation)
    obs.date = _ephem_date(now)
    sun = ephem.Sun()
    sun.compute(obs)
    return math.degrees(sun.alt) > 0.0
