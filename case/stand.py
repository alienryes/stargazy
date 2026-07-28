"""Desk stand leg for the Touch Display 2 (5") stargazing case.

Remix of RonnyS's "Raspberry Pi Touch Display 2 Case" (Printables 1377047,
CC-BY), re-worked for the 5" panel. TWO of these are printed, one bolted to
each X flange of the case-bottom (x = +-58) with 2x M2.5 screws 70.7mm apart.

Geometry: an easel leg. The mounting face lies flat on the case-bottom's rear
face; the foot lies on the desk. Because the display leans back by `tilt`, the
angle between those two faces is (90 - tilt). The leg is a triangle - arm up
the case back, foot along the desk, strut across - lightened by a triangular
void, with a boss at each screw so the head always seats on a flat pad.

MODELLED IN PRINT ORIENTATION: profile flat on the bed (X = along the mounting
face, Y = away from the case, Z = leg width). Prints flat, no supports, no
overhangs - it is a simple 2D extrusion.

Assembly mapping (leg frame -> case frame, for the +x leg):
    case_Y = FACE_Y0 + x     case_Z = FACE_Z0 + y
so the mounting face (y=0) lands on the case-bottom's rear face (Z=2.5) and
the foot edge lies in the desk plane. The -x leg is the same part mirrored in
X placement only (the part itself is symmetric through its thickness).
"""

import math

import cadquery as cq

VERSION = "0.1.0"

# ============================================================
# PARAMETERS - all mm / degrees.
# ============================================================
tilt = 20.0           # display lean-back from vertical

# --- Interface to case_bottom.py (must match) ---
hole_span = 70.7      # M2.5 screw spacing along the mounting face
screw_d = 2.9         # M2.5 clearance
cbore_d = 5.2         # cylindrical head counterbore
cbore_depth = 2.5

# --- Where the mounting face sits in case coords (see assembly mapping) ---
# FACE_Y0 is the case Y at which the leg's foot meets the desk plane, derived
# in case_bottom/shell terms: the desk is set 3mm below the shell's lowest
# corner so the case never rests on itself - the legs carry it.
FACE_Y0 = -51.01
FACE_Z0 = 2.5
CASE_HOLE_Y = 35.35   # case-bottom stand holes at Y = +-35.35

# --- Leg proportions ---
arm_len = 93.0        # along the mounting face from the foot end
foot_len = 60.0       # along the desk from the same corner
leg_w = 8.0           # thickness (Z in print orientation)
arm_t = 9.0           # rib thickness along the mounting face
foot_t = 6.0          # rib thickness along the desk
strut_t = 8.0         # rib thickness across the back
boss_d = 8.0          # flat pad around each screw (= leg_w, stays flush)
boss_h = 9.0          # pad height off the mounting face

# ============================================================
# DERIVED
# ============================================================
s, c = math.sin(math.radians(tilt)), math.cos(math.radians(tilt))

# screw positions along the mounting face, measured from the foot corner
d_lo = -CASE_HOLE_Y - FACE_Y0          # 15.66
d_hi = CASE_HOLE_Y - FACE_Y0           # 86.36
assert abs((d_hi - d_lo) - hole_span) < 1e-6, "hole span does not match"

# outer triangle: corner at the foot end, arm up the face, foot along the desk
p_corner = (0.0, 0.0)
p_arm = (arm_len, 0.0)
p_foot = (foot_len * s, foot_len * c)

assert d_hi + 4.0 < arm_len, "upper screw too close to the arm tip"


def _line(p, q, inside):
    """Return (nx, ny, k) for n.X = k, with n the unit normal pointing
    toward `inside`."""
    dx, dy = q[0] - p[0], q[1] - p[1]
    n = (-dy, dx)
    ln = math.hypot(*n)
    n = (n[0] / ln, n[1] / ln)
    k = n[0] * p[0] + n[1] * p[1]
    if n[0] * inside[0] + n[1] * inside[1] < k:      # normal points outward
        n, k = (-n[0], -n[1]), -k
    return n[0], n[1], k


def _cross(la, lb):
    """Intersection of two lines given as (nx, ny, k)."""
    a1, b1, c1 = la
    a2, b2, c2 = lb
    det = a1 * b2 - a2 * b1
    return ((c1 * b2 - c2 * b1) / det, (a1 * c2 - a2 * c1) / det)


# inset each edge by its rib thickness to get the lightening void
l_arm = _line(p_corner, p_arm, p_foot)
l_foot = _line(p_corner, p_foot, p_arm)
l_strut = _line(p_arm, p_foot, p_corner)
v_arm = (l_arm[0], l_arm[1], l_arm[2] + arm_t)
v_foot = (l_foot[0], l_foot[1], l_foot[2] + foot_t)
v_strut = (l_strut[0], l_strut[1], l_strut[2] + strut_t)
void = [_cross(v_arm, v_foot), _cross(v_arm, v_strut),
        _cross(v_foot, v_strut)]

# ============================================================
# MODEL  (print orientation: profile on the bed, extrude in Z)
# ============================================================
leg = (
    cq.Workplane("XY")
    .polyline([p_corner, p_arm, p_foot]).close()
    .extrude(leg_w)
)
leg = leg.cut(
    cq.Workplane("XY").polyline(void).close().extrude(leg_w)
)

# screw bosses: flat pads standing off the mounting face (y = 0).
# NOTE: on an XZ workplane a POSITIVE extrude runs toward -Y, so the pads and
# bores are extruded negative to grow away from the case into +Y.
for d in (d_lo, d_hi):
    leg = leg.union(
        cq.Workplane("XZ")
        .circle(boss_d / 2)
        .extrude(-boss_h)
        .translate((d, 0, leg_w / 2))
    )

# screw holes + counterbores, bored along +y from the mounting face
for d in (d_lo, d_hi):
    leg = leg.cut(
        cq.Workplane("XZ").circle(screw_d / 2).extrude(-(boss_h + 2))
        .translate((d, 0, leg_w / 2))
    )
    leg = leg.cut(
        cq.Workplane("XZ").circle(cbore_d / 2).extrude(-cbore_depth)
        .translate((d, boss_h - cbore_depth, leg_w / 2))
    )

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(leg, "stand.stl", tolerance=0.01, angularTolerance=0.1)
print(f"stand v{VERSION}: arm {arm_len} x foot {foot_len} x {leg_w}mm, "
      f"tilt {tilt} deg, screws at d={d_lo:.2f}/{d_hi:.2f} "
      f"(case Y {-CASE_HOLE_Y}/{CASE_HOLE_Y})")
