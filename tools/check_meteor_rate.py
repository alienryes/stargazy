"""Verification for the meteors page's printed rate - build10 rate_text.

The defect this guards against is one the page cannot show you is wrong, because
every figure on it is individually true. On 2026-08-21 a named Perseid row read
~0/hr four lines above a sporadic background of ~1/hr: a shower the page had
chosen to name, reporting that nothing was falling, above a rate it was actually
at 37% of. Neither number was incorrect and the pair was, because at that end of
the range a whole number has two values and one of them is zero.

Zero is a legitimate reading - a radiant below the horizon delivers none - so
the invariant is not "never print zero". It is that a shower NAMED by the page,
with its radiant up, never prints one.

The formatter and the floor are imported rather than restated: a check carrying
its own copy of a rule tests the copy. The site coordinates are read from the
config the panel actually runs on, for the same reason; the tracked example
config stands in where that file is absent, so the checks run on a fresh
clone rather than failing to start. The heading line names which was used.

    python tools/check_meteor_rate.py
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.meteors import (  # noqa: E402
    NAMED_SHOWER_FLOOR,
    RATE_BOUND_BELOW,
    RATE_DECIMAL_BELOW,
    SPORADIC_ZHR,
    active,
    rate_text,
    visible_rate,
)
from core.positions import alt_az, observer  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<58} {detail}")
    if not ok:
        fails.append(name)


cfg = ROOT / "build10" / "config.toml"
if not cfg.exists():
    cfg = ROOT / "build10" / "config.example.toml"
with open(cfg, "rb") as fh:
    site = tomllib.load(fh)["location"]
LAT, LON = site["latitude"], site["longitude"]
print(f"site {LAT:.4f}, {LON:.4f} ({cfg.name})   "
      f"decimal below {RATE_DECIMAL_BELOW}/hr, "
      f"bound below {RATE_BOUND_BELOW}/hr\n")

# --- The formatter itself, at the boundaries. Run against the values the old
# --- whole-number format got wrong, so the check can distinguish the fixed code
# --- from the broken code rather than passing on both.
for rate, want in ((0.0, "~0/hr"), (0.04, "<0.1/hr"), (0.42, "~0.4/hr"),
                   (0.96, "~1.0/hr"), (1.0, "~1/hr"), (5.66, "~6/hr")):
    check(f"{rate} prints {want}", rate_text(rate) == want, rate_text(rate))
check("a positive rate never prints as nothing",
      all(rate_text(r / 1000) != "~0/hr" for r in range(1, 1000)), "n=999")


def named_rows(when, cloud=0.0, moon=0.0):
    """(name, radiant alt, printed rate) for the showers the page would name."""
    obs = observer(LAT, LON, when=when)
    out = []
    for s in active(when):
        if s["zhr"] * s["strength"] < NAMED_SHOWER_FLOOR:
            continue
        alt, _az = alt_az(obs, s["ra"], s["dec"])
        out.append((s["name"], alt,
                    rate_text(visible_rate(s["zhr"], s["strength"], alt, cloud, moon))))
    return out


# --- The reported night, under conditions that reproduce the sporadic ~1/hr it
# --- was seen at. This is the known-bad input: under the old format the Perseid
# --- row printed ~0/hr here, so an assertion that passes on both formats would
# --- be no evidence at all.
night = datetime(2026, 8, 22, 0, 0)
CLOUD, MOON = 80.0, 0.0
rows = named_rows(night, CLOUD, MOON)
spor = visible_rate(SPORADIC_ZHR, 1.0, 45.0, CLOUD, MOON)
perseids = [r for r in rows if r[0] == "Perseids"]
check("the reported night still names the Perseids", len(perseids) == 1, f"n={len(rows)}")
if perseids:
    _name, alt, text = perseids[0]
    check("the Perseid row no longer reads as nothing", text != "~0/hr",
          f"{text} vs sporadic {rate_text(spor)}, radiant {alt:.1f}° up")

# --- The invariant across the year, at the same hour each night so radiant
# --- altitudes are sampled consistently. Cloud is set high deliberately: it is
# --- what pushes rates into the range where the old format collapsed, and a
# --- clear-sky sample would never exercise the branch being checked.
nights = [datetime(2026, 1, 1, 0, 0) + timedelta(days=d) for d in range(365)]
sampled = [(n, r) for n in nights for r in named_rows(n, CLOUD, MOON)]
up = [(n, r) for n, r in sampled if r[1] > 0]
zeros = [(n, r) for n, r in up if r[2] == "~0/hr"]
check("the year was actually sampled", len(sampled) > 0, f"n={len(sampled)} rows")
check("the sample contains rows with the radiant up", len(up) > 0, f"n={len(up)} rows")
check("no named shower with its radiant up prints nothing", not zeros,
      f"n={len(zeros)}" + (f"  first {zeros[0][0].date()} {zeros[0][1][0]}" if zeros else ""))

# --- The other half: a radiant below the horizon must still read ~0/hr, or the
# --- fix has traded one untruth for another.
down = [(n, r) for n, r in sampled if r[1] <= 0]
check("the sample contains rows with the radiant down", len(down) > 0, f"n={len(down)} rows")
check("a radiant below the horizon still prints ~0/hr",
      all(r[2] == "~0/hr" for _n, r in down), f"n={len(down)}")

# --- How much of the page's range the decimal actually covers. Not an
# --- assertion: it is the figure that says whether the threshold is in the
# --- right place, and it belongs beside the checks rather than in a note.
decimals = sum(1 for _n, r in up if r[2].startswith("~0.") or r[2].startswith("<"))
print(f"\n  rows below 1/hr   {decimals}/{len(up)} = {decimals / len(up):.0%} "
      f"at {CLOUD:.0f}% cloud")

print()
if fails:
    print(f"FAILED: {len(fails)}")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("All checks passed.")
