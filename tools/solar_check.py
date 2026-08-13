#!/usr/bin/env python3
"""Controls for core.solar, run on the Pi against the live feeds.

Every aggregate prints its sample size and every filter prints what it rejected,
because an assertion that never ran looks exactly like one that passed. Where a
rejection class cannot be populated from live data that is stated rather than
glossed - see the contamination gate, which is empty by nature and not by luck.

    PYTHONPATH=/home/operations/stargazy python3 tools/solar_check.py
"""
import sys
from datetime import datetime, timedelta, timezone

import ephem

from core import solar

FAIL = []
LAT, LON, ELEV = 51.44108266071185, -2.0060965418815617, 80


def check(name, condition, detail=""):
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not condition:
        FAIL.append(name)


def head(t):
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)


head("1. flare_class boundaries")
for flux, expect in ((1e-4, "X"), (5.4e-5, "M"), (1e-6, "C"), (9.9e-7, "B"),
                     (1e-8, "A"), (0, None), (None, None)):
    got = solar.flare_class(flux)
    check(f"{flux} -> {expect}", (got or " ")[0] == (expect or " "), f"got {got}")

head("2. obscuration against magnitude - the two must not agree")
# A ring of cases with the Moon's disc taken as the Sun's, so magnitude is
# analytic: at separation r, magnitude is exactly 0.5.
r = 0.26
check("no overlap is zero", solar.obscuration(0.6, r, r) == 0.0)
check("total covers everything", solar.obscuration(0.0, r, r * 1.05) == 1.0)
half = solar.obscuration(r, r, r)
check("half-diameter covers LESS than half the area", 0.3 < half < 0.42,
      f"magnitude 0.500 -> obscuration {half:.3f}")

head("3. Eclipse - positive control, 2026-08-12 (recorded 0.938 at 18:14 UT, alt 11.8)")
obs = solar._observer(LAT, LON, ELEV)
hit = solar._scan_day(obs, ephem.Date("2026/08/12"), 1)
check("an eclipse is found", hit is not None)
if hit:
    print(f"        magnitude {hit['magnitude']:.3f}  obscuration "
          f"{hit['obscuration']:.3f}  at {ephem.Date(hit['when'])} UT  "
          f"sun alt {hit['sun_altitude']:.1f}")
    check("magnitude within 0.01 of the record", abs(hit["magnitude"] - 0.938) < 0.01)
    check("sun altitude within 0.5 of the record", abs(hit["sun_altitude"] - 11.8) < 0.5)
    check("obscuration is NOT the magnitude",
          abs(hit["magnitude"] - hit["obscuration"]) > 0.005,
          f"differ by {hit['magnitude'] - hit['obscuration']:.3f}")

head("4. Eclipse - the empty case, which is what caught the radius bug")
for day in ("2026/08/13", "2026/08/20", "2026/07/12", "2026/06/15"):
    check(f"no eclipse on {day}", solar._scan_day(obs, ephem.Date(day), 2) is None)
# The specific false positive: at a new moon with no eclipse the discs must be
# far apart. A radius error inflates them and this is the case it breaks.
nm = ephem.next_new_moon(ephem.Date("2026/08/20"))
sep, r_sun, r_moon, _ = solar._discs(obs, nm)
check("new moon separation exceeds the summed radii", sep > r_sun + r_moon,
      f"sep {sep:.2f} deg vs {r_sun + r_moon:.3f} deg")
check("solar radius is about 16 arcmin", 15.0 < r_sun * 60 < 16.5,
      f"{r_sun * 60:.2f}'")
check("lunar radius is about 16 arcmin", 14.5 < r_moon * 60 < 17.0,
      f"{r_moon * 60:.2f}'")

head("5. Eclipse - the horizon gate rejects something")
# 2028-01-26 reaches maximum 0.4 deg BELOW the horizon here, so the gate has a
# case to act on: without it the page would quote a maximum nobody can see.
ungated = None
day = ephem.Date("2028/01/26")
best_any = None
for i in range(0, 24 * 60, 2):
    when = ephem.Date(day + i * ephem.minute)
    s, rs, rm, alt = solar._discs(obs, when)
    if s >= rs + rm:
        continue
    mag = (rs + rm - s) / (2.0 * rs)
    if best_any is None or mag > best_any[0]:
        best_any = (mag, alt)
gated = solar._scan_day(obs, day, 2)
check("an eclipse exists on 2028-01-26 ignoring the horizon", best_any is not None,
      f"magnitude {best_any[0]:.3f} at sun alt {best_any[1]:+.1f}" if best_any else "")
if best_any and gated:
    check("the gated maximum is shallower than the ungated one",
          gated["magnitude"] < best_any[0],
          f"{gated['magnitude']:.3f} visible vs {best_any[0]:.3f} overall")
    check("the gated maximum is above the horizon", gated["sun_altitude"] > 0,
          f"alt {gated['sun_altitude']:+.1f}")
elif best_any and not gated:
    check("gate correctly reports nothing visible from here", True,
          f"deepest phase sits at alt {best_any[1]:+.1f}")

head("6. Eclipse - the forward search and its cache")
solar.ECLIPSE_CACHE.unlink(missing_ok=True)
t0 = datetime.now()
event = solar.next_eclipse(LAT, LON, ELEV)
cold = (datetime.now() - t0).total_seconds()
check("the next visible eclipse is found", event is not None, f"cold search {cold:.1f}s")
if event:
    print(f"        {event['maximum']:%Y-%m-%d %H:%M %Z}  magnitude "
          f"{event['magnitude']:.3f}  obscuration {event['obscuration']:.3f}  "
          f"sun alt {event['sun_altitude']:.1f}")
    print(f"        begins {event['begins']:%H:%M}  ends {event['ends']:%H:%M}")
    check("it is in the future", event["maximum"] > datetime.now().astimezone())
    check("begins before maximum", event["begins"] < event["maximum"])
    check("ends after maximum", event["ends"] > event["maximum"])
t0 = datetime.now()
again = solar.next_eclipse(LAT, LON, ELEV)
warm = (datetime.now() - t0).total_seconds()
check("the cache is used on the second call", warm < cold / 10,
      f"{warm:.3f}s against {cold:.1f}s cold")
check("and returns the same event",
      (again or {}).get("maximum") == (event or {}).get("maximum"))

# A different site must not read the cached answer.
t0 = datetime.now()
other = solar.next_eclipse(64.13, -21.90, 0.0)          # Reykjavik
recomputed = (datetime.now() - t0).total_seconds() > warm * 10
check("a different site recomputes rather than reusing the cache", recomputed)
if other:
    print(f"        Reykjavik: {other['maximum']:%Y-%m-%d %H:%M}  "
          f"magnitude {other['magnitude']:.3f}")
check("and gets a different answer from this site",
      (other or {}).get("maximum") != (event or {}).get("maximum"))
solar.ECLIPSE_CACHE.unlink(missing_ok=True)

head("7. Live feeds - each filter reports what it rejected")
regions = solar.fetch_regions()
check("regions fetched", regions is not None)
if regions:
    print(f"        {regions['date']}: {regions['regions']} regions, "
          f"{regions['spots']} spots, area {regions['area']}, largest "
          f"{regions['largest']}")
    print(f"        flare odds C {regions['c_probability']}%  "
          f"M {regions['m_probability']}%  X {regions['x_probability']}%")
    # The rejection this gate exists for, counted rather than assumed.
    rows = solar._get(solar.REGIONS_URL)
    newest = max(r["observed_date"] for r in rows)
    stale = sum(1 for r in rows if r["observed_date"] != newest)
    check("the stale-row filter rejected something", stale > 0,
          f"{stale} of {len(rows)} rows discarded as older than {newest}")
    check("rows are NOT sorted, so neither end is safe",
          [r["observed_date"] for r in rows] != sorted(r["observed_date"] for r in rows))

xray = solar.fetch_xray()
check("x-rays fetched", xray is not None)
if xray:
    print(f"        peak {xray['peak_class']} at {xray['peak_time']}  |  "
          f"latest {xray['latest_class']} at {xray['latest_time']}")
    rows = solar._get(solar.XRAY_URL)
    long_band = [r for r in rows if r.get("energy") == solar.LONG_BAND]
    contaminated = [r for r in long_band if r.get("electron_contaminaton")]
    short_flagged = [r for r in rows
                     if r.get("energy") != solar.LONG_BAND
                     and r.get("electron_contaminaton")]
    check("the band filter rejected something", len(rows) - len(long_band) > 0,
          f"{len(rows) - len(long_band)} of {len(rows)} rows are the short band")
    print(f"  [NOTE] the contamination gate rejected {len(contaminated)} long-band "
          f"rows and CANNOT be populated here:")
    print(f"         {len(short_flagged)} short-band rows carry the flag, 0 long-band "
          f"rows do. The band filter above is what protects the reading.")

f107 = solar.fetch_f107()
check("F10.7 fetched", f107 is not None, f"flux {f107}")

head("8. CME - the arrival lives on CME.cmeAnalyses, not on CMEAnalysis")
cme = solar.fetch_cme()
if cme:
    print(f"        arrival {cme['arrival']:%Y-%m-%d %H:%M %Z}  "
          f"speed {cme['speed_kms']} km/s  Kp {cme['kp']}  "
          f"glancing {cme['glancing']}  from {cme['source']}")
    check("the arrival is in the future", cme["arrival"] > datetime.now(timezone.utc))
    check("it is inside the lookahead",
          cme["arrival"] <= datetime.now(timezone.utc)
          + timedelta(days=solar.CME_LOOKAHEAD_DAYS))
else:
    print("        no CME arriving in the next "
          f"{solar.CME_LOOKAHEAD_DAYS} days - the empty case, which is the "
          "normal one")
# Prove the parser works even when the live window is empty, by running it over
# a window known to contain arrivals. An empty result is not evidence.
past = solar.fetch_cme(now=datetime(2026, 7, 1, tzinfo=timezone.utc))
check("the parser finds a known past arrival when pointed at one",
      past is not None,
      f"{past['arrival']:%Y-%m-%d %H:%M} at {past['speed_kms']} km/s, Kp {past['kp']}"
      if past else "nothing found in the 2026-07-01 window")

head("9. activity() and its cache")
solar.ACTIVITY_CACHE.unlink(missing_ok=True)
data = solar.activity()
check("activity returns something", data is not None)
if data:
    print(f"        keys: {sorted(data.keys())}")
    check("at least three of the four feeds answered",
          sum(1 for k in ("regions", "xray", "f107", "cme") if data.get(k)) >= 3,
          f"{[k for k in ('regions', 'xray', 'f107', 'cme') if data.get(k)]} present")
check("the cache file was written", solar.ACTIVITY_CACHE.exists())

head("10b. A zero flare probability is not always a forecast of calm")
rows = solar._get(solar.REGIONS_URL)
by_date = {}
for r in rows:
    by_date.setdefault(r["observed_date"], []).append(r)
issued, pending = [], []
for d, day in sorted(by_date.items(), reverse=True):
    probs = [x.get("c_flare_probability") for x in day]
    classes = [x.get("spot_class") for x in day]
    (issued if any(p for p in probs) else pending).append((d, len(day), probs, classes))
print(f"  {len(by_date)} report dates in the file")
print(f"  forecast ISSUED on {len(issued)}, PENDING on {len(pending)}")
for d, n, probs, classes in pending:
    print(f"    pending: {d}  {n} regions  C {probs}")
    print(f"             spot_class {classes}   <- note some ARE classified")
for d, n, probs, _ in issued[:3]:
    print(f"    issued : {d}  {n} regions  C {probs}")

# The discriminator has to separate two populated classes, or it is untested.
check("both states are present in the sample",
      issued and pending, f"{len(issued)} issued / {len(pending)} pending")
check("every ISSUED day carries a non-zero probability",
      all(any(p for p in probs) for _, _, probs, _ in issued))

# ⇒ WHY THE MARKER IS THE PROBABILITY AND NOT spot_class. The first attempt used
# spot_class and the feed disproved it within the hour: regions get classified
# before the probabilities are attached, so a partly-filled report reads as
# issued. This asserts that state exists rather than describing it.
partly = [(d, sum(1 for c in classes if c), n)
          for d, n, probs, classes in pending if any(classes)]
check("a PENDING day can already carry spot classes - so spot_class is the "
      "wrong marker", bool(partly),
      f"{partly}" if partly else "no partly-classified pending day right now")

# The decisive case: one region, one classification, two very different
# probabilities on consecutive days. A real forecast does not do that.
dates = sorted(by_date, reverse=True)
if len(dates) > 1:
    a = {r["region"]: r for r in by_date[dates[0]]}
    b = {r["region"]: r for r in by_date[dates[1]]}
    for reg in sorted(set(a) & set(b)):
        if a[reg].get("spot_class") and a[reg]["spot_class"] == b[reg].get("spot_class"):
            print(f"    region {reg} is {a[reg]['spot_class']} on both days: "
                  f"C {b[reg]['c_flare_probability']}% -> "
                  f"{a[reg]['c_flare_probability']}%")

regions = solar.fetch_regions()
if regions:
    check("fetch_regions reports which state today is in",
          "forecast_issued" in regions,
          f"forecast_issued={regions.get('forecast_issued')} for {regions['date']}")

head("11. Heliographic position - location strings and the disc projection")
for text, expect in (("S17W54", (-17.0, -54.0)), ("N14E102", (14.0, 102.0)),
                     ("N00W00", (0.0, 0.0)), ("", (None, None)),
                     ("nonsense", (None, None)), (None, (None, None))):
    got = solar._location(text)
    check(f"{text!r} -> {expect}", got == expect, f"got {got}")

# B0 runs from -7.25 in early March to +7.25 in early September and passes zero
# in early June and December. Checked against those extremes rather than another
# implementation, because agreeing with a second copy of the same mistake proves
# nothing.
print()
b0s = {}
for label, day in (("early Mar", "2027/03/06"), ("early Jun", "2027/06/06"),
                   ("early Sep", "2027/09/07"), ("early Dec", "2027/12/07")):
    b0s[label] = solar.solar_b0(ephem.Date(day))
    print(f"        B0 {label} {day}: {b0s[label]:+.2f} deg")
check("B0 is near its minimum in early March", b0s["early Mar"] < -6.5)
check("B0 is near its maximum in early September", b0s["early Sep"] > 6.5)
check("B0 passes zero in early June", abs(b0s["early Jun"]) < 1.0)
check("B0 passes zero in early December", abs(b0s["early Dec"]) < 1.0)
check("B0 never exceeds the axial tilt",
      all(abs(v) <= 7.25 for v in b0s.values()))

print()
x, y, front = solar.project_spot(0.0, 0.0, 0.0)
check("disc centre projects to the origin", abs(x) < 1e-9 and abs(y) < 1e-9)
check("and is on the near side", front)
# Orientation, which is a convention and therefore the easy thing to mirror.
x, _, _ = solar.project_spot(0.0, -90.0, 0.0)
check("solar WEST (W90) is on the RIGHT", abs(x - 1.0) < 1e-9, f"x={x:+.3f}")
x, _, _ = solar.project_spot(0.0, 90.0, 0.0)
check("solar EAST (E90) is on the LEFT", abs(x + 1.0) < 1e-9, f"x={x:+.3f}")
# Rotation carries a group from the east limb to the west, so its x must
# INCREASE as its east-longitude falls. A mirrored disc passes both limb checks
# only if it also fails this one, which is why the drift is checked too.
xs = [solar.project_spot(10.0, lo, 0.0)[0] for lo in (60, 30, 0, -30, -60)]
check("a group drifts left to right as the Sun turns",
      all(b > a for a, b in zip(xs, xs[1:])),
      "  ".join(f"{v:+.2f}" for v in xs))
_, _, front = solar.project_spot(0.0, 150.0, 0.0)
check("a group 150 degrees round is on the FAR side", not front)
_, y, _ = solar.project_spot(30.0, 0.0, 0.0)
check("northern latitude projects UPWARD (negative y)", y < 0, f"y={y:.3f}")
_, y_flat, _ = solar.project_spot(0.0, 0.0, 0.0)
_, y_tilt, _ = solar.project_spot(0.0, 0.0, 7.25)
check("a positive B0 pushes the equator BELOW centre", y_tilt > y_flat,
      f"{y_flat:.3f} -> {y_tilt:.3f}")
check("every point stays inside the unit disc",
      all(solar.project_spot(la, lo, 7.0)[0] ** 2
          + solar.project_spot(la, lo, 7.0)[1] ** 2 <= 1.0 + 1e-9
          for la in range(-80, 81, 10) for lo in range(-180, 181, 10)))

# The live groups, and how many of them the far-side gate removes.
regions = solar.fetch_regions()
if regions and regions.get("groups"):
    groups = regions["groups"]
    b0 = solar.solar_b0()
    placed = [g for g in groups if g["latitude"] is not None]
    visible = [g for g in placed
               if solar.project_spot(g["latitude"], g["longitude"], b0)[2]]
    print(f"\n        B0 today {b0:+.2f} deg; {len(groups)} groups, "
          f"{len(placed)} with a position, {len(visible)} on the near side")
    for g in placed:
        px, py, front = solar.project_spot(g["latitude"], g["longitude"], b0)
        print(f"          {g['region']}  {g['spot_class'] or '--':5} "
              f"lat {g['latitude']:+5.1f} lon {g['longitude']:+6.1f}  "
              f"-> ({px:+.2f}, {py:+.2f})  {'near' if front else 'FAR SIDE'}")
    check("every group carries a parsed position", len(placed) == len(groups),
          f"{len(groups) - len(placed)} without one")

head("10. sun_up - both states, at instants chosen to give one each")
noon = ephem.Date("2026/08/13 12:00:00")
midnight = ephem.Date("2026/08/13 01:00:00")
check("up at midday", solar.sun_up(LAT, LON, ELEV, now=noon))
check("down at 01:00", not solar.sun_up(LAT, LON, ELEV, now=midnight))
# The gate must also separate the two hemispheres' seasons, not just the clock.
check("down at midday at the winter pole",
      not solar.sun_up(89.0, 0.0, 0.0, now=ephem.Date("2026/12/21 12:00:00")))

print("\n" + "=" * 72)
print(f"{len(FAIL)} failed" if FAIL else "ALL PASSED")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
