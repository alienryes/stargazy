"""Whether aurora is visible from here tonight, and where to look for it.

⇒ THE QUERY IS NOT "PROBABILITY AT MY LATITUDE". Aurora emits between about 100
and 250 km up, so it is visible from far beyond the ground it sits over: an
observer sees whatever pokes above their horizon. Reading the model cell that
contains the site returns zero while a display is genuinely visible to the
north, which is the failure this module exists to avoid.

⇒ NOR IS IT "THE STRONGEST CELL TO THE NORTH". That is a property of southern
latitudes, not of aurora. The auroral oval passes overhead at high latitudes and
lies to the SOUTH in the southern hemisphere, so every cell within the horizon is
searched in every direction and the bearing is reported rather than assumed. The
same code gives Bristol an event every few years, Reykjavik a frequent one and
Hobart the aurora australis, none of them special-cased.

Source: NOAA SWPC's OVATION model, a US Government public domain product needing
no key or registration. It is a FORECAST, roughly 76 minutes ahead of its
observation time, and a probability rather than a sighting - both instants are
returned so a caller can say so rather than implying an observation.
"""
import logging
import math

import numpy as np
import requests

log = logging.getLogger(__name__)

OVATION_URL = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"
KP_URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
KP_FORECAST_URL = (
    "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json")

# Identifying a hobby display rather than pretending to be a browser. SWPC ask
# for a real agent and the endpoints are free; being a good citizen is the rent.
HEADERS = {"User-Agent": "touch2-stargazing-display (github.com/alienryes)"}

EARTH_R_KM = 6371.0

# Where the emission actually is. The green base sits near 100 km, but the high
# red emission reaches 200-250 km and is what gets reported from far south of the
# oval - so the taller figure is not optimism, it is the height of the part that
# clears a distant horizon first. Overridable: this is the honest knob for how
# far into the distance the display may claim to see.
DEFAULT_EMISSION_KM = 250.0

# Below this the model is not saying anything worth showing. Deliberately NOT
# per-site: the same cut gives a low-latitude site an event every few years and a
# high-latitude one a frequent page, because that difference is real rather than
# a setting.
DEFAULT_THRESHOLD_PCT = 10.0


def horizon_angle(emission_km=DEFAULT_EMISSION_KM):
    """Central angle to where emission at this height sits on the horizon.

    Exact rather than the sqrt(2Rh) flat approximation, which overstates the
    reach by about 2% at these heights.
    """
    return math.degrees(math.acos(EARTH_R_KM / (EARTH_R_KM + emission_km)))


def _geometry(lat, lon, glat, glon, emission_km):
    """Central angle, bearing and elevation from a site to grid points.

    All three vectorised over the grid: the OVATION product carries 65,160
    points and this runs on a Pi alongside a render loop.
    """
    la1, lo1 = math.radians(lat), math.radians(lon)
    la2, lo2 = np.radians(glat), np.radians(glon)
    dlon = lo2 - lo1

    # Central angle, via the haversine form - the law of cosines loses precision
    # at the small separations that matter most here.
    sin_half = np.sqrt(np.sin((la2 - la1) / 2) ** 2
                       + math.cos(la1) * np.cos(la2) * np.sin(dlon / 2) ** 2)
    theta = 2 * np.arcsin(np.clip(sin_half, 0.0, 1.0))

    bearing = np.degrees(np.arctan2(
        np.sin(dlon) * np.cos(la2),
        math.cos(la1) * np.sin(la2) - math.sin(la1) * np.cos(la2) * np.cos(dlon))) % 360.0

    # Elevation above the observer's horizon of emission at this height and
    # angular distance. Zero exactly at the horizon angle, 90 overhead.
    r = EARTH_R_KM + emission_km
    elevation = np.degrees(np.arctan2(r * np.cos(theta) - EARTH_R_KM,
                                      r * np.sin(theta)))
    return np.degrees(theta), bearing, elevation


# Resolution of the drawable field. Coarser than the model grid on purpose: the
# point is the shape of the storm from here, and OVATION resolves nothing finer
# than this at the distances that matter.
FIELD_AZ_BINS, FIELD_ALT_BINS = 96, 48
# Everything faintly lit goes into the field, not just what clears the alert
# threshold - otherwise the drawn shape would be cut off at its own edge and the
# storm would look smaller than the model says it is.
FIELD_FLOOR_PCT = 1.0


def lowest_visible_km(theta_deg):
    """The lowest altitude still above the horizon at this angular distance.

    Everything below it is behind the Earth. This is what decides the COLOUR an
    observer would see: the green line sits around 100-150 km, so once the
    lowest visible altitude climbs past that band only the red emission from
    200 km and up is left - which is exactly why a distant aurora reads red and
    one overhead reads green.
    """
    return EARTH_R_KM * (1.0 / np.cos(np.radians(theta_deg)) - 1.0)


def _bin_field(bearing, elevation, prob, theta, alt_max=90.0):
    """Per bearing/elevation bin: highest probability and lowest visible height.

    Returned as [(az, alt, prob, lowest_visible_km)]. alt_max is the full sky,
    matching the altitude axis a caller would plot it against; a caller drawing
    a different axis must rebin rather than rescale.
    """
    if bearing.size == 0:
        return []
    ai = np.clip((bearing / 360.0 * FIELD_AZ_BINS).astype(int), 0, FIELD_AZ_BINS - 1)
    ei = np.clip((elevation / alt_max * FIELD_ALT_BINS).astype(int), 0, FIELD_ALT_BINS - 1)
    flat = ai * FIELD_ALT_BINS + ei
    best = np.zeros(FIELD_AZ_BINS * FIELD_ALT_BINS)
    np.maximum.at(best, flat, prob)
    # The most favourable geometry in the bin, since that is what would be seen.
    low = np.full(FIELD_AZ_BINS * FIELD_ALT_BINS, np.inf)
    np.minimum.at(low, flat, lowest_visible_km(theta))
    idx = np.flatnonzero(best > 0)
    return [(float((i // FIELD_ALT_BINS + 0.5) * 360.0 / FIELD_AZ_BINS),
             float((i % FIELD_ALT_BINS + 0.5) * alt_max / FIELD_ALT_BINS),
             float(best[i]), float(low[i])) for i in idx]


def best_visible(grid, lat, lon, emission_km=DEFAULT_EMISSION_KM,
                 threshold_pct=DEFAULT_THRESHOLD_PCT):
    """The strongest aurora above this site's horizon, or None.

    `grid` is OVATION's [[lon, lat, probability], ...]. Longitudes arrive as
    0-360 and are used as they are; the geometry wraps on its own.
    """
    arr = np.asarray(grid, dtype=np.float64)
    if arr.size == 0:
        return None
    glon, glat, prob = arr[:, 0], arr[:, 1], arr[:, 2]

    theta, bearing, elevation = _geometry(lat, lon, glat, glon, emission_km)
    # Above the horizon AND worth reporting. The horizon test is what makes this
    # latitude-general; the probability test is what keeps quiet nights quiet.
    visible = (theta <= horizon_angle(emission_km)) & (prob >= threshold_pct)
    if not visible.any():
        return None

    idx = np.flatnonzero(visible)

    def describe(pick):
        return {
            "probability": float(prob[pick]),
            "bearing": float(bearing[pick]) % 360.0,
            "elevation": float(elevation[pick]),
            "distance_km": float(math.radians(theta[pick]) * EARTH_R_KM),
            "aurora_lat": float(glat[pick]),
            "aurora_lon": float(((glon[pick] + 180.0) % 360.0) - 180.0),
        }

    # TWO answers, because they are answers to different questions and the
    # strongest cell is routinely the one grazing the horizon - measured on live
    # data, where the best Hobart cell sat at 0.5 degrees, behind any terrain at
    # all and through the whole thickness of the atmosphere. "Where is it
    # strongest" is not "what can be seen", which is the question that matters.
    # Both are reported and the observer chooses; nothing is discarded.
    out = {
        "strongest": describe(idx[np.argmax(prob[idx])]),
        "highest": describe(idx[np.argmax(elevation[idx])]),
        # How much sky is lit, not just one cell: a single hot cell and a whole
        # visible oval look identical through a maximum alone.
        "visible_cells": int(visible.sum()),
    }
    # The storm's real extent, for drawing. Every faintly lit cell above the
    # horizon, binned - so what gets plotted is the model's own shape from this
    # position rather than an impression of one.
    lit = (theta <= horizon_angle(emission_km)) & (prob >= FIELD_FLOOR_PCT)
    out["field"] = _bin_field(bearing[lit], elevation[lit], prob[lit], theta[lit])
    return out


def fetch_ovation(timeout=30):
    """(grid, observation time, forecast time), or (None, None, None)."""
    try:
        r = requests.get(OVATION_URL, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        d = r.json()
        return d.get("coordinates"), d.get("Observation Time"), d.get("Forecast Time")
    except Exception as e:
        log.warning("Aurora forecast unavailable (%s).", e)
        return None, None, None


def fetch_kp(timeout=15):
    """Planetary Kp over the last three hours, or None.

    The highest reading in that span, NOT the most recent one. Kp is a
    three-hourly index and this feed reports a running estimate of the interval
    in progress, so it restarts from zero at 00, 03, 06 ... UTC and climbs. The
    final row is therefore a partial figure whenever a new interval has just
    begun, and reads far below the activity actually happening.

    Observed on the panel during the first real storm this page ever displayed
    (2026-08-08): rows to 20:59 read Kp 6, 21:00 to 21:02 read 0, and 21:03
    read 1, while OVATION still put a 72% cell in view. The header said "Kp 0"
    beside it. A three-hour window always spans at least one complete interval,
    so the maximum over it cannot fall back to zero mid-storm.

    Context only - this never gates the display.
    """
    try:
        r = requests.get(KP_URL, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return None
        # The feed is one row a minute, so 180 rows is three hours. Taking a
        # count rather than parsing time_tag keeps this free of the feed's
        # timestamp format, and a short feed simply yields what it has.
        recent = rows[-180:]
        return max(float(x["kp_index"]) for x in recent)
    except Exception as e:
        log.warning("Kp unavailable (%s).", e)
        return None


def fetch_kp_forecast(timeout=20):
    """[(time_tag, kp)] for the PREDICTED part of SWPC's three-day Kp outlook.

    ⚠ These rows are dicts, unlike most SWPC /products/ endpoints, which return
    an array of arrays with a header row. Code written against that shape gets
    nothing here and fails silently, so the filter below is on a dict key.
    """
    try:
        r = requests.get(KP_FORECAST_URL, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return [(x["time_tag"], float(x["kp"])) for x in r.json()
                if x.get("observed") == "predicted"]
    except Exception as e:
        log.warning("Kp forecast unavailable (%s).", e)
        return []


def visible_now(lat, lon, emission_km=DEFAULT_EMISSION_KM,
                threshold_pct=DEFAULT_THRESHOLD_PCT, with_kp=True):
    """Everything the aurora page needs, or None when there is nothing to say.

    Returning None on a quiet night is the point: the page is built only when
    this is not None, so the display costs nothing at all on the overwhelming
    majority of nights - which at temperate latitudes is very nearly all of them.
    """
    grid, observed, forecast = fetch_ovation()
    if not grid:
        return None
    best = best_visible(grid, lat, lon, emission_km, threshold_pct)
    if best is None:
        return None
    best["observed_at"] = observed
    best["forecast_at"] = forecast
    best["kp"] = fetch_kp() if with_kp else None
    best["kp_forecast"] = fetch_kp_forecast() if with_kp else []
    return best


def compass(bearing):
    """A bearing as a 16-point compass name."""
    points = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
    return points[int((bearing % 360.0) / 22.5 + 0.5) % 16]
