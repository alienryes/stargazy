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
from datetime import datetime

import requests

from core.values import _dt, _f

log = logging.getLogger(__name__)

# Every value the dashboard needs, as HA entity suffix -> pyastroweatherio
# property. ONE table, because the two weather sources must stay in step: the
# Home Assistant path uses the keys, the direct path uses the values, and the
# render code is keyed on the full entity id either way.
HA_PREFIX = "sensor.astroweather_backyard_"

FIELDS = {
    "astronomical_night_duration":           "night_duration_astronomical",
    "deepsky_forecast_today":                "deepsky_forecast_today",
    "deepsky_forecast_today_description":    "deepsky_forecast_today_desc",
    "deepsky_forecast_tomorrow":             "deepsky_forecast_tomorrow",
    "deepsky_forecast_tomorrow_description": "deepsky_forecast_tomorrow_desc",
    "cloud_cover":                           "cloudcover_percentage",
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
    "forecast_model": "ecmwf_ifs025",
}


def fetch_states(ha_url, token):
    """Weather and sun/moon conditions, as entity -> state string."""
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"
    states = {}
    for eid in ENTITIES:
        try:
            r = session.get(f"{ha_url}/api/states/{eid}", timeout=10)
            r.raise_for_status()
            states[eid] = r.json()["state"]
        except Exception as e:
            log.warning("Failed to fetch %s: %s", eid, e)
            states[eid] = "unknown"
    return states


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
            return await aw.get_location_data()

    try:
        data = asyncio.run(_fetch())
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
    return states


def make_fetcher(config):
    """Return a zero-argument callable giving the states dict for this config."""
    weather = config.get("weather", {})
    source = weather.get("source", "direct")
    if source == "homeassistant":
        ha = config["ha"]
        url, token = ha["url"].rstrip("/"), ha["token"]
        return lambda: fetch_states(url, token)
    if source != "direct":
        raise ValueError(
            f'weather.source is "{source}"; expected "direct" or "homeassistant"')
    loc = config["location"]
    tuning = {**TUNING_DEFAULTS, **{k: v for k, v in weather.items() if k != "source"}}
    return lambda: fetch_states_direct(loc, tuning)


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
