"""When a bright satellite crosses this sky, and where to watch for it.

⇒ A PASS IS THE ONLY MAN-MADE THING THE SKY LAYER MAY HOLD. Everything drawn
into that layer claims "this is what is in front of you, in this direction", and
a satellite pass can honour it: the object is really there, at that bearing and
that altitude, at that minute. Contrast the aurora field and the Moon card,
which are dashboard content precisely because they cannot.

⇒ WHAT MAKES A PASS VISIBLE IS NOT DARKNESS ALONE, and this is the whole of why
the module is short. The satellite has to be in sunlight while the observer is
not, which is why passes belong to twilight rather than to the middle of the
night - deep in the night the station is in the Earth's shadow and there is
nothing to see. ephem answers the hard half of that directly with
`sat.eclipsed`, so no illumination geometry is computed here.

⇒ NOTHING HERE PREDICTS A BRIGHTNESS. The station's apparent magnitude depends
on which face is turned towards the observer, and no keyless source reports the
attitude. Range and altitude are reported instead, both of which are computed
rather than guessed; a caller wanting to rank passes should rank on those.

Source: CelesTrak's GP element sets, keyless and unregistered. Orbital elements
age, so the cache below has a hard expiry rather than an unbounded fallback.
"""
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ephem
import requests

log = logging.getLogger(__name__)

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php"

# ⚠ CELESTRAK THROTTLES, AND NOT GENTLY. Observed while building this: the same
# URL that had answered 200 began returning 503 and then dropping connections
# entirely after a handful of requests. Two consequences, both structural rather
# than cosmetic:
#
#   - ONE request covers every satellite here, by fetching the "stations" GROUP
#     rather than querying each catalogue number. CelesTrak's own guidance is to
#     pull groups for exactly this reason, and both stations are in that group.
#   - A failed fetch starts a cooldown. Without one, a display whose cache has
#     expired retries on every data refresh, which is how a throttle becomes a
#     block.
CELESTRAK_GROUP = "stations"
FETCH_COOLDOWN_MINUTES = 30
_last_failure = None

# Identifying a hobby display rather than pretending to be a browser, matching
# core.aurora - the endpoints are free and being a good citizen is the rent.
HEADERS = {"User-Agent": "stargazy (github.com/alienryes)"}

# The only two crewed stations bright enough to be worth naming on a panel. The
# ISS reaches roughly magnitude -3 at a high pass, brighter than anything in the
# sky but the Moon and Venus; Tiangong is a magnitude or two fainter and still
# an easy naked-eye object. Nothing else is added on purpose: the visible
# Starlink phenomenon is a freshly launched train rather than a catalogued
# object, and no keyless source predicts one.
SATELLITES = (("ISS", 25544), ("Tiangong", 48274))

# Beside the entry point, as core.imagery does, so a build's cache stays in one
# place rather than being buried inside the engine.
CACHE_ROOT = Path(__file__).resolve().parent.parent / "cache"
TLE_CACHE = CACHE_ROOT / "stations.tle"

# Refetch after this long, and REFUSE to predict from elements older than the
# hard limit. A cached element set asserts an orbit, and that assertion decays:
# the station manoeuvres, and drag is not perfectly modelled. Declining to
# predict is the honest failure here, because a stale TLE does not produce an
# obviously wrong answer - it produces a plausible one at the wrong minute.
TLE_REFRESH_HOURS = 12
TLE_MAX_AGE_DAYS = 3

# Below this culmination the pass is not worth announcing: it spends its whole
# duration in haze and behind whatever is on the horizon. This is not a
# refinement - the first pass a naive next_pass() call returned for this site
# culminated at 2 degrees 49 minutes, at dawn, and would have been shown.
MIN_CULMINATION_ALT = 10.0

# The observer's sky has to be dark enough for the object to stand out. Civil
# twilight is the usual cut for a magnitude -3 object and it is deliberately
# NOT the astronomical-night gate the aurora page uses: waiting for full
# darkness would discard the twilight passes, which are most of the good ones.
MAX_SUN_ALT = -6.0

# How far ahead to look. Two days spans the run of consecutive evening passes
# the station gives before its ground track drifts away, without predicting from
# elements that will have been refreshed several times by then.
DEFAULT_HOURS = 48

# Guard on the pass walk: each step advances past one set time, so this bounds
# the loop against a body that never sets rather than against a real sky.
MAX_STEPS = 400

# Samples along a pass when a caller asks for the path. A pass lasts about ten
# minutes, so this is roughly one point every fifteen seconds - far finer than a
# panel can resolve, and cheap enough beside a render loop that there is no
# reason to be sparing.
TRACK_SAMPLES = 48


def _cache_age():
    """How old the cached element set is, or None when there is not one."""
    if not TLE_CACHE.exists():
        return None
    return datetime.now(timezone.utc) - datetime.fromtimestamp(
        TLE_CACHE.stat().st_mtime, timezone.utc)


def _parse_group(text):
    """{catalogue number: [name, line1, line2]} from a three-line-per-object set."""
    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    out = {}
    for i in range(0, len(lines) - 2, 3):
        name, l1, l2 = lines[i:i + 3]
        if not l1.startswith("1 ") or not l2.startswith("2 "):
            continue
        try:
            out[int(l1[2:7])] = [name.strip(), l1, l2]
        except ValueError:
            continue
    return out


def fetch_elements(timeout=20):
    """{catalogue number: [name, line1, line2]} for the stations group, or {}.

    NETWORK on a cache miss, at most one request per refresh interval, and none
    at all while a failure cooldown is running.
    """
    global _last_failure

    age = _cache_age()
    if age is not None and age < timedelta(hours=TLE_REFRESH_HOURS):
        return _parse_group(TLE_CACHE.read_text(encoding="utf-8"))

    def cached_or_empty():
        # The cache is usable only inside the hard expiry. Past it, refusing is
        # the honest answer: a stale element set does not produce an obviously
        # wrong pass, it produces a plausible one at the wrong minute.
        if age is None:
            return {}
        if age < timedelta(days=TLE_MAX_AGE_DAYS):
            return _parse_group(TLE_CACHE.read_text(encoding="utf-8"))
        log.warning("Cached elements are %s old; refusing them.", age)
        return {}

    if _last_failure is not None:
        since = datetime.now(timezone.utc) - _last_failure
        if since < timedelta(minutes=FETCH_COOLDOWN_MINUTES):
            return cached_or_empty()

    try:
        r = requests.get(CELESTRAK_URL, headers=HEADERS, timeout=timeout,
                         params={"GROUP": CELESTRAK_GROUP, "FORMAT": "tle"})
        r.raise_for_status()
        # CelesTrak answers an unknown group with a 200 and a body saying so
        # rather than a 404, so the parsed shape is what proves the fetch.
        elements = _parse_group(r.text)
        if not elements:
            raise ValueError(f"no element sets in response: {r.text[:60]!r}")
        TLE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        TLE_CACHE.write_text(r.text.strip(), encoding="utf-8")
        _last_failure = None
        return elements
    except Exception as e:
        log.warning("Orbital elements unavailable (%s).", e)
        _last_failure = datetime.now(timezone.utc)
        return cached_or_empty()


def _local(when):
    """An ephem date as a timezone-AWARE local datetime.

    ephem.localtime returns a naive one, and everything a caller will compare
    these against - the clock on a page, timestamps out of Home Assistant - is
    aware. Mixing the two raises rather than quietly misreporting, but it raises
    inside the page render, which is a poor place to find out.
    """
    return ephem.localtime(when).astimezone()


def _sun_alt(obs):
    sun = ephem.Sun()
    sun.compute(obs)
    return math.degrees(sun.alt)


def _at(obs, sat, when):
    """(altitude, azimuth, sun altitude, eclipsed, range_km) at one instant.

    The observer's date is restored: a caller holds one observer across a whole
    walk, and ephem's own next_pass moves it.
    """
    saved = obs.date
    try:
        obs.date = when
        sat.compute(obs)
        return (math.degrees(sat.alt), math.degrees(sat.az), _sun_alt(obs),
                bool(sat.eclipsed), sat.range / 1000.0)
    finally:
        obs.date = saved


def _pass_after(obs, sat, when):
    """The next pass strictly after `when`, as a dict of raw ephem values.

    None when ephem cannot produce one, which happens for a body that never
    rises from this site and for an incomplete pass at the end of the walk.
    """
    saved = obs.date
    try:
        obs.date = when
        rise_t, rise_az, max_t, max_alt, set_t, set_az = obs.next_pass(sat)
        if None in (rise_t, max_t, set_t, max_alt):
            return None
        return {"rise_t": rise_t, "rise_az": rise_az, "max_t": max_t,
                "max_alt": max_alt, "set_t": set_t, "set_az": set_az}
    except (ephem.AlwaysUpError, ephem.NeverUpError, ValueError) as e:
        log.debug("No pass available (%s).", e)
        return None
    finally:
        obs.date = saved


def _track(obs, sat, rise_t, set_t, samples=TRACK_SAMPLES):
    """[(bearing, altitude)] along the pass, in degrees.

    COMPUTED at each sample rather than interpolated between rise, culmination
    and set. A satellite's path across a bearing-by-altitude plot is a curve,
    and three points joined by straight lines would be a drawing of an
    assumption rather than of the orbit.

    Altitudes are clamped at zero: the endpoints land a fraction below the
    horizon by rounding, and a caller plotting against an altitude axis has
    nowhere to put a negative.
    """
    out = []
    for i in range(samples + 1):
        when = ephem.Date(rise_t + (set_t - rise_t) * i / samples)
        alt, az, _, _, _ = _at(obs, sat, when)
        out.append((az % 360.0, max(0.0, alt)))
    return out


def passes(lat, lon, elevation=0.0, hours=DEFAULT_HOURS,
           min_alt=MIN_CULMINATION_ALT, max_sun_alt=MAX_SUN_ALT, now=None,
           with_track=False):
    """Visible passes of every satellite in SATELLITES, soonest first.

    A pass is reported only when all three gates hold at its culmination: it
    climbs above `min_alt`, the observer's sun is below `max_sun_alt`, and the
    satellite is not in the Earth's shadow. Each is checked at the culmination
    rather than over the whole track, so a pass entering shadow partway through
    is reported as visible - which it is, for the part that matters.

    Returns [] rather than None: the caller decides whether an empty sky is
    worth a page, and there is no failure to distinguish here.
    """
    out = []
    start = ephem.Date(now) if now is not None else ephem.now()
    end = ephem.Date(start + hours * ephem.hour)
    elements = fetch_elements()

    for name, catnr in SATELLITES:
        tle = elements.get(catnr)
        if tle is None:
            log.warning("No elements for %s (%s).", name, catnr)
            continue
        try:
            sat = ephem.readtle(*tle)
        except ValueError as e:
            log.warning("Unusable elements for %s (%s).", name, e)
            continue

        obs = ephem.Observer()
        obs.lat, obs.lon = str(lat), str(lon)
        obs.elevation = elevation

        when, steps = start, 0
        while when < end and steps < MAX_STEPS:
            steps += 1
            p = _pass_after(obs, sat, when)
            if p is None or p["set_t"] <= when:
                break
            # Step past this pass before any gate can skip the iteration, or a
            # rejected pass is found again forever.
            when = ephem.Date(p["set_t"] + ephem.minute)
            if p["max_t"] > end:
                break

            alt = math.degrees(p["max_alt"])
            if alt < min_alt:
                continue
            _, culm_az, sun_alt, eclipsed, range_km = _at(obs, sat, p["max_t"])
            if sun_alt > max_sun_alt or eclipsed:
                continue

            entry = {
                "name": name,
                "rise": _local(p["rise_t"]),
                "culminate": _local(p["max_t"]),
                "set": _local(p["set_t"]),
                "rise_bearing": math.degrees(p["rise_az"]) % 360.0,
                "set_bearing": math.degrees(p["set_az"]) % 360.0,
                # Where to actually look. Not the mean of the rise and set
                # bearings: the track is a curve, and on a high pass the two
                # ends can be most of the compass apart while the culmination
                # sits nowhere between them.
                "culminate_bearing": culm_az % 360.0,
                "max_altitude": alt,
                "range_km": range_km,
                "sun_altitude": sun_alt,
                "duration_min": (p["set_t"] - p["rise_t"]) * 24.0 * 60.0,
            }
            if with_track:
                entry["track"] = _track(obs, sat, p["rise_t"], p["set_t"])
            out.append(entry)

    out.sort(key=lambda p: p["culminate"])
    return out


def elements_age():
    """How old the cached element set is, as a short phrase for a footer.

    A pass time is only as current as the elements behind it, and a page that
    quotes a minute should be able to say how stale the arithmetic is.
    """
    age = _cache_age()
    if age is None:
        return "not cached"
    hours = age.total_seconds() / 3600.0
    if hours < 1.0:
        return f"{int(age.total_seconds() // 60)} min old"
    if hours < 48.0:
        return f"{int(hours)} h old"
    return f"{age.days} days old"


def next_visible(lat, lon, elevation=0.0, hours=DEFAULT_HOURS, **kw):
    """The soonest visible pass from here, or None when there is none.

    The shape core.aurora uses: None means there is nothing to say, so a caller
    can build a page only when this is not None and cost the panel nothing on
    the nights when no bright satellite crosses in a dark sky.
    """
    found = passes(lat, lon, elevation, hours, **kw)
    return found[0] if found else None
