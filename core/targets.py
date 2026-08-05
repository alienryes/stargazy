"""UpTonight's observing targets, read off disk.

UpTonight runs on the same Pi from a daily timer and writes these reports; they
are read straight from its output directory. Absent files simply mean it has not
run yet, or that the section is disabled (comets are off by default).
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from core.imagery import cutout
from core.values import _f

log = logging.getLogger(__name__)

UPTONIGHT_REPORTS = {
    "objects": "uptonight-report.json",
    "bodies":  "uptonight-bodies-report.json",
    "comets":  "uptonight-comets-report.json",
}


def _records(columns):
    """UpTonight writes pandas column-major JSON - {"mag": {"0": 8.4, ...}, ...}
    - so pivot it back into one dict per object. Key names are unchanged."""
    if not isinstance(columns, dict) or not columns:
        return []
    index = sorted(next(iter(columns.values())).keys(), key=lambda k: int(k))
    return [{col: values.get(i) for col, values in columns.items()} for i in index]


def read_targets(out_dir):
    """UpTonight's object/body/comet lists, empty if it has not run yet."""
    targets = {}
    for key, name in UPTONIGHT_REPORTS.items():
        path = Path(out_dir) / name
        if not path.exists():
            continue
        try:
            targets[key] = _records(json.loads(path.read_text()))
        except Exception as e:
            log.warning("Failed to read %s: %s", path, e)
    return targets


# How high each object actually gets. UpTonight gives alt/az for the planets and
# comets but nothing positional for deep-sky objects, so the cards derive it:
# peak altitude is 90 - |latitude - declination|, with declination coming
# straight out of UpTonight's own report file. (Until v3.0.0 that number was
# looked up from CDS's Sesame resolver and cached, because the MQTT transport
# then in use dropped the field; running UpTonight locally made both unnecessary.)
def peak(dec, lat):
    """(altitude, compass letter) at meridian transit. An object north of the
    zenith culminates due north, not south, which is the direction to face."""
    return 90.0 - abs(lat - dec), ("N" if dec > lat else "S")


def ut_dt(s):
    """UpTonight's transit stamps are US-format local time, or "" when it does
    not transit within the observing window."""
    try:
        return datetime.strptime(s, "%m/%d/%Y %H:%M:%S")
    except (ValueError, TypeError):
        return None


def load_cutouts(targets, limit, px=200):
    """{object id: image} for the objects the page will show. NETWORK on a cache
    miss, so this runs on the data thread, not the render loop."""
    images = {}
    for o in sorted(targets.get("objects") or [],
                    key=lambda o: (-_f(o.get("foto")), _f(o.get("mag"), 99)))[:limit]:
        oid = str(o.get("id", ""))
        pic = cutout(oid, _f(o.get("size"), 10.0), px)
        if pic is not None:
            images[oid] = pic
    return images
