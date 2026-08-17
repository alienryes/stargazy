"""The two weather sources, and the one table that keeps them in step.

The display works with no Home Assistant on the network by computing the
conditions here with pyastroweatherio - the very library the HA integration
wraps, so the numbers are its numbers rather than a reimplementation of its
judgement. Home Assistant remains selectable, because the same data is worth
recording there for dashboards and automations.

Both paths build the identical entity-keyed dict of strings, which is what lets
the render code be written once.
"""
import logging
from datetime import datetime, timezone

import requests

from core.values import _dt, _f, _i

log = logging.getLogger(__name__)

# Every value the dashboard needs, as HA entity suffix -> pyastroweatherio
# property. ONE table, because the two weather sources must stay in step: the
# Home Assistant path uses the keys, the direct path uses the values, and the
# render code is keyed on the full entity id either way.
#
# ⚠ THE TWO PATHS NOW DIFFER IN ONE RESPECT, DELIBERATELY. The Home Assistant
# path interpolates the conditions between the current forecast hour and the
# next (see _interpolate_hour); the direct path serves the hour's row as
# published. Both are honest readings of the same hourly series and the values
# agree on the hour, but between hours the HA path moves and the direct one
# steps. The table above still governs WHICH values exist and what they are
# called - that part has not diverged - and the direct path can be brought into
# line by giving it the same treatment against pyastroweatherio's own hourly
# forecast. Recorded here rather than left for someone to notice from a diff.
HA_PREFIX = "sensor.astroweather_backyard_"

FIELDS = {
    "astronomical_night_duration":           "night_duration_astronomical",
    "deepsky_forecast_today":                "deepsky_forecast_today",
    "deepsky_forecast_today_description":    "deepsky_forecast_today_desc",
    "deepsky_forecast_tomorrow":             "deepsky_forecast_tomorrow",
    "deepsky_forecast_tomorrow_description": "deepsky_forecast_tomorrow_desc",
    "cloud_cover":                           "cloudcover_percentage",
    # The same sky split by height. cloud_cover above is the RAW fraction, which
    # counts thin cirrus as heavily as thick stratus; these are what OBSCURATION
    # is derived from. See cloud_obscuration.
    "cloud_area_fraction_high":              "cloud_area_fraction_high_percentage",
    "cloud_area_fraction_medium":            "cloud_area_fraction_medium_percentage",
    "cloud_area_fraction_low":               "cloud_area_fraction_low_percentage",
    "seeing_percentage":                     "seeing_percentage",
    # NB the plain `transparency` property is a magnitude figure; the HA sensor
    # of that name carries the PERCENTAGE, which is what the bars expect.
    "transparency":                          "transparency_percentage",
    "calm_percentage":                       "calm_percentage",
    "moon_phase":                            "moon_phase",
    "moon_icon":                             "moon_icon",
    "moon_constellation":                    "moon_constellation",
    "moon_next_new_moon":                    "moon_next_new_moon",
    "moon_next_full_moon":                   "moon_next_full_moon",
    "moon_next_dark_night":                  "moon_next_dark_night",
    "sun_next_setting":                      "sun_next_setting",
    "sun_next_rising":                       "sun_next_rising",
    "2m_temperature":                        "temp2m",
    "2m_dewpoint":                           "dewpoint2m",
    "2m_relative_humidity":                  "rh2m",
    "10m_wind_speed":                        "wind10m_speed",
    "10m_wind_direction":                    "wind10m_direction",
    "lifted_index_plain":                    "lifted_index_plain",
    "moon_next_rising":                      "moon_next_rising",
    "moon_next_setting":                     "moon_next_setting",
    # The plain sun_next_setting/rising are CIVIL twilight; these are the real
    # astronomical dark bounds the timeline highlights.
    "sun_next_setting_astronomical":         "sun_next_setting_astro",
    "sun_next_rising_astronomical":          "sun_next_rising_astro",
}

ENTITIES = [HA_PREFIX + suffix for suffix in FIELDS]

# pyastroweatherio reports wind in m/s; Home Assistant serves the same figure in
# km/h. Everything downstream - the footer and the starfield drift coefficient
# in sky_params() - was tuned against km/h, so the direct path converts and km/h
# stays the internal unit. Only the footer converts again, to mph, for display.
MS_TO_KMH = 3.6
KMH_TO_MPH = 1 / 1.609344

# Derived, and not one of pyastroweatherio's own properties. Kept beside the
# real entities because everything downstream is keyed on an entity id.
OBSCURATION = HA_PREFIX + "cloud_obscuration"


def obscuration_of(states):
    """The obscuration figure for a states dict, for everything that reads it.

    Falls back to raw cover so a states dict from before this was derived - a
    fixture, or a Home Assistant instance queried directly - still works.
    """
    return _i(states.get(OBSCURATION, states.get(HA_PREFIX + "cloud_cover")))


def cloud_obscuration(states, tuning):
    """How much of the sky's light the cloud actually stops, as a percentage.

    WHY NOT cloud_cover. That property is int(cloud_area_fraction) - the raw
    fraction of sky with any cloud in it, at any height and any thickness. A sky
    of thin cirrus reads 100 there and looks like blue sky with veins in it. On
    2026-08-10 the feed reported 90% while the sky over the site was cirrus with
    the blue plainly visible through it, and the panel drew the 90.

    The layers combine as independent transmittances - 1 minus the product of
    what each lets through - with each weakened by how much that height of cloud
    obstructs. Those weakenings already exist in the configuration and already
    feed the deep-sky verdict; only the figure the sky layer drew ignored them.

    Falls back to the raw cover when the split is unavailable, which is how a
    Home Assistant instance whose AstroWeather integration does not publish the
    per-layer sensors will behave. Absence is tested on the state string, not on
    the parsed number: a missing sensor reads "unknown" and parses to 0, which
    is indistinguishable from a genuinely clear layer and would silently report
    a covered sky as clear.
    """
    layers = ("high", "medium", "low")
    raw = [states.get(f"{HA_PREFIX}cloud_area_fraction_{n}") for n in layers]
    if any(v is None or str(v).lower() in ("unknown", "unavailable", "none", "")
           for v in raw):
        return _i(states.get(HA_PREFIX + "cloud_cover"))
    transmitted = 1.0
    for name, value in zip(layers, raw):
        transmitted *= 1.0 - min(1.0, _i(value) * tuning[f"cloudcover_{name}_weakening"] / 100.0)
    return int(round((1.0 - transmitted) * 100.0))

# pyastroweatherio's own defaults. They are NOT the AstroWeather HA
# integration's DEFAULT_ constants, which are on a different scale for the
# weights and expressed as percentages for the weakenings.
TUNING_DEFAULTS = {
    "cloudcover_weight": 3,
    "cloudcover_high_weakening": 0.4,
    "cloudcover_medium_weakening": 0.7,
    "cloudcover_low_weakening": 1.0,
    "fog_weight": 3,
    "seeing_weight": 2,
    "transparency_weight": 1,
    "calm_weight": 2,
    "experimental_features": True,
    # Open-Meteo's own blend, which picks the highest-resolution model covering
    # the site. pyastroweatherio passes no model at all by default and gets the
    # same thing; the string is used here so a config file can override it.
    #
    # WHY NOT ecmwf_ifs025, which this was pinned to until 2026-08-11. That is a
    # 25 km global grid, and on a cloudless afternoon it reported 51% cover and
    # 60% high cloud at the reference site while best_match, ukmo_seamless and
    # the sky itself all read zero. Over the UK the blend resolves to models an
    # order of magnitude finer, and cloud is exactly the field where that tells.
    # A single global model can be pinned here where one is known to suit the
    # site better than the blend.
    "forecast_model": "best_match",
}


def fetch_states(ha_url, token):
    """Weather and sun/moon conditions, as entity -> state string.

    One session for the ~30 entity reads, closed on the way out: the connection
    is kept alive across them, and this runs on the data thread several times an
    hour for as long as the daemon is up, so a session left open each time is a
    socket left open each time.
    """
    states = {}
    with requests.Session() as session:
        session.headers["Authorization"] = f"Bearer {token}"
        for eid in ENTITIES:
            try:
                r = session.get(f"{ha_url}/api/states/{eid}", timeout=10)
                r.raise_for_status()
                states[eid] = r.json()["state"]
            except Exception as e:
                log.warning("Failed to fetch %s: %s", eid, e)
                states[eid] = "unknown"
        _interpolate_hour(session, ha_url, states)
    return states


# The forecast properties worth moving between one hour and the next: everything
# the four bars rest on, the three cloud layers obscuration is derived from, and
# the footer's air figures. All vary continuously and share their units across
# both sources.
#
# ⚠ NOTHING HERE IS A STATE, A TIME OR A DIRECTION. Averaging a condition string
# or a moonrise is meaningless, and a bearing averaged across the compass seam
# gives the opposite heading.
#
# ⚠ WIND IS DELIBERATELY ABSENT. The two sources publish it in different units -
# metres per second direct, km/h through Home Assistant, which fetch_states_direct
# converts for the hour's own value - so a shared blend would have to know which
# source it was serving. It feeds the footer and the starfield drift rather than
# any verdict, so the hour's step costs nothing worth that.
_SMOOTH = {"cloudcover_percentage", "cloud_area_fraction_high_percentage",
           "cloud_area_fraction_medium_percentage",
           "cloud_area_fraction_low_percentage",
           "seeing_percentage", "transparency_percentage", "calm_percentage",
           "temp2m", "dewpoint2m", "rh2m"}


def _astroweather_entity(session, ha_url):
    """The AstroWeather weather entity, found by what it carries.

    ⚠ NOT BY NAME. The entity is named after whatever the integration was called
    when it was set up - the reference install's reads `almaterrace` while every
    sensor beside it says `backyard` - so matching on the id would work here and
    nowhere else. Its `seeing_percentage` attribute is the signature: no other
    weather integration publishes one.
    """
    try:
        r = session.get(f"{ha_url}/api/states", timeout=15)
        r.raise_for_status()
        for s in r.json():
            if (s.get("entity_id", "").startswith("weather.")
                    and "seeing_percentage" in (s.get("attributes") or {})):
                return s["entity_id"]
    except Exception as e:
        log.debug("Could not look for an AstroWeather weather entity (%s).", e)
    return None


def _interpolate_hour(session, ha_url, states):
    """Move the conditions between this hour's forecast row and the next.

    ⇒⇒ THE ROW IS THE HOUR, FLOORED, AND THAT IS THE SOURCE'S RESOLUTION RATHER
    THAN A CHOICE MADE HERE. AstroWeather publishes one row per hour and its
    sensors carry the current row unchanged, so a value can be up to an hour old
    and a real change arrives as a single step. Measured on a live evening,
    cloudless ran 84, 64, 32, 8 over four consecutive hours - so for most of the
    hour before midnight the panel showed 84 while the sky was well past it.

    ⚠ THIS INVENTS VALUES THE MODEL DID NOT PUBLISH, and says so on the panel.
    Linear interpolation between two forecast hours is an ordinary reading of an
    hourly series, not new information: it cannot know that cloud arrived early.
    What it removes is the step and the staleness, both of which are artefacts of
    the publishing interval rather than statements about the sky.

    Best effort throughout. A failure here leaves `states` exactly as fetched -
    the floored row, which is what the display has always drawn - so the page
    degrades to correct rather than to empty.
    """
    entity = _astroweather_entity(session, ha_url)
    if not entity:
        return
    try:
        r = session.post(
            f"{ha_url}/api/services/weather/get_forecasts?return_response",
            json={"entity_id": entity, "type": "hourly"}, timeout=15)
        r.raise_for_status()
        rows = (r.json().get("service_response", {})
                .get(entity, {}).get("forecast") or [])
    except Exception as e:
        log.warning("Hourly forecast unavailable (%s); using the hour's row.", e)
        return
    pairs = []
    for row in rows:
        try:
            when = datetime.fromisoformat(row["datetime"])
        except (KeyError, ValueError):
            continue
        pairs.append((when, {_HA_FORECAST_ALIAS.get(k, k): v
                             for k, v in row.items()}))
    moved = _blend(pairs, states)
    if not moved:
        log.debug("No forecast row contained the current instant.")


# ⚠ HOME ASSISTANT'S FORECAST ROWS DO NOT USE pyastroweatherio's PROPERTY NAMES,
# and the overlap is close enough to look complete when it is not. The four bar
# percentages happen to match, so a check that watched only those would pass
# while the THREE CLOUD LAYERS obscuration is derived from were silently left on
# the hour - the page's headline figure stepping while the bars beside it moved.
_HA_FORECAST_ALIAS = {
    "cloud_area_fraction_high": "cloud_area_fraction_high_percentage",
    "cloud_area_fraction_medium": "cloud_area_fraction_medium_percentage",
    "cloud_area_fraction_low": "cloud_area_fraction_low_percentage",
    "temperature": "temp2m",
    "humidity": "rh2m",
}


def _blend(rows, states):
    """Move `states` between the forecast row containing now and the next.

    `rows` is [(aware datetime, mapping of pyastroweatherio property -> value)],
    in order. ONE implementation for both weather sources: they publish the same
    hourly series under the same property names, and the whole point of FIELDS is
    that neither path gets its own arithmetic. The alternative was two copies of
    a linear blend that would agree until one of them was edited.
    """
    now = datetime.now(timezone.utc)
    for (t0, a), (t1, b) in zip(rows, rows[1:]):
        if not t0 <= now < t1:
            continue
        span = (t1 - t0).total_seconds()
        if span <= 0:
            return 0
        f = (now - t0).total_seconds() / span
        moved = 0
        for suffix, prop in FIELDS.items():
            if prop not in _SMOOTH:
                continue
            lo, hi = a.get(prop), b.get(prop)
            try:
                lo, hi = float(lo), float(hi)
            except (TypeError, ValueError):
                continue
            states[HA_PREFIX + suffix] = _as_state(round(lo + (hi - lo) * f, 1))
            moved += 1
        log.debug("Interpolated %d values %.0f%% into the hour.", moved, f * 100)
        return moved
    return 0


def _as_state(value):
    """Render a library value the way Home Assistant's REST API would.

    The whole point is that both sources hand the render code the same thing:
    strings, with datetimes in ISO form (which _dt parses) and missing values
    as "unknown" (which _f/_i already fall back on).
    """
    if value is None:
        return "unknown"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def fetch_states_direct(loc, tuning):
    """The same dict as fetch_states(), fetched straight from Met.no/Open-Meteo.

    Imported lazily and deliberately: the library pulls in aiohttp, pandas and
    ephem (~195MB installed), and nobody running source = "homeassistant"
    should have to carry that.
    """
    import asyncio

    import aiohttp
    from pyastroweatherio import AstroWeather

    async def _fetch():
        async with aiohttp.ClientSession() as session:
            aw = AstroWeather(
                session,
                latitude=loc["latitude"],
                longitude=loc["longitude"],
                elevation=loc.get("elevation", 0),
                timezone_info=loc.get("timezone", "Etc/UTC"),
                cloudcover_weight=tuning["cloudcover_weight"],
                # fractions, not percentages - the HA integration scales its
                # own 40/70/100 defaults down before passing them
                cloudcover_high_weakening=tuning["cloudcover_high_weakening"],
                cloudcover_medium_weakening=tuning["cloudcover_medium_weakening"],
                cloudcover_low_weakening=tuning["cloudcover_low_weakening"],
                fog_weight=tuning["fog_weight"],
                seeing_weight=tuning["seeing_weight"],
                transparency_weight=tuning["transparency_weight"],
                calm_weight=tuning["calm_weight"],
                uptonight_path="",   # UpTonight is read off disk by read_targets
                experimental_features=tuning["experimental_features"],
                forecast_model=tuning["forecast_model"],
            )
            return (await aw.get_location_data(),
                    await aw.get_hourly_forecast())

    try:
        data, hourly = asyncio.run(_fetch())
    except Exception as e:
        log.warning("Direct weather fetch failed: %s", e)
        return {eid: "unknown" for eid in ENTITIES}

    if isinstance(data, list):        # get_location_data returns a 1-item list
        data = data[0]

    states = {}
    for suffix, prop in FIELDS.items():
        try:
            value = getattr(data, prop)
        except Exception as e:
            log.warning("No %s from pyastroweatherio: %s", prop, e)
            value = None
        if suffix == "10m_wind_speed" and value is not None:
            value = _f(value) * MS_TO_KMH
        states[HA_PREFIX + suffix] = _as_state(value)

    # The same blend the Home Assistant path gets, over the same hourly series -
    # `get_location_data` returns the containing hour's row unchanged, which is
    # where the step and the staleness come from. Best effort: a forecast that
    # cannot be read leaves the hour's own values in place.
    try:
        rows = [(r.forecast_time, {p: getattr(r, p, None) for p in _SMOOTH})
                for r in (hourly or [])]
        _blend([(t, v) for t, v in rows if t is not None], states)
    except Exception as e:
        log.warning("Hourly forecast unusable (%s); using the hour's row.", e)
    return states


def make_fetcher(config):
    """Return a zero-argument callable giving the states dict for this config."""
    weather = config.get("weather", {})
    source = weather.get("source", "direct")
    tuning = {**TUNING_DEFAULTS, **{k: v for k, v in weather.items() if k != "source"}}

    def with_obscuration(fetch):
        # Derived once, here, so both sources deliver it and the render code
        # never has to know which one it is talking to.
        def go():
            states = fetch()
            states[OBSCURATION] = str(cloud_obscuration(states, tuning))
            return states
        return go

    if source == "homeassistant":
        ha = config["ha"]
        url, token = ha["url"].rstrip("/"), ha["token"]
        return with_obscuration(lambda: fetch_states(url, token))
    if source != "direct":
        raise ValueError(
            f'weather.source is "{source}"; expected "direct" or "homeassistant"')
    loc = config["location"]
    return with_obscuration(lambda: fetch_states_direct(loc, tuning))


def compare_sources(config):
    """Fetch from both sources and diff them, value by value.

    Worth keeping in the tool rather than in a scratch script: the two sources
    are meant to agree, and the cheapest way to know they still do after a
    library or integration update is to ask the running install.

    Both are fetched back to back - AstroWeather refreshes every few minutes,
    so comparing readings taken minutes apart invents differences that are not
    there.
    """
    loc, ha = config["location"], config["ha"]
    weather = config.get("weather", {})
    tuning = {**TUNING_DEFAULTS, **{k: v for k, v in weather.items() if k != "source"}}

    direct = fetch_states_direct(loc, tuning)
    hass = fetch_states(ha["url"].rstrip("/"), ha["token"])

    same = 0
    for suffix in FIELDS:
        eid = HA_PREFIX + suffix
        d, h = direct[eid], hass[eid]
        # Times come back at differing precision - Home Assistant truncates to
        # whole seconds, the library keeps microseconds - so compare instants
        # with a tolerance rather than for equality.
        dd, hh = _dt(d), _dt(h)
        if dd and hh:
            equal = abs((dd - hh).total_seconds()) < 2.0
        else:
            equal = d == h
        if not equal and not (dd or hh):
            # numeric near-equality, so 45 and 45.0 are not a "difference"
            fd, fh = _f(d, None), _f(h, None)
            equal = fd is not None and fh is not None and abs(fd - fh) < 0.05
        same += equal
        print(f"{'ok ' if equal else 'DIFF'} {suffix:38s} "
              f"direct={d:<34.34} ha={h}")
    print(f"\n{same}/{len(FIELDS)} identical")
    return 0 if same == len(FIELDS) else 1
