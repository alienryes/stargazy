#!/usr/bin/env python3
"""Render the solar page in each of its states, on the Pi, for looking at.

Run ON the Pi. core.fonts resolves two absolute Linux paths and otherwise falls
back to Pillow's default bitmap face without saying so, which has already put a
collision on the panel that a dev-box width check called fine - so every width
printed here is measured with the faces the panel actually uses.

    PYTHONPATH=/home/operations/stargazy python3 solar_preview.py

Instants are moved WHOLE: the gate, the eclipse search and the countdown all
take the same `now`, so each image is a page a user could really have rather
than one instant wearing another's clock.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

sys.path.insert(0, "/home/operations/stargazy")

import display  # noqa: E402
from core import solar  # noqa: E402
from core.fonts import font  # noqa: E402

OUT = Path("/home/operations/checks/solar")
OUT.mkdir(parents=True, exist_ok=True)
TZ = ZoneInfo("Europe/London")
LAT, LON = 51.44108266071185, -2.0060965418815617

# The panel composes the overlay over a painted sky. Reviewing the overlay alone
# would repeat the aurora page's recorded verification error, where transparency
# read as black and the glow was tuned against a picture the display never
# produces. A flat navy is not the real sky but it is the right ORDER, and every
# element here is text on it.
SKY = (10, 12, 28)


def save(name, img, note=None):
    if img is None:
        print(f"  {name:24} -> None (no page)")
        return
    frame = Image.new("RGB", img.size, SKY)
    frame.paste(img, (0, 0), img)
    if note:
        # Stated ON the image, per the standing rule: a preview that still needs
        # fabrication says so where the picture goes, not in a caption that gets
        # separated from it.
        # At the FOOT of the image. Stamped at the top it sat over the page
        # title, so the note about what was fabricated hid part of what it was
        # annotating.
        d = ImageDraw.ImageDraw(frame)
        f = font("IBMPlexSans-Bold.ttf", 26)
        w = int(d.textlength(note, font=f))
        d.rectangle([0, frame.height - 46, w + 40, frame.height], fill=(120, 20, 20))
        d.text((20, frame.height - 38), note, font=f, fill=(255, 255, 255))
    path = OUT / f"{name}.png"
    frame.save(path)
    print(f"  {name:24} -> {path}")


OVERFLOWS = []


def widths(label, lines, limit=display.W - 2 * display.MARGIN):
    """Measured with the panel's own faces. Anything over the limit collides."""
    d = ImageDraw.ImageDraw(Image.new("RGB", (10, 10)))
    print(f"\n  {label}  ({len(lines)} strings)")
    for text, f in lines:
        w = int(d.textlength(text, font=f))
        over = w > limit
        if over:
            OVERFLOWS.append((label, text, w))
        print(f"    {w:5}/{limit}  {text[:64]!r}{'  <-- OVERFLOWS' if over else ''}")


print("Rendering solar page states")
print("=" * 72)

# 1. Now. Daylight at the time of writing, quiet Sun, no CME, eclipse a year off.
now = datetime.now(TZ)
save("01_now", display.render_solar({}, LAT, LON, now=now))
print(f"     instant {now:%Y-%m-%d %H:%M %Z}")

# 2. Night: the gate itself. This must be None or the gate does not work.
night = now.replace(hour=1, minute=30)
save("02_night_must_be_none", display.render_solar({}, LAT, LON, now=night))

# 3. The eclipse band, 3 hours before first contact on the real event.
eclipse = solar.next_eclipse(LAT, LON, now=now)
print(f"\n     next eclipse: {eclipse['maximum']:%Y-%m-%d %H:%M %Z}  "
      f"magnitude {eclipse['magnitude']:.3f}  obscuration "
      f"{eclipse['obscuration']:.3f}  sun alt {eclipse['sun_altitude']:.1f}")
save("03_eclipse_3h_before",
     display.render_solar({}, LAT, LON,
                          now=eclipse["begins"] - timedelta(hours=3)))

# 4. In progress, at maximum.
save("04_eclipse_at_maximum",
     display.render_solar({}, LAT, LON, now=eclipse["maximum"]))

# 5. Just inside the band edge, which is where the countdown is longest.
save("05_eclipse_band_edge",
     display.render_solar({}, LAT, LON,
                          now=eclipse["begins"]
                          - timedelta(hours=display.SOL_ECLIPSE_BAND_HOURS - 0.1)))

# 6. Feeds down: the page must still carry the eclipse, and say the rest is
#    missing rather than printing nothing. The cache is cleared so there is
#    genuinely no data, rather than a stale copy standing in for the failure.
solar.ACTIVITY_CACHE.unlink(missing_ok=True)
real_urls = (solar.REGIONS_URL, solar.XRAY_URL, solar.F107_URL, solar.DONKI_CME_URL)
solar.REGIONS_URL = solar.XRAY_URL = solar.F107_URL = solar.DONKI_CME_URL = \
    "https://127.0.0.1:9/none"
save("06_feeds_down_eclipse_near",
     display.render_solar({}, LAT, LON,
                          now=eclipse["begins"] - timedelta(hours=2)))
save("07_feeds_down_ordinary_day", display.render_solar({}, LAT, LON, now=now))
(solar.REGIONS_URL, solar.XRAY_URL, solar.F107_URL,
 solar.DONKI_CME_URL) = real_urls
solar.ACTIVITY_CACHE.unlink(missing_ok=True)
# ⚠ CLEAR THE COOLDOWN THE FAILED RUN JUST SET, or every render below quietly
# gets nothing. It cost the first CME preview every other row on the page and
# looked like a page fault rather than a fault in the preview.
solar._last_failure = None

# 8. The CME row. No CME is inbound today, so the only honest way to see the row
#    is with a real model run from a window that had one - and the image says so.
cme = solar.fetch_cme(now=datetime(2026, 7, 1, tzinfo=timezone.utc))
if cme:
    data = solar.activity() or {}
    data["cme"] = solar._serialise(cme)
    original = display.solar_activity
    display.solar_activity = lambda: data
    save("08_cme_inbound", display.render_solar({}, LAT, LON, now=now),
         note=f"CME row from the real {cme['arrival']:%Y-%m-%d} model run; "
              f"every other figure is current")
    display.solar_activity = original
    print(f"     CME: arrives {cme['arrival']:%Y-%m-%d %H:%M}  "
          f"{cme['speed_kms']} km/s  Kp {cme['kp']}  glancing {cme['glancing']}")
else:
    print("  08_cme_inbound          -> no historical CME found to render")

# 9. The disc, both ways. The photographic path is what ships; the drawn one is
#    reached only when SDO cannot be fetched, which is exactly the state nobody
#    looks at until it happens.
save("09_disc_photo", display.render_solar({}, LAT, LON, now=now))
real_sun = display.sun_image
display.sun_image = lambda: (None, None)
save("10_disc_drawn_fallback", display.render_solar({}, LAT, LON, now=now))
display.sun_image = real_sun
photo, observed = display.sun_image()
print(f"     SDO frame: {'fetched' if photo is not None else 'UNAVAILABLE'}"
      + (f", observed {observed:%Y-%m-%d %H:%M %Z}, "
         f"{(datetime.now(timezone.utc) - observed).total_seconds() / 3600:.1f} h old"
         if photo is not None else ""))

# ⇒ EVERY STRING THE PAGE DRAWS, NOT A LIST WRITTEN BY HAND. The first pass
# measured the band lines and the rows and passed, while the line that actually
# ran off the edge - the sentence under the verdict - was not in the list,
# because a hand-kept list omits exactly the line nobody thought about. This
# intercepts draw.text instead, so the check cannot disagree with the render.
DRAWN = []


class Recorder(ImageDraw.ImageDraw):
    def text(self, xy, text, *a, **kw):
        DRAWN.append((xy, text, kw.get("font")))
        return super().text(xy, text, *a, **kw)


real_draw = ImageDraw.Draw
ImageDraw.Draw = lambda im, mode=None: Recorder(im, mode)
for label, when in (("ordinary day", now),
                    ("eclipse band", eclipse["begins"] - timedelta(hours=3)),
                    ("eclipse running", eclipse["maximum"])):
    DRAWN.clear()
    display.render_solar({}, LAT, LON, now=when)
    widths(f"{label} - every drawn string", [(t, fnt) for _, t, fnt in DRAWN])
ImageDraw.Draw = real_draw

print("\n" + "=" * 72)
if OVERFLOWS:
    print(f"{len(OVERFLOWS)} STRINGS OVERFLOW:")
    for label, text, w in OVERFLOWS:
        print(f"  {label}: {w}px  {text!r}")
    sys.exit(1)
print("No string overflows the text column.")
