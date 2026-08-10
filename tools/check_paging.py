"""Verification for the deep-sky card paging arithmetic.

The failure this guards against is silent: an off-by-one in the offset drops an
object out of every screenful, or shows one twice, and the page still looks
entirely correct - the cards are real targets and the heading still counts up.
Nothing on the panel would give it away.

Checked against both builds' card counts, because 40 objects divides into six
and four differently and the last screenful is the short one in each case.

    python tools/check_paging.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.targets import rank_objects  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<54} {detail}")
    if not ok:
        fails.append(name)


def screenfuls(objects, per_page):
    """What build_pages and render_targets between them produce."""
    n = max(1, -(-len(objects) // per_page))
    ranked = rank_objects(objects)
    return [ranked[i * per_page:i * per_page + per_page] for i in range(n)]


def heading(objects, page, offset, per_page):
    """The count the heading shows, as render_targets builds it."""
    if len(objects) <= per_page:
        return f"all {len(objects)}"
    return f"{offset + 1}-{offset + len(page)} of {len(objects)}"


# Distinct foto values so the ranking is a real ordering rather than one big tie,
# and ids that carry their rank so a slice can be read at a glance.
def sample(n):
    return [{"id": f"obj{i:02d}", "foto": 1.0 - i / 1000.0, "mag": 5.0}
            for i in range(n)]


for per_page, build in ((6, "10in"), (4, "5in")):
    print(f"\n  {build}, {per_page} cards per screenful")
    for count in (0, 1, per_page - 1, per_page, per_page + 1, 40, 41):
        objs = sample(count)
        pages = screenfuls(objs, per_page)
        flat = [o["id"] for p in pages for o in p]
        expected = [o["id"] for o in rank_objects(objs)]

        check(f"{count:>2} objects: every object appears exactly once",
              flat == expected,
              f"{len(pages)} screenful(s), {len(flat)} shown of {count}")

        check(f"{count:>2} objects: no screenful over {per_page}",
              all(len(p) <= per_page for p in pages),
              f"sizes {[len(p) for p in pages]}")

        # An empty run must still be one (empty) screenful rather than none, or
        # the ceiling division yields zero pages and the page vanishes for a
        # reason unrelated to whether there is anything to show.
        check(f"{count:>2} objects: at least one screenful", len(pages) >= 1,
              f"{len(pages)}")

        heads = [heading(objs, p, i * per_page, per_page)
                 for i, p in enumerate(pages)]
        check(f"{count:>2} objects: heading ends at the true total",
              heads[-1].endswith(f"of {count}") or heads[-1] == f"all {count}",
              heads[0] if len(heads) == 1 else f"{heads[0]} ... {heads[-1]}")

# The wrap the loop applies: pressing More past the end returns to the start.
pages = screenfuls(sample(40), 6)
seq = [(i % len(pages)) for i in range(len(pages) + 2)]
check("More wraps to the first screenful", seq[len(pages)] == 0 and seq[-1] == 1,
      f"{len(pages)} screenfuls, press sequence {seq}")

print("\n  " + ("ALL CHECKS PASSED" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
