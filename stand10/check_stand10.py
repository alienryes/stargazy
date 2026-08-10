"""Verification for stand10.stl. Run after every build.

The checks that matter here are not "is the mesh valid" - they are the ones
that would otherwise only fail on the panel:

  - the screw axes are CLEAR. A fastener needs the ABSENCE of material, and
    asking whether the pad is present at the screw position answers a
    different question - one that returns True when the hole is missing.
  - the step is real and lands the right way round: the front face touches the
    plate BOTH sides of the bolt line, with the pad band recessed between them
    onto the boss plane. Getting this backwards looks identical in a render,
    and bearing on only one side is what made v0.3.x rock on the desk.
  - nothing reaches into the panel, and nothing reaches up into the Pi.
"""

import math
import sys
from pathlib import Path

import numpy as np
import trimesh

import stand10 as S

# Resolved against this file, not the working directory, so the suite reads the
# STL it is paired with wherever it is run from.
STL = Path(__file__).with_name("stand10.stl")

A = math.radians(S.tilt)
TOL = 0.01

fails = []
notes = []


def check(name, ok, detail=""):
    notes.append(f"  {'PASS' if ok else 'FAIL'}  {name:<44} {detail}")
    if not ok:
        fails.append(name)


def to_panel(pts):
    """Desk (X, Y, Z) -> panel (X, s, t)."""
    y, z = pts[:, 1], pts[:, 2] - S.clear_z
    return np.column_stack([pts[:, 0],
                            y * math.sin(A) + z * math.cos(A),
                            y * math.cos(A) - z * math.sin(A)])


def to_desk(x, s, t):
    """Panel (X, s, t) -> desk (X, Y, Z)."""
    return np.column_stack([
        x,
        s * math.sin(A) + t * math.cos(A),
        S.clear_z + s * math.cos(A) - t * math.sin(A),
    ])


mesh = trimesh.load(STL)

# --- Mesh sanity. split() is the one that catches a detached feature, which
# --- leaves the mesh watertight because each body is closed in itself.
check("watertight", mesh.is_watertight)
bodies = len(mesh.split(only_watertight=False))
check("single body", bodies == 1, f"{bodies} bodies")

# --- Bed fit, against the printer's 250 x 220 x 270 envelope.
ext = mesh.extents
check("fits the bed", ext[0] <= 250 and ext[1] <= 220 and ext[2] <= 270,
      f"{ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f}")

# --- The screw axes must be clear through the pad, and there must be material
# --- beside them. n = 26 samples per hole; the sample count is printed so an
# --- empty check cannot pass silently.
axis_pts, flank_pts = [], []
for sx in (-1, 1):
    x = sx * S.BOSS_DX / 2.0
    for t in np.linspace(S.BOSS_PROUD - 1.0, S._BACK_T + 1.0, 26):
        axis_pts.append((x, S.BOSS_S, t))
    for dx, ds in ((3.5, 0), (-3.5, 0), (0, 3.5), (0, -3.5)):
        flank_pts.append((x + dx, S.BOSS_S + ds, (S.BOSS_PROUD + S._BACK_T) / 2.0))

axis = to_desk(*np.array(axis_pts).T)
inside_axis = mesh.contains(axis)
check("screw axes clear", not inside_axis.any(),
      f"n={len(axis)}, {int(inside_axis.sum())} obstructed")

flank = to_desk(*np.array(flank_pts).T)
inside_flank = mesh.contains(flank)
check("material beside each hole", inside_flank.all(),
      f"n={len(flank)}, {int((~inside_flank).sum())} missing")

# --- The step. Below the bolt line the front face sits on the boss plane, so
# --- a point just off the plate must be OUTSIDE the part; above it the bearing
# --- face touches the plate, so the same point must be INSIDE.
bear_xs = [-S.BOSS_DX / 2.0, 0.0, S.BOSS_DX / 2.0]

# The front face touches BOTH SIDES of the bolt line - that is what stops the
# assembly pivoting on the screw axis, which is a defect the panel showed and
# no render would have. Sampled on the columns and the centre rib, where the
# windows leave material.
lo_probe = to_desk(*np.array(
    [(x, s, 0.5) for x in bear_xs for s in (6.0, 20.0, S.lo_bear_s1 - 2)]).T)
lo_solid = mesh.contains(lo_probe)
check("bearing face below the bolt line", lo_solid.all(),
      f"n={len(lo_probe)}, {int((~lo_solid).sum())} missing")

# ...and the pad band between them is held off the plate, so the bosses have
# somewhere to sit. This is the one place the face must NOT touch.
pad_probe = to_desk(*np.array(
    [(x, s, 0.5) for x in np.linspace(-S.col_in + 2, S.col_in - 2, 9)
     for s in (S.pad_s0 + 1, S.BOSS_S, S.pad_s1 - 1)]).T)
pad_clear = ~mesh.contains(pad_probe)
check("pad band held off the plate", pad_clear.all(),
      f"n={len(pad_probe)}, {int((~pad_clear).sum())} touching")

# Sampled on the columns and the centre rib, where the bearing face survives
# the windows - the windows deliberately remove it in between.
bear_probe = to_desk(*np.array(
    [(x, s, 0.5) for x in bear_xs for s in (S.bear_s0 + 2, 75.0, S.bear_s1 - 2)]).T)
bear_solid = mesh.contains(bear_probe)
check("bearing face above the bolt line", bear_solid.all(),
      f"n={len(bear_probe)}, {int((~bear_solid).sum())} missing")

# --- The two faces really are 3 mm apart, measured off the mesh rather than
# --- assumed from the parameters that drew it.
pv = to_panel(mesh.vertices)
# Taken inside the pad band itself, not merely below the bolt line: the face is
# now on the plate either side of it, so a window that reached from the bottom
# would put a t=0 vertex in the sample and report no step at all.
front_pad = pv[(pv[:, 1] > S.pad_s0 + 1) & (pv[:, 1] < S.pad_s1 - 1)][:, 2].min()
front_bear = pv[(pv[:, 1] > S.bear_s0 + 1)][:, 2].min()
step = front_pad - front_bear
check("step is 3.0 mm", abs(step - S.BOSS_PROUD) < 0.05,
      f"pad t={front_pad:.3f}, bearing t={front_bear:.3f}, step {step:.3f}")

# --- Nothing may intrude into the panel, and nothing may reach the Pi.
check("nothing in front of the plate", pv[:, 2].min() > -TOL,
      f"min t {pv[:, 2].min():.3f}")
check(f"clears the Pi at s={S.PI_S0:.0f}", pv[:, 1].max() < S.PI_S0 - TOL,
      f"max s {pv[:, 1].max():.2f}, Pi at {S.PI_S0}")

# --- The cable collars. A bore is a hole, so the test is for the ABSENCE of
# --- material along it; asking whether the collar is present answers a
# --- different question, and that one passes when the bore was never cut. The
# --- mouth needs both halves of the same argument: open where the lead goes
# --- in, and closed the whole way round everywhere else.
bore_pts, wall_pts, mouth_pts = [], [], []
lip = S.clip_bore / 2.0 + S.clip_wall / 2.0
for s0, msign in zip(S.clip_s0, S.clip_mouth_sign):
    for s in np.linspace(s0 + 0.5, s0 + S.clip_h - 0.5, 12):
        bore_pts.append((S._CLIP_X, s, S._CLIP_T))
        # The wall opposite the mouth, then the lips over and under the bore.
        # Between them these say the ring closes everywhere the mouth is not.
        for dx, dt in ((-msign * 2.9, 0.6), (-msign * 3.8, 0.6),
                       (0.0, lip), (0.0, -lip)):
            wall_pts.append((S._CLIP_X + dx, s, S._CLIP_T + dt))
        # Straight out through the mouth, from the bore wall into clear air.
        for d in np.linspace(S.clip_bore / 2.0 + 0.2, S._CLIP_R + 2.0, 10):
            mouth_pts.append((S._CLIP_X + msign * d, s, S._CLIP_T + 0.6))

bore = to_desk(*np.array(bore_pts).T)
bore_blocked = mesh.contains(bore)
check("clip bores clear", not bore_blocked.any(),
      f"n={len(bore)}, {int(bore_blocked.sum())} obstructed")

wall = to_desk(*np.array(wall_pts).T)
wall_solid = mesh.contains(wall)
check("collar closed around each bore", wall_solid.all(),
      f"n={len(wall)}, {int((~wall_solid).sum())} missing")

mouth = to_desk(*np.array(mouth_pts).T)
mouth_open = ~mesh.contains(mouth)
check("mouths open outward", mouth_open.all(),
      f"n={len(mouth)}, {int((~mouth_open).sum())} blocked")

# --- Retention is the alternation, not a snap fit: the lead cannot leave
# --- without moving two ways at once. A run of collars all opening the same
# --- way would pass every check above and hold nothing.
alternates = all(a * b < 0 for a, b in zip(S.clip_mouth_sign, S.clip_mouth_sign[1:]))
check("mouths alternate", alternates,
      " ".join("-X" if m < 0 else "+X" for m in S.clip_mouth_sign))

# --- The mouth gap, measured off the mesh rather than read back from the
# --- parameter that drew it. Sampled at a radius where both cut faces exist:
# --- further out the collar has curved away and there is nothing to measure
# --- between, which would report the constriction as wide open.
STEP = 0.02
gaps = []
for s0, msign in zip(S.clip_s0, S.clip_mouth_sign):
    ts = np.arange(S._CLIP_T - 4.0, S._CLIP_T + 4.0, STEP)
    scan = to_desk(np.full(len(ts), S._CLIP_X + msign * 3.0),
                   np.full(len(ts), s0 + S.clip_h / 2.0), ts)
    free = ~mesh.contains(scan)
    mid = int(np.argmin(np.abs(ts - S._CLIP_T)))
    if not free[mid]:
        gaps.append(0.0)
        continue
    lo = hi = mid
    while lo > 0 and free[lo - 1]:
        lo -= 1
    while hi < len(ts) - 1 and free[hi + 1]:
        hi += 1
    gaps.append((hi - lo + 1) * STEP)

check("mouth gap is the drawn width", max(abs(g - S.clip_mouth) for g in gaps) < 0.15,
      f"n={len(gaps)}, " + ", ".join(f"{g:.2f}" for g in gaps)
      + f" vs {S.clip_mouth}")
check("mouth narrower than the lead", max(gaps) < S.CABLE_D,
      f"widest {max(gaps):.2f} vs a {S.CABLE_D} lead")

# --- The top collar is held clear of the upright's top so the lead's overmould
# --- has room to turn into it, and the middle one clears the bolt head. Both
# --- are stated as distances rather than as the positions that produce them,
# --- so moving a collar has to move the reason with it.
top_gap = S.bear_s1 - (S.clip_s0[-1] + S.clip_h)
check("top collar clear of the upright's top", abs(top_gap - S.clip_top_clear) < TOL,
      f"{top_gap:.1f} mm, wanted {S.clip_top_clear}")
above = to_desk(*np.array(
    [(S._CLIP_X, s, S._CLIP_T)
     for s in np.linspace(S.clip_s0[-1] + S.clip_h + 0.5, S.bear_s1, 12)]).T)
above_clear = ~mesh.contains(above)
check("nothing protrudes above the top collar", above_clear.all(),
      f"n={len(above)}, {int((~above_clear).sum())} obstructing")

# --- A driver has to reach both bolts, and the middle collar is now the
# --- nearest material to one of them.
DRIVER_D = 6.0
drv = []
for sx in (-1, 1):
    for t in np.linspace(S._BACK_T + 0.5, S._BACK_T + 30.0, 20):
        for a in range(8):
            th = 2.0 * math.pi * a / 8.0
            drv.append((sx * S.BOSS_DX / 2.0 + DRIVER_D / 2.0 * math.cos(th),
                        S.BOSS_S + DRIVER_D / 2.0 * math.sin(th), t))
driver = to_desk(*np.array(drv).T)
driver_blocked = mesh.contains(driver)
check(f"driver access, {DRIVER_D:.0f} mm shaft", not driver_blocked.any(),
      f"n={len(driver)}, {int(driver_blocked.sum())} obstructed")

# --- Tipping. The panel's centre of mass projects behind the front contact and
# --- ahead of the rear, and the backward pull it takes to lift the front is
# --- what the cable has to beat.
W = 5.47                                  # N, 558 g
com_s, com_z = S.PANEL_H / 2.0, S.PANEL_H / 2.0 * math.cos(A) + S.clear_z
com_y = com_s * math.sin(A)
rear = mesh.vertices[:, 1].max()
front = mesh.vertices[:, 1].min()
check("centre of mass inside the footprint", front < com_y < rear,
      f"CoM Y {com_y:.1f} in {front:.1f}..{rear:.1f}")
tip_force = W * (rear - com_y) / com_z
check("resists >0.75 N of backward pull", tip_force > 0.75,
      f"{tip_force:.2f} N at the panel's top")

# --- Overhangs. Anything facing downward at less than 45 degrees from
# --- horizontal needs support, which this part is meant not to need. The foot's
# --- underside is excluded: it faces straight down but rests on the bed, and
# --- counting it would swamp every real overhang with one that cannot exist.
# --- Every unsupported region is MEASURED rather than exempted. A downward
# --- face is where the print has to bridge, so the question is not whether any
# --- exists - the screw bores guarantee two - but how far each one spans.
# --- Grouping the downward faces into connected regions and taking each one's
# --- larger horizontal extent gives that, conservatively: a tunnel roof is
# --- anchored along its length and really spans its diameter, while a flat
# --- window roof is anchored only at the columns either side and spans the
# --- whole width, so the larger extent is right for the case that matters and
# --- pessimistic for the one that does not.
#
# --- This replaces exempting the bores by position. A position exemption
# --- follows the hole if the hole moves, and it encodes the assumption that
# --- 2.9 mm bridges fine instead of testing it. The gables exist precisely so
# --- that no window contributes a bridge at all; nothing here checked that
# --- until now.
BRIDGE_MAX = 12.0

normals, areas = mesh.face_normals, mesh.area_faces
on_bed = mesh.triangles_center[:, 2] < mesh.vertices[:, 2].min() + 0.1
down = (normals[:, 2] < -math.cos(math.radians(45.0))) & ~on_bed

spans = []
if down.any():
    for region in mesh.submesh([np.where(down)[0]], append=True).split(
            only_watertight=False):
        spans.append(float(region.extents[:2].max()))
worst = max(spans) if spans else 0.0
check(f"no bridge over {BRIDGE_MAX:.0f} mm", worst <= BRIDGE_MAX,
      f"{len(spans)} unsupported region(s), widest {worst:.2f} mm"
      + (f" [{', '.join(f'{s:.1f}' for s in sorted(spans, reverse=True)[:4])}]"
         if spans else ""))
check("no unsupported overhangs beyond the bores",
      float(areas[down].sum()) < 60.0,
      f"{float(areas[down].sum()):.1f} mm2 facing down, "
      f"bed contact {float(areas[on_bed].sum()):.0f} mm2")

vol = mesh.volume / 1000.0
print(f"stand10 v{S.VERSION} - verification")
print("\n".join(notes))
print(f"\n  volume {vol:.1f} cm3, PETG solid {vol * 1.27:.0f} g")
print(f"  {'ALL CHECKS PASSED' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
