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


def _mag_rank(o):
    """Catalogued magnitude, or 99 for an object that has none.

    UpTonight writes 0.0 rather than null when a target has no catalogued
    magnitude, so a plain float conversion reads it as magnitude zero - brighter
    than anything real - and sorts it to the front. The 99 fallback that used to
    sit in the sort key was always meant to send unknowns to the back; it simply
    never fired, because the field is present.

    Measured on the 9 Aug report: 25 of 40 objects carry 0.0, all of them LBN,
    vdB and Sh2 catalogue nebulae, which are extended and have no integrated
    magnitude. They filled the first 24 places and pushed M 31 to 25th, M 81 to
    28th and M 13 to last.
    """
    mag = _f(o.get("mag"))
    return mag if mag > 0 else 99.0


def rank_objects(objects):
    """UpTonight's deep-sky objects, best first: most of the night up, then
    brightest.

    Shared because three callers ranked independently and one of them is
    `load_cutouts`, which decides which imagery to FETCH. Had the orders drifted
    apart, the cards would have quietly fallen back to drawn glyphs for want of
    the right images, which looks like a network fault rather than a sort bug.
    """
    return sorted(objects or [], key=lambda o: (-_f(o.get("foto")), _mag_rank(o)))


def load_cutouts(targets, limit, px=200):
    """{object id: image} for the objects the page will show. NETWORK on a cache
    miss, so this runs on the data thread, not the render loop."""
    images = {}
    for o in rank_objects(targets.get("objects"))[:limit]:
        oid = str(o.get("id", ""))
        pic = cutout(oid, _f(o.get("size"), 10.0), px)
        if pic is not None:
            images[oid] = pic
    return images
