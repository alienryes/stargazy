"""Verification for stand10.stl. Run after every build.

The checks that matter here are not "is the mesh valid" - they are the ones
that would otherwise only fail on the panel:

  - the screw axes are CLEAR. A fastener needs the ABSENCE of material, and
    asking whether the pad is present at the screw position answers a
    different question - one that returns True when the hole is missing.
  - the step is real and lands the right way round: relieved on the boss plane
    below the bolt line, touching the plate above it. Getting this backwards
    would look identical in a render.
  - nothing reaches into the panel, and nothing reaches up into the Pi.
"""

import math
import sys

import numpy as np
import trimesh

import stand10 as S

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


mesh = trimesh.load("stand10.stl")

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
grid_x = np.linspace(-S.col_in + 2, S.col_in - 2, 9)

pad_probe = to_desk(*np.array(
    [(x, s, 0.5) for x in grid_x for s in (20.0, 30.0, 41.0)]).T)
pad_clear = ~mesh.contains(pad_probe)
check("relieved below the bolt line", pad_clear.all(),
      f"n={len(pad_probe)}, {int((~pad_clear).sum())} touching")

# Sampled on the columns and the centre rib, where the bearing face survives
# the windows - the windows deliberately remove it in between.
bear_xs = [-S.BOSS_DX / 2.0, 0.0, S.BOSS_DX / 2.0]
bear_probe = to_desk(*np.array(
    [(x, s, 0.5) for x in bear_xs for s in (S.bear_s0 + 2, 75.0, S.bear_s1 - 2)]).T)
bear_solid = mesh.contains(bear_probe)
check("bearing face on the plate", bear_solid.all(),
      f"n={len(bear_probe)}, {int((~bear_solid).sum())} missing")

# --- The two faces really are 3 mm apart, measured off the mesh rather than
# --- assumed from the parameters that drew it.
pv = to_panel(mesh.vertices)
front_pad = pv[(pv[:, 1] < S.pad_s1 - 1) & (pv[:, 1] > 5)][:, 2].min()
front_bear = pv[(pv[:, 1] > S.bear_s0 + 1)][:, 2].min()
step = front_pad - front_bear
check("step is 3.0 mm", abs(step - S.BOSS_PROUD) < 0.05,
      f"pad t={front_pad:.3f}, bearing t={front_bear:.3f}, step {step:.3f}")

# --- Nothing may intrude into the panel, and nothing may reach the Pi.
check("nothing in front of the plate", pv[:, 2].min() > -TOL,
      f"min t {pv[:, 2].min():.3f}")
check("clears the Pi at s=95.5", pv[:, 1].max() < S.PI_S0 - TOL,
      f"max s {pv[:, 1].max():.2f}, Pi at {S.PI_S0}")

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
# --- The screw bores are exempt and are counted separately. They run along the
# --- panel's normal, so each has a drooping roof by construction; the span is
# --- 2.9 mm, which bridges. Exempting them by position rather than by raising
# --- the threshold keeps a new overhang anywhere else a failure.
normals, areas = mesh.face_normals, mesh.area_faces
centres = mesh.triangles_center
on_bed = centres[:, 2] < mesh.vertices[:, 2].min() + 0.1

d = np.array([0.0, math.cos(A), -math.sin(A)])
in_bore = np.zeros(len(centres), dtype=bool)
for sx in (-1, 1):
    p0 = to_desk(np.array([sx * S.BOSS_DX / 2.0]), np.array([S.BOSS_S]),
                 np.array([0.0]))[0]
    v = centres - p0
    in_bore |= np.linalg.norm(v - np.outer(v @ d, d), axis=1) < S.hole_d
bore_area = float(areas[in_bore & (normals[:, 2] < 0)].sum())

down = (normals[:, 2] < -math.cos(math.radians(45.0))) & ~on_bed & ~in_bore
bad_area = float(areas[down].sum())
check("no unsupported overhangs", bad_area < 1.0,
      f"{bad_area:.2f} mm2 outside the bores "
      f"(bores {bore_area:.0f}, bed contact {float(areas[on_bed].sum()):.0f})")

vol = mesh.volume / 1000.0
print(f"stand10 v{S.VERSION} - verification")
print("\n".join(notes))
print(f"\n  volume {vol:.1f} cm3, PETG solid {vol * 1.27:.0f} g")
print(f"  {'ALL CHECKS PASSED' if not fails else 'FAILED: ' + ', '.join(fails)}")
sys.exit(1 if fails else 0)
