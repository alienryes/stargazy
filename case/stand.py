"""Snap-on desk stand leg for the Touch Display 2 (5") stargazing case.

Remix of RonnyS's "Raspberry Pi Touch Display 2 Case" (Printables 1377047,
CC-BY), re-worked for the 5" panel. TWO of these are printed per stand, one on
each X flange of the case-bottom. They take NO screws: each leg slides onto
three ribs moulded into the flange's rear face (see case_bottom.py).

Geometry: an easel leg. The mounting face lies flat on the case-bottom's rear
face; the foot lies on the desk. Because the display leans back by `tilt`, the
angle between those two faces is (90 - tilt). The leg is a triangle - arm up
the case back, foot along the desk, strut across - lightened by a triangular
void.

How the joint works, and why it is arranged this way:

  - The leg slides UP (+case Y) to engage. That is the direction the case's own
    weight drives it, so service load seats the joint deeper instead of working
    it loose.
  - Two half-dovetail ribs, flaring toward -Y, each sweep a pocket in the arm.
    Once the leg has slid up, the leg material left under each flare cannot
    pass back through it, so the leg cannot be pulled off the face. Two of
    them, spread apart, also stop the leg pivoting away at either end.
  - The tapers are also the up-stop: the leg slides until the pocket's slanted
    wall wedges on the rib's, which takes up all the clearance at once. There
    is no separate hard stop, so the seated position depends on print
    tolerance by a few tenths - irrelevant at these loads.
  - A compliant tongue rides over the detent bump and drops behind it,
    latching the leg against sliding back DOWN. That only has to beat the
    leg's own weight (0.16 N) when the case is picked up; it is sized far
    beyond that so it clicks positively.
  - Release is by pushing the leg back down, hard. The detent's ramps are
    symmetric because there is no way to reach the tongue's back face once
    the leg is on - the case is behind it - so a press-to-release latch would
    be unreachable. Sliding it off is the only usable release action.

MODELLED IN PRINT ORIENTATION: profile flat on the bed (X = along the mounting
face, Y = away from the case, Z = leg width). Every feature is prismatic in Z,
so the part prints as one stack of identical layers - no supports, and the
tongue bends in the layer plane rather than across it, so there is no
delamination path through the joint.

Assembly mapping (leg frame -> case frame):
    case_Y = FACE_Y0 + x     case_Z = FACE_Z0 + y
so the mounting face (y=0) lands on the case-bottom's rear face (Z=2.5) and
the foot edge lies in the desk plane. The -x leg is the same part mirrored in
X placement only (the part itself is symmetric through its thickness).
"""

import math

import cadquery as cq

VERSION = "0.2.0"

# ============================================================
# PARAMETERS - all mm / degrees.
# ============================================================
tilts = (15.0, 20.0, 30.0)   # one leg exported per angle

# --- Interface to case_bottom.py (MUST match) ---
cleat_span_y = 56.0   # spacing of the ribs' -Y base edges (the load faces)
rib_t = 3.0           # rib base thickness along Y
rib_h = 3.5           # rib height off the flange face
rib_flare = 2.0       # rib undercut at the top, toward -Y
detent_y = 0.0        # detent bump apex in case Y
detent_h = 1.2        # bump height
FACE_Z0 = 2.5         # case Z of the flange's rear face

# --- Fit (PETG; it prints slightly proud, so these are not bare nominals) ---
fit = 0.3             # clearance on the pocket's flat faces
slant_fit = 0.25      # perpendicular clearance on the dovetail slant
travel = 5.0          # slide distance from offer-up to seated

# --- Detent tongue ---
tongue_t = 1.8        # tongue thickness (bends in the layer plane)
tongue_len = 16.0
tongue_gap = 2.0      # slot above the tongue; must exceed the deflection
detent_gap = 0.2      # play along the slide once latched
relief_len = 4.0      # full-depth pocket the bump sits in when seated

# --- Leg proportions ---
arm_len = 93.0        # along the mounting face from the foot corner
foot_len = 60.0       # along the desk from the same corner
leg_w = 8.0           # thickness (Z in print orientation) = rib length
arm_t = 9.0           # rib thickness along the mounting face
foot_t = 6.0          # rib thickness along the desk
strut_t = 8.0         # rib thickness across the back

# --- Desk plane ---
desk_clear = 3.0      # the legs carry the case; it never rests on its own corner
# (case_Y, case_Z) corners that could reach the desk once tilted. Which one is
# lowest depends on the angle: the shell's rear-bottom corner governs at 20
# deg, but the lid's takes over past ~28 deg, which is why the desk plane is
# derived per tilt instead of hardcoded.
case_corners = [
    (-48.73, 0.0),     # shell, bottom rear (back plate outer face)
    (-48.73, -18.8),   # shell, bottom front (glass side)
    (-38.0, 2.5),      # case_bottom, bottom rear
    (-32.0, 30.4),     # case_top, bottom rear (lid outer face)
]

# --- Mass model, for the tipping check only (grams, at case (Y, Z)) ---
masses = [
    (140.0, 0.0, -10.6),   # display module
    (58.0, 0.0, -9.4),     # shell
    (21.0, 0.0, 4.0),      # case_bottom
    (46.0, 0.0, 6.7),      # Raspberry Pi 4
    (33.0, 0.0, 20.0),     # lid
]

# --- Material, for the detent check ---
E_PETG = 2000.0       # MPa
MU = 0.3              # PETG on PETG
STRAIN_LIMIT = 0.025  # PETG yields ~4.5%; stay well inside it

# ============================================================
# DETENT SIZING (tilt-independent)
# ============================================================
deflect = detent_h + 0.3
_I = leg_w * tongue_t ** 3 / 12.0
snap_force = 3.0 * E_PETG * _I * deflect / tongue_len ** 3
slide_force = snap_force * (MU + 1.0) / (1.0 - MU)      # 45 deg ramps
strain = 3.0 * tongue_t * deflect / (2.0 * tongue_len ** 2)

assert tongue_gap > deflect, "slot too shallow for the tongue to deflect"
assert strain < STRAIN_LIMIT, f"tongue overstrained at {100*strain:.1f}%"
assert 5.0 < slide_force < 40.0, "detent is either limp or unassemblable"
assert relief_len > detent_h + detent_gap + 1.0, "bump has nowhere to seat"
assert arm_t - (rib_h + fit) > 4.0, "pockets leave too little arm behind them"
assert arm_t - (tongue_t + tongue_gap) > 4.0, "tongue slot undercuts the arm"
assert travel > rib_flare + 1.0, "not enough travel to clear the undercut"


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


def _cut(part, pts):
    """Cut a profile polygon clean through the leg's width."""
    return part.cut(
        cq.Workplane("XY").polyline(pts).close()
        .extrude(leg_w + 2).translate((0, 0, -1))
    )


def _pocket(x_r):
    """Swept clearance for one half-dovetail rib whose load face is at x_r.

    The rib travels from x_r + travel (offered up) to x_r (seated); the region
    it sweeps is the convex hull of both positions, dilated by the fit
    clearances. The slanted -x wall is what captures the rib's flare, and its
    wedge against the rib is what stops the slide.
    """
    dx = slant_fit * math.hypot(rib_flare, rib_h) / rib_h
    top = rib_h + fit
    return [
        (x_r - dx, 0.0),
        (x_r + rib_t + travel + fit, 0.0),
        (x_r + rib_t + travel + fit, top),
        (x_r - dx - rib_flare * top / rib_h, top),
    ]


def build_leg(tilt):
    """Return (solid, report) for one leg at the given lean-back angle."""
    s, c = math.sin(math.radians(tilt)), math.cos(math.radians(tilt))

    # Desk plane: the lowest case corner, once tilted, clears it by desk_clear.
    v_min = min(cy * c - cz * s for (cy, cz) in case_corners)
    face_y0 = (v_min - desk_clear + FACE_Z0 * s) / c

    # Interface positions in leg coordinates
    x_lo = -cleat_span_y / 2 - face_y0
    x_hi = cleat_span_y / 2 - face_y0
    x_bump = detent_y - face_y0
    x_tip = x_bump + detent_h + detent_gap        # tongue's free end
    x_root = x_tip + tongue_len

    lo_end = x_lo + rib_t + travel + fit          # +x end of the lower pocket
    hi_start = x_hi - slant_fit - rib_flare * (rib_h + fit) / rib_h

    assert x_tip - relief_len > lo_end + 2.0, "tongue relief clashes with a pocket"
    assert x_root + 2.0 < hi_start, "tongue root clashes with the upper pocket"
    assert x_bump + travel + detent_h < x_root - 1.0, \
        "bump misses the tongue when the leg is offered up"
    assert x_hi + rib_t + travel + fit + 2.0 < arm_len, \
        "upper pocket runs off the end of the arm"

    # Outer triangle: corner at the foot end, arm up the face, foot on the desk
    p_corner = (0.0, 0.0)
    p_arm = (arm_len, 0.0)
    p_foot = (foot_len * s, foot_len * c)

    leg = (
        cq.Workplane("XY")
        .polyline([p_corner, p_arm, p_foot]).close()
        .extrude(leg_w)
    )

    # inset each edge by its rib thickness to get the lightening void
    l_arm = _line(p_corner, p_arm, p_foot)
    l_foot = _line(p_corner, p_foot, p_arm)
    l_strut = _line(p_arm, p_foot, p_corner)
    v_arm = (l_arm[0], l_arm[1], l_arm[2] + arm_t)
    v_foot = (l_foot[0], l_foot[1], l_foot[2] + foot_t)
    v_strut = (l_strut[0], l_strut[1], l_strut[2] + strut_t)
    void = [_cross(v_arm, v_foot), _cross(v_arm, v_strut),
            _cross(v_foot, v_strut)]
    leg = _cut(leg, void)

    # cleat pockets
    leg = _cut(leg, _pocket(x_lo))
    leg = _cut(leg, _pocket(x_hi))

    # detent: full-depth relief the bump seats in, then the slot that frees
    # the tongue. The tongue's tip faces -x, so the bump - which travels -x
    # relative to the leg - rides under it and drops off its tip.
    slot_top = tongue_t + tongue_gap
    leg = _cut(leg, [(x_tip - relief_len, 0.0), (x_tip, 0.0),
                     (x_tip, slot_top), (x_tip - relief_len, slot_top)])
    leg = _cut(leg, [(x_tip, tongue_t), (x_root, tongue_t),
                     (x_root, slot_top), (x_tip, slot_top)])

    # --- verify the desk plane and tipping margin numerically ---
    def world_h(cy, cz):
        return cy * s + cz * c

    def world_v(cy, cz):
        return cy * c - cz * s

    v_foot_edge = world_v(face_y0, FACE_Z0)
    clear = v_min - v_foot_edge
    assert abs(clear - desk_clear) < 1e-6, "desk clearance derivation is wrong"

    m_tot = sum(m for (m, _, _) in masses)
    com_h = sum(m * world_h(cy, cz) for (m, cy, cz) in masses) / m_tot
    h_front = world_h(face_y0, FACE_Z0)
    h_back = h_front + foot_len
    assert h_front + 5.0 < com_h < h_back - 5.0, \
        f"tips over at {tilt} deg: CoM {com_h:.1f} vs feet {h_front:.1f}..{h_back:.1f}"

    bb = leg.val().BoundingBox()
    report = (f"tilt {tilt:.0f} deg: {bb.xlen:.1f} x {bb.ylen:.1f} x "
              f"{bb.zlen:.1f}mm, face_y0 {face_y0:.2f}, desk clear "
              f"{clear:.1f}, ribs at x {x_lo:.1f}/{x_hi:.1f}, tongue "
              f"{x_tip:.1f}..{x_root:.1f}, tip margin {com_h - h_front:.1f}")
    return leg, report


# ============================================================
# EXPORT
# ============================================================
print(f"stand v{VERSION}: detent {snap_force:.1f}N flex / "
      f"{slide_force:.1f}N slide, strain {100*strain:.2f}% "
      f"({STRAIN_LIMIT/strain:.1f}x margin)")
for t in tilts:
    solid, line = build_leg(t)
    name = f"stand_{int(t)}.stl"
    cq.exporters.export(solid, name, tolerance=0.01, angularTolerance=0.1)
    print(f"  {name}: {line}")
