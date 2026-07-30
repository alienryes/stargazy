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
  - THE TAPERS ARE THE CLAMP, and they are the whole retention mechanism. The
    rib's slant leans toward -Y as it rises and the lip bears on it from
    below, so pushing the leg up drives the lip along the slant and the
    reaction pulls the leg ONTO the flange. Push harder, grip harder, and the
    friction that results is what stops it sliding back down. A wedge is also
    the only feature here that shrugs off print tolerance: whatever slack the
    printer leaves, the leg slides a fraction further until it grips.
    Consequence: NOTHING else may stop the slide. Three printed versions had
    no tension in them because a hard up-stop landed 0.1mm before the taper
    could touch, so it never clamped.
  - The tongue and bump are a BACKSTOP, not the retention. They are slack by
    1mm at both ends so they cannot become the up-stop; they only catch the
    leg if the wedge ever relaxes.
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

VERSION = "0.5.0"

# ============================================================
# PARAMETERS - all mm / degrees.
# ============================================================
tilts = (15.0, 20.0, 30.0)   # one leg exported per angle

# --- Interface to case_bottom.py (MUST match) ---
cleat_span_y = 48.0   # spacing of the ribs' -Y base edges (the load faces)
rib_t = 3.0           # rib base thickness along Y
rib_h = 3.5           # rib height off the flange face
rib_flare = 2.0       # rib undercut at the top, toward -Y
detent_y = -4.0       # Y of the bump's vertical face (the up-stop)
detent_h = 1.5        # bump height
detent_top = 1.2      # flat top width
detent_face = 50.0    # +Y retention ramp, degrees from horizontal
FACE_Z0 = 2.5         # case Z of the flange's rear face

# --- Fit (PETG; it prints slightly proud, so these are not bare nominals) ---
fit = 0.3             # clearance on the pocket's flat faces
# THE DOVETAIL TAPER IS THE CLAMP. The rib's slant leans toward -Y as it
# rises and the leg's lip bears on it from underneath, so pushing the leg UP
# drives the lip along the slant and the reaction pulls the leg ONTO the
# flange: a self-clamping tapered slide. Push harder, grip harder.
#
# Keep this clearance small. A wedge is the one feature here that is immune to
# print tolerance - whatever slack the printer leaves, the leg simply slides a
# fraction further until it grips - but only if nothing else stops it first.
# v0.12.0 had 0.15 here AND a hard up-stop 0.1mm before the wedge could touch,
# which is why three printed versions had no tension in them at all.
slant_fit = 0.05      # perpendicular clearance on the dovetail slant
travel = 5.0          # slide distance from offer-up to seated

# --- Backstop tongue ---
# Secondary only: the taper holds the leg, this just catches it if the wedge
# ever relaxes. Deliberately SLACK so it can never become the up-stop and
# rob the taper of its grip - that was the v0.12.0 mistake.
tongue_t = 2.0        # tongue thickness (bends in the layer plane)
tongue_len = 18.0
tongue_gap = 2.2      # slot above the tongue; must exceed the deflection
detent_gap = 1.0      # slack from the tongue's tip to the ramp when seated
up_gap = 1.0          # slack at the relief's -Y wall, so the bump never butts

# Material that must remain between the upper pocket's roof and the arm's
# outline. The arm tapers to a point at its tip, so the depth available there
# is set by the strut edge, NOT by arm_t: at cleat_span_y 56 the pocket ended
# where the outline was only 4.43mm tall, leaving 0.63mm of plastic holding
# the tip on - the slicer gave it a perimeter and no infill.
min_ligament = 2.5

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
detent_run = detent_h / math.tan(math.radians(detent_face))
detent_span = detent_top + detent_run       # bump width, from its vertical face
# The relief is sized to the bump, not chosen: the bump is trapped between the
# relief's -Y wall (up-stop) and the tongue's tip (latch), with only up_gap +
# detent_gap of play. An oversized relief is what made v0.11.0 feel dead.
relief_len = up_gap + detent_span + detent_gap

deflect = detent_h + 0.3
_I = leg_w * tongue_t ** 3 / 12.0
snap_force = 3.0 * E_PETG * _I * deflect / tongue_len ** 3
_ramp = math.tan(math.radians(detent_face))
slide_force = snap_force * (MU + _ramp) / (1.0 - MU * _ramp)
strain = 3.0 * tongue_t * deflect / (2.0 * tongue_len ** 2)

# Travel past nominal at which the tapers wedge and start clamping. This must
# happen FIRST - it is the whole retention mechanism - so both the bump's
# vertical face and the tongue's tip are held well clear of it.
wedge_travel = slant_fit * math.hypot(rib_flare, rib_h) / rib_h
lift_play = slant_fit / (rib_flare / math.hypot(rib_flare, rib_h))

assert tongue_gap > deflect, "slot too shallow for the tongue to deflect"
assert strain < STRAIN_LIMIT, f"tongue overstrained at {100*strain:.1f}%"
assert 5.0 < slide_force < 40.0, "backstop is either limp or unassemblable"
assert MU * _ramp < 1.0, "retention ramp self-locks: the leg could not come off"
assert up_gap > wedge_travel + 0.5, \
    "bump would butt before the taper clamps - the joint would have no grip"
assert detent_gap > wedge_travel + 0.5, \
    "tongue must drop behind the ramp before the taper clamps"
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
    x_bump = detent_y - face_y0                   # the bump's vertical face
    x_tip = x_bump + detent_span + detent_gap     # tongue's free end
    x_root = x_tip + tongue_len

    lo_end = x_lo + rib_t + travel + fit          # +x end of the lower pocket
    hi_end = x_hi + rib_t + travel + fit          # +x end of the upper pocket
    hi_start = x_hi - slant_fit - rib_flare * (rib_h + fit) / rib_h

    # How much plastic is left over the upper pocket. The arm's outline there
    # is the strut edge running back from the tip, so the depth available
    # shrinks toward the tip and has nothing to do with arm_t.
    strut_slope = foot_len * c / (arm_len - foot_len * s)
    ligament = (arm_len - hi_end) * strut_slope - (rib_h + fit)

    assert x_tip - relief_len > lo_end + 2.0, "tongue relief clashes with a pocket"
    assert x_root + 2.0 < hi_start, "tongue root clashes with the upper pocket"
    assert x_bump + travel + detent_span < x_root - 1.0, \
        "bump misses the tongue when the leg is offered up"
    assert ligament >= min_ligament, \
        f"only {ligament:.2f}mm of arm over the upper pocket - the tip would " \
        f"hang off a sliver; pull cleat_span_y in"

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

    # detent: the relief the bump is trapped in, then the slot that frees the
    # tongue. The tongue's tip faces -x, so the bump - which travels -x
    # relative to the leg - rides under it and drops off its tip. The relief's
    # -x wall then butts the bump's vertical face: that is the up-stop.
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
              f"{x_tip:.1f}..{x_root:.1f}, arm over pocket {ligament:.2f}, "
              f"tip margin {com_h - h_front:.1f}")
    return leg, report


# ============================================================
# EXPORT
# ============================================================
print(f"stand v{VERSION}: taper clamps after {wedge_travel:.3f}mm of push "
      f"(slant_fit {slant_fit}, lift play {lift_play:.2f}mm); backstop "
      f"{slide_force:.1f}N at {100*strain:.2f}% strain, slack "
      f"{detent_gap:.1f}/{up_gap:.1f}mm so it never robs the clamp")
for t in tilts:
    solid, line = build_leg(t)
    name = f"stand_{int(t)}.stl"
    cq.exporters.export(solid, name, tolerance=0.01, angularTolerance=0.1)
    print(f"  {name}: {line}")
