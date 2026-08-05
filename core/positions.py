"""Where things are in the sky, computed here rather than read from a report.

UpTonight's reports do carry alt/az, but the object and body reports are sampled
at DIFFERENT instants - measured on real reports, about three hours apart - so
anything plotting both populations together has to compute its own or it puts
two different moments on one axis. Both reports carry right ascension and
declination, which is all this needs.

Computing it also makes the answer live: the reports are written once a day by a
midday timer, while this recomputes on every data refresh.

ephem arrives with pyastroweatherio and is listed explicitly in each build's
requirements, since a build using Home Assistant as its weather source would not
otherwise pull it in.
"""
import math
from datetime import timedelta

import ephem


def observer(lat, lon, elevation=0.0, when=None):
    o = ephem.Observer()
    o.lat, o.lon = str(lat), str(lon)
    o.elevation = elevation
    if when is not None:
        o.date = ephem.Date(when)
    return o


def alt_az(obs, ra_deg, dec_deg):
    """(altitude, azimuth) in degrees for a J2000 position."""
    body = ephem.FixedBody()
    body._ra = math.radians(ra_deg)
    body._dec = math.radians(dec_deg)
    body._epoch = ephem.J2000
    body.compute(obs)
    return math.degrees(body.alt), math.degrees(body.az)


def plot_instant(window):
    """The moment a sky plot should represent, and how to label it.

    While it is dark, "now" is the only honest answer. Outside the window a plot
    of now would show a daylit sky, so it shows the middle of tonight's darkness
    instead - and says so, because a chart that silently means a different time
    than the viewer assumes is worse than one that admits it.
    """
    import datetime as _dt

    now = _dt.datetime.now().astimezone()
    dusk, dawn = window if window else (None, None)
    if dusk and dawn and dusk <= now <= dawn:
        return now, "now"
    if dusk and dawn and dawn > dusk:
        mid = dusk + (dawn - dusk) / 2
        return mid, mid.strftime("at %H:%M")
    # No usable window (polar summer, or missing data): midnight is a defensible
    # stand-in and is labelled as a time rather than as "now".
    mid = now.replace(hour=0, minute=0, second=0) + timedelta(days=1)
    return mid, mid.strftime("at %H:%M")


def place(rows, obs, ra_key="right ascension", dec_key="declination"):
    """[(row, alt, az)] for rows carrying a J2000 position, skipping any without."""
    out = []
    for r in rows:
        ra, dec = r.get(ra_key), r.get(dec_key)
        if ra is None or dec is None:
            continue
        alt, az = alt_az(obs, ra, dec)
        out.append((r, alt, az))
    return out
