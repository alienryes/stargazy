"""Verification for core.targets.rank_objects.

The defect this guards against is invisible in a render and invisible in the
data at a glance: UpTonight writes 0.0, not null, for a target with no
catalogued magnitude, so a float conversion reads "no magnitude" as "magnitude
zero" and sorts it ahead of everything real. It ran that way for weeks - the
page looked plausible throughout, because the objects it promoted are genuine
targets, just not the ones a person would pick first.

Synthetic records rather than a captured report, deliberately. A fixture makes
the checks depend on a file that may not be present, and a check that skips
reads exactly like a check that passed. These run everywhere, every time.

    python tools/check_ranking.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.targets import rank_objects  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<52} {detail}")
    if not ok:
        fails.append(name)


def ids(objects):
    return [o["id"] for o in rank_objects(objects)]


# --- The defect itself. Equal foto, one object with a real magnitude and one
# --- with UpTonight's 0.0 placeholder: the real one must come first.
pair = [{"id": "Sh2-155", "foto": 1.0, "mag": 0.0},
        {"id": "M 31", "foto": 1.0, "mag": 3.4}]
check("an absent magnitude does not outrank a real one", ids(pair) == ["M 31", "Sh2-155"],
      " -> ".join(ids(pair)))

# --- ...and it must hold whichever way round the input arrives, or the check is
# --- only testing that sorted() is stable.
check("...whichever order the records arrive in",
      ids(pair[::-1]) == ["M 31", "Sh2-155"], " -> ".join(ids(pair[::-1])))

# --- Real magnitudes still rank brightest first among themselves.
mags = [{"id": "faint", "foto": 1.0, "mag": 9.5},
        {"id": "mid", "foto": 1.0, "mag": 6.4},
        {"id": "bright", "foto": 1.0, "mag": 3.4}]
check("real magnitudes rank brightest first",
      ids(mags) == ["bright", "mid", "faint"], " -> ".join(ids(mags)))

# --- foto still leads. A dimmer object up all night beats a brighter one that
# --- is barely up, which is the ordering the page is built around.
foto = [{"id": "brief", "foto": 0.2, "mag": 3.0},
        {"id": "all night", "foto": 1.0, "mag": 9.0}]
check("foto outranks magnitude", ids(foto) == ["all night", "brief"],
      " -> ".join(ids(foto)))

# --- Unknowns keep their place relative to each other rather than being
# --- reordered arbitrarily, so the page does not reshuffle between refreshes.
unknown = [{"id": "first", "foto": 1.0, "mag": 0.0},
           {"id": "second", "foto": 1.0, "mag": 0.0}]
check("unknowns hold their input order", ids(unknown) == ["first", "second"],
      " -> ".join(ids(unknown)))

# --- Missing and malformed fields must not raise. UpTonight has changed its
# --- column set before, and a crash here takes the whole page down.
odd = [{"id": "no fields"},
       {"id": "junk", "foto": "n/a", "mag": "n/a"},
       {"id": "null mag", "foto": 1.0, "mag": None},
       {"id": "good", "foto": 1.0, "mag": 5.0}]
try:
    order = ids(odd)
    check("absent and malformed fields are tolerated", order[0] == "good",
          " -> ".join(order))
except Exception as e:  # noqa: BLE001 - the point is that nothing escapes
    check("absent and malformed fields are tolerated", False, repr(e))

check("empty input returns empty", rank_objects([]) == [] and rank_objects(None) == [])

print("\n  " + ("ALL CHECKS PASSED" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
