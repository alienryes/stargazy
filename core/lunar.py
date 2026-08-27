"""When the Moon next enters Earth's shadow, and how much of it can be seen here.

⇒ THE COMPANION TO core.solar's ECLIPSE HALF, AND IT FOLLOWS THE SAME RULE: an
eclipse is an appointment, the rest are conditions. Computed from ephem with no
network at all, and cached until it has passed rather than for a duration,
because the answer changes exactly once.

⇒ IT BELONGS ON PAGE 1 OF BOTH BUILDS, NOT ON THE SOLAR PAGE. The Moon card is
on the conditions page of both; the solar page is build10 only. A lunar eclipse
is also the more observable of the two - naked eye, no filter, no safety caveat
- so putting it behind a build10-only page would hide the easier event behind
the harder one.

⚠ ONLY UMBRAL ECLIPSES ARE RETURNED. A penumbral eclipse is a slight shading
that the eye cannot separate from an ordinary full Moon, and the penumbral
CONTACTS of a partial eclipse are just as unobservable: at the 2026-08-28 event
the penumbra was entered at 01:24 and nothing was visible until the umbra bit at
02:34, seventy minutes later. Reporting either would send someone out to look at
a Moon showing nothing, which is what the page-must-be-observable rule exists to
prevent. Penumbral magnitude is not computed and the penumbral radius is used
only to bound the search.

⚠ THE HARD CASE IS NOT WHETHER IT HAPPENS - IT IS THE SITE WINDOW. A lunar
eclipse is visible from a whole hemisphere at once, so "is it visible from here"
is a far weaker gate than for a solar eclipse and would pass almost everything.
What is genuinely local is that THE MOON CAN SET MID-ECLIPSE: on 2026-08-28 from
51.4N the umbral phase ends at 05:52 UTC with the Moon 4.7 degrees BELOW the
horizon, having set at 05:24 still deep in the shadow. A page printing the
geocentric contacts would name a time to watch something that has already gone.
The contacts are therefore clipped to the Moon's own rise and set, the way
core.solar._scan_day restricts a solar eclipse to while the Sun is up.

⚠ AND THE EVENT CAN DEEPEN AS IT BECOMES LESS OBSERVABLE, so the maximum is not
automatically the moment to name. That same night the greatest eclipse sits 8.9
degrees up in civil twilight while the easy viewing is the shallower phase an
hour and a half earlier. `sun_altitude` and `altitude` are returned at the
maximum so a caller can say so rather than pointing at the worst moment to look.
"""
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import ephem

log = logging.getLogger(__name__)

CACHE = Path(__file__).resolve().parent.parent / "cache" / "lunar_eclipse.json"

# Two years, matching core.solar. Lunar eclipses are commoner than solar ones at
# any one site - two or three umbral events a year are visible from somewhere in
# a given hemisphere - so this horizon is rarely reached.
HORIZON_DAYS = 730

# The shadow is searched either side of full moon, which is when the Moon is
# opposite the Sun and the only time it can be eclipsed. Four hours covers the
# offset between full moon and least separation from the antisolar point plus
# half the longest umbral phase.
SEARCH_HOURS = 4
COARSE_MIN = 10

R_EARTH_KM = 6378.14
AU_KM = 149597870.7

# ⇒ DANJON'S RULE, NOT THE 2% ONE, AND THE DIFFERENCE IS MEASURABLE. Earth's
# shadow is enlarged to account for the atmosphere, and there are two
# conventions: multiply the geometric radii by 1.02, or add a 1/85 enlargement
# of Earth's radius to each. They are not interchangeable - the first is
# multiplicative and inflates the much larger penumbra far more.
#
# Checked against NASA's canon for 2026-08-28 (umbral magnitude 0.9299,
# penumbral 1.9645, and its plot header states `Rule = CdT (Danjon)`), and
# against timeanddate's contacts for the same event:
#
#   rule     umbral mag   worst contact error
#   1.02     0.9376       120 s
#   Danjon   0.9327        23 s
#
# The 2% rule puts the printed figure at 94% where every published source says
# 93%. Danjon is what this module uses.
DANJON_DIVISOR = 85.0


def _shadow(when):
    """(separation, umbra, penumbra, moon radius) at `when`, degrees, geocentric.

    Separation is measured from the ANTISOLAR POINT - the centre of Earth's
    shadow - which is where the Moon has to arrive for an eclipse, and is not
    the same question as its separation from the Sun.

    Geocentric throughout, and deliberately: unlike a solar eclipse, where lunar
    parallax is the whole reason totality is a narrow track, the Moon really is
    inside Earth's shadow or it is not, and every observer who can see it sees
    the same phase at the same instant. Parallax enters this module only through
    the horizon clipping below, which is a question about the observer rather
    than about the eclipse.
    """
    d = ephem.Date(when)
    sun, moon = ephem.Sun(d), ephem.Moon(d)
    sep = float(ephem.separation(
        (float(sun.g_ra) + math.pi, -float(sun.g_dec)),
        (float(moon.g_ra), float(moon.g_dec))))
    par_moon = math.asin(R_EARTH_KM / (float(moon.earth_distance) * AU_KM))
    par_sun = math.asin(R_EARTH_KM / (float(sun.earth_distance) * AU_KM))
    enlarge = par_moon / DANJON_DIVISOR
    base = par_moon + par_sun + enlarge
    s_sun = float(sun.radius)
    return tuple(math.degrees(x) for x in
                 (sep, base - s_sun, base + s_sun, float(moon.radius)))


def _clearance(when, kind):
    """How far inside a shadow boundary the Moon is, degrees. Positive is inside.

    One function for every contact so the search cannot use a different
    expression for the boundary than the one the magnitude is computed from -
    the drift that puts a check and its subject quietly out of step.
    """
    sep, umbra, penumbra, r_moon = _shadow(when)
    edge = {"penumbral": penumbra + r_moon,
            "partial": umbra + r_moon,
            "total": umbra - r_moon}[kind]
    return edge - sep


def _contact(centre, direction, kind, limit_min=400):
    """The instant the Moon crosses a shadow boundary, bisected. Or None.

    Stepped by the minute to bracket the crossing and then bisected, rather than
    stepped to the answer: a minute-stepped result is the first sample PAST the
    boundary, so it lands up to a minute out and in a direction that depends on
    which side the search came from. That asymmetry is visible in a table of
    contacts as an event that is not symmetric about its own maximum.

    Returns None when the boundary is never crossed inside the bound, which for
    `total` is the ordinary state of a partial eclipse rather than a failure.
    """
    if _clearance(centre, kind) <= 0:
        return None
    lo = centre
    for i in range(1, limit_min):
        hi = ephem.Date(centre + direction * i * ephem.minute)
        if _clearance(hi, kind) <= 0:
            for _ in range(40):
                mid = ephem.Date((float(lo) + float(hi)) / 2)
                if _clearance(mid, kind) > 0:
                    lo = mid
                else:
                    hi = mid
            return ephem.Date((float(lo) + float(hi)) / 2)
        lo = hi
    return None


def _greatest(full_moon):
    """The instant of least separation from the shadow centre, near full moon."""
    span = SEARCH_HOURS * 60
    coarse = min(
        (ephem.Date(full_moon + i * ephem.minute)
         for i in range(-span, span + 1, COARSE_MIN)),
        key=lambda w: _shadow(w)[0])
    # Ternary search: the separation is a smooth minimum, so this converges
    # without needing a derivative and without assuming the coarse sample that
    # won is on either particular side of the true least.
    lo, hi = float(coarse) - COARSE_MIN * ephem.minute, \
        float(coarse) + COARSE_MIN * ephem.minute
    for _ in range(60):
        a, b = lo + (hi - lo) / 3.0, hi - (hi - lo) / 3.0
        if _shadow(a)[0] < _shadow(b)[0]:
            hi = b
        else:
            lo = a
    return ephem.Date((lo + hi) / 2.0)


def _observer(lat, lon, elevation=0.0):
    obs = ephem.Observer()
    obs.lat, obs.lon, obs.elevation = str(lat), str(lon), elevation
    return obs


def _altitude(obs, when):
    """The Moon's altitude in degrees at `when`, topocentric."""
    obs.date = ephem.Date(when)
    moon = ephem.Moon()
    moon.compute(obs)
    return math.degrees(float(moon.alt))


def _sun_altitude(obs, when):
    obs.date = ephem.Date(when)
    sun = ephem.Sun()
    sun.compute(obs)
    return math.degrees(float(sun.alt))


def _visible_span(obs, begins, ends):
    """The part of [begins, ends] with the Moon above the horizon, or (None, None).

    ⚠ USES EPHEM'S OWN RISE AND SET RATHER THAN A TEST ON ALTITUDE, and the two
    do not agree. Sampling for `alt > 0` looks like the more direct measurement
    and answers a different question: at the 2026-08-28 event the refracted
    centre crosses zero at 05:22:05 while `next_setting` returns 05:24:17, which
    is the 05:24 every almanac and every weather app prints. The gap is the
    convention - a set is the upper limb reaching the horizon through a standard
    atmosphere, not the centre reaching a geometric zero - and a panel printing
    a moonset two minutes off the published one reads as a defect in the clock.
    So the boundary is taken from the same function a reader's own source used.

    Rise and set also settle whether the Moon is up at first contact more
    reliably than an altitude test does, since both then come from one
    convention instead of one from each.
    """
    moon = ephem.Moon()
    obs.date = ephem.Date(begins)
    try:
        up = float(obs.previous_rising(moon)) > float(obs.previous_setting(moon))
    except ephem.AlwaysUpError:
        return ephem.Date(begins), ephem.Date(ends)
    except ephem.NeverUpError:
        return None, None

    if up:
        start = ephem.Date(begins)
    else:
        obs.date = ephem.Date(begins)
        start = obs.next_rising(moon)
        if float(start) >= float(ends):
            return None, None           # rises after the umbral phase is over

    obs.date = ephem.Date(start)
    try:
        setting = float(obs.next_setting(moon))
    except ephem.AlwaysUpError:
        return ephem.Date(start), ephem.Date(ends)
    return ephem.Date(start), ephem.Date(min(setting, float(ends)))


def _local(when):
    return ephem.localtime(ephem.Date(when)).astimezone() if when else None


def _compute(lat, lon, elevation, now, horizon_days):
    """The next umbral lunar eclipse with any of it above this horizon, or None.

    Steps full moon by full moon - the only time an eclipse can happen - so a
    two-year search costs about twenty-five candidates rather than seven hundred
    days, which is the same economy core.solar._compute_eclipse gets from
    stepping new moons.
    """
    obs = _observer(lat, lon, elevation)
    start = ephem.Date(now.astimezone(timezone.utc).replace(tzinfo=None))
    end = float(start) + horizon_days
    when = start
    while float(when) < end:
        full = ephem.next_full_moon(when)
        when = ephem.Date(float(full) + 1)
        peak = _greatest(full)
        if _clearance(peak, "partial") <= 0:
            continue                      # penumbral at best, or no eclipse
        begins = _contact(peak, -1, "partial")
        ends = _contact(peak, +1, "partial")
        if begins is None or ends is None:
            continue
        if float(ends) < float(start):
            continue                      # already over
        visible_from, visible_to = _visible_span(obs, begins, ends)
        if visible_from is None:
            continue                      # umbral phase wholly below the horizon

        sep, umbra, _penumbra, r_moon = _shadow(peak)
        total_begins = _contact(peak, -1, "total")
        total_ends = _contact(peak, +1, "total")
        return {
            "total": total_begins is not None,
            "magnitude": (umbra + r_moon - sep) / (2.0 * r_moon),
            "begins": _local(begins),
            "maximum": _local(peak),
            "ends": _local(ends),
            "total_begins": _local(total_begins),
            "total_ends": _local(total_ends),
            # The clipped pair is what a caller should print. Both are always
            # present on a returned event, because an event with neither would
            # have been rejected above.
            "visible_from": _local(visible_from),
            "visible_to": _local(visible_to),
            # Stated rather than left to be compared, because the comparison is
            # against a float date a caller does not hold. A minute of slack, so
            # an eclipse whose last contact falls seconds either side of moonset
            # is not announced as cut short over a difference nobody can see.
            "rises_during": (float(visible_from) - float(begins)) > ephem.minute,
            "sets_during": (float(ends) - float(visible_to)) > ephem.minute,
            "altitude": _altitude(obs, peak),
            "sun_altitude": _sun_altitude(obs, peak),
        }
    return None


def _serialise(event):
    return {k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in event.items()}


def _revive(event):
    out = dict(event)
    for key in ("begins", "maximum", "ends", "total_begins", "total_ends",
                "visible_from", "visible_to"):
        if isinstance(out.get(key), str):
            try:
                out[key] = datetime.fromisoformat(out[key])
            except ValueError:
                out[key] = None
    return out


def is_imminent(event, now, hours):
    """Whether the Moon card should be given over to this eclipse.

    Bounded at BOTH ends by the local window rather than the geocentric one. The
    far end is `visible_to`, not `ends`: once the Moon has set the event is over
    here whatever the shadow is still doing, and a card counting through an
    eclipse nobody can see is the failure this module exists to avoid.
    """
    if not event or not event["visible_from"]:
        return False
    return (event["visible_from"] - now).total_seconds() <= hours * 3600 \
        and now <= event["visible_to"]


def summary(event, now):
    """Ready-made lines for the Moon card, shortest first.

    ⇒ THE STRINGS LIVE HERE BECAUSE THERE ARE TWO BUILDS. The 5" panel has room
    for two caption lines and the 10.1" for four, so each picks how many of
    these it can carry - but the wording, the rounding and the decision about
    what to count towards are one implementation. A feature written into one
    build's display.py and not the other is this project's most repeated bug.

    ⚠ EVERY TIME HERE IS THE LOCAL WINDOW, NOT THE GEOCENTRIC CONTACT. On
    2026-08-28 the shadow leaves the Moon at 06:52 BST and the Moon set at
    06:24; `window` prints the second, and `note` says why it stops early.
    """
    heading = ("TOTAL LUNAR ECLIPSE" if event["total"]
               else "PARTIAL LUNAR ECLIPSE")

    start, stop = event["visible_from"], event["visible_to"]

    # ⚠ NOTHING HERE IS A COUNTDOWN, AND THAT IS NOT AN OVERSIGHT. Both builds
    # draw page 1 into an overlay that is CACHED between data refreshes - which
    # is why the clock is drawn per frame instead - so "starts in 1h 30m" baked
    # into it would sit frozen for the whole refresh interval and be read as the
    # wrong time by exactly the amount nobody can see. Absolute times stay true
    # however old the overlay is, and the live clock is already on the screen
    # beside them for the reader to subtract from.
    day = "" if start.date() == now.date() else f"{start:%A %d %B}"

    # "moonset" rather than a bare time: the end of the window and the end of
    # the eclipse are different facts, and printing the earlier one unlabelled
    # would read as the eclipse itself finishing there.
    tail = f"{stop:%H:%M} moonset" if event["sets_during"] else f"{stop:%H:%M}"
    window = f"{start:%H:%M} - {tail}   ·   "
    # ⚠ UMBRAL MAGNITUDE EXCEEDS 1 AT A TOTAL ECLIPSE, so a percentage is the
    # wrong figure there: "142% of the diameter covered" is arithmetically what
    # the definition gives and reads as a mistake, since a disc cannot be more
    # than wholly covered. Past totality the quantity a viewer wants is how long
    # it lasts, not how deep it goes.
    if event["total"] and event["total_begins"] and event["total_ends"]:
        window += (f"total {event['total_begins']:%H:%M}-"
                   f"{event['total_ends']:%H:%M}")
    else:
        window += f"{event['magnitude'] * 100:.0f}%"

    if event["sets_during"]:
        # ⚠ DIFFERENCED AFTER TRUNCATING TO THE MINUTE, because both endpoints
        # are PRINTED to the minute and a reader can subtract them. From the
        # raw seconds this read "27 min" beside a printed 06:24 and 06:52 - a
        # 27m56s gap floored - and the panel contradicted itself in a way
        # arithmetic on its own face exposes. Truncating first makes the stated
        # figure equal to the subtraction the reader can do.
        minute = {"second": 0, "microsecond": 0}
        lost = int((event["ends"].replace(**minute)
                    - stop.replace(**minute)).total_seconds() // 60)
        note = (f"The Moon sets {lost} min before the shadow leaves it, "
                f"{event['ends']:%H:%M}")
    elif event["rises_during"]:
        note = f"Already eclipsed when it rises at {start:%H:%M}"
    else:
        # No truncation to report, so the space says how hard it will be to
        # see instead - the eclipse can deepen as it becomes less observable,
        # and altitude and twilight are what decide that.
        note = f"{event['altitude']:.0f}° up at maximum"
        if event["sun_altitude"] > -18.0:
            note += ", in twilight"
    return {"heading": heading, "window": window, "note": note, "day": day}


def next_eclipse(lat, lon, elevation=0.0, now=None, horizon_days=HORIZON_DAYS):
    """The next lunar eclipse observable from this site, or None in the horizon.

    Needs NO NETWORK, which is the property core.solar values in its own eclipse
    half and the reason both survive a feed failure.

    ⇒ CACHED UNTIL IT HAS PASSED, not for an age. Keyed on the MAXIMUM rather
    than on `ends` - the same reasoning as core.solar.next_eclipse, where a
    contact time that failed to revive would make the event permanently fail its
    own cache test and rerun a two-year search on every refresh, on a Pi. The
    site is stored with it because the horizon clipping makes a cached event a
    property of the place it was computed for.
    """
    now = now or datetime.now().astimezone()
    if CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            same_site = (abs(cached.get("lat", 999) - lat) < 1e-6
                         and abs(cached.get("lon", 999) - lon) < 1e-6)
            event = cached.get("event")
            if same_site and event is None:
                return None
            if same_site and event:
                event = _revive(event)
                if event["maximum"] and (event["ends"] or event["maximum"]) > now:
                    return event
        except (ValueError, TypeError) as e:
            log.warning("Unusable lunar eclipse cache (%s); recomputing.", e)

    event = _compute(lat, lon, elevation, now, horizon_days)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(
        json.dumps({"lat": lat, "lon": lon,
                    "event": _serialise(event) if event else None}),
        encoding="utf-8")
    return event
