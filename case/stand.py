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

HOW THE JOINT HOLDS - the tongue is a permanently sprung leaf, not a latch:

  - Two half-dovetail ribs, flaring toward -Y, each sweep a pocket in the arm.
    The leg material left under each flare cannot pass back through it, so the
    ribs capture the leg. Two of them, spread apart, also stop it pivoting away
    at either end.
  - The detent bump sits under the tongue AT ALL TIMES, including when fully
    seated, holding it deflected by the bump's full height. The tongue
    therefore pushes the leg AWAY from the flange, which presses each lip up
    against the underside of its rib flare. That is the preload: it takes up
    all the lift play, kills every rattle, and puts normal force on the slants
    whose friction resists sliding back down.
  - The up-stop falls out of the same contact. With the lips pressed against
    the flares, sliding further up would drive lip into flare, so it simply
    stops. Sliding DOWN opens the taper and is free, resisted only by friction
    - about 6 N against the 0.16 N a dangling leg actually applies.
  - The spring deflects 1.5 mm, roughly ten times the printer's tolerance, so
    the preload varies but is NEVER ZERO. That is the whole point, and it is
    what four earlier attempts lacked: they all located the leg precisely and
    then relied on 0.05-0.3 mm clearances to generate grip, which FDM cannot
    hold. Do not "improve" this by adding a hard stop that lifts the bump off
    the tongue - that removes the only source of tension in the joint.
  - Sustained deflection means creep, so the tongue is sized for a low steady
    strain (see CREEP_LIMIT) rather than for maximum force.

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

VERSION = "0.7.0"

# ============================================================
# PARAMETERS - all mm / degrees.
# ============================================================
tilts = (15.0, 20.0, 30.0)   # one leg exported per angle

# --- Interface to case_bottom.py (MUST match) ---
cleat_span_y = 48.0   # spacing of the ribs' -Y base edges (the load faces)
rib_t = 3.0           # rib base thickness along Y
rib_h = 3.5           # rib height off the flange face
rib_flare = 1.0       # rib undercut DEPTH toward -Y
rib_ledge = 10.0      # undercut angle from horizontal (self-locking, see below)
rib_lip = 1.2         # thickness of the rib's retaining lip
detent_y = -4.0       # Y of the bump's vertical face
detent_h = 1.5        # bump height - this IS the spring's deflection
detent_top = 1.2      # flat top width; the tongue rides on this
detent_face = 50.0    # +Y ramp, only needed here to know the bump's width
FACE_Z0 = 2.5         # case Z of the flange's rear face

# --- Fit ---
fit = 0.3             # clearance on the pocket's flat faces
# Sliding clearance on the pocket's -x wall. Keep it small: it is subtracted
# directly from the ledge's grip, since the lip can only reach as far under the
# ledge as this clearance allows.
side_clear = 0.15
# How far the spring may lift the leg before its lips meet the ledges. This is
# now dimensioned DIRECTLY rather than falling out of a slant clearance: the
# undercut is only 0.6mm deep, so a lift clearance anywhere near that would let
# the lip clear the ledge entirely.
# 0.20 rather than tighter because the ledge is a printed micro-overhang and
# will droop slightly into this gap.
lift_clear = 0.20
travel = 5.0          # slide distance from offer-up to seated

# --- Sprung tongue ---
# Longer and thicker than a latch would need: at equal force, scaling length
# and thickness together cuts the sustained strain, which is what governs creep.
tongue_t = 2.0        # tongue thickness (bends in the layer plane)
tongue_len = 21.0
tongue_gap = 2.0      # slot above the tongue; must exceed the deflection
tongue_lead = 1.0     # how far the tip reaches past the bump when seated

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

# --- Material, for the tongue and the ligament ---
E_PETG = 2000.0       # MPa
MU = 0.3              # PETG on PETG
CREEP_LIMIT = 0.013   # sustained strain ceiling - the tongue never relaxes
min_ligament = 2.5    # material left over the upper pocket, see below

# --- Mass model, for the tipping check only (grams, at case (Y, Z)) ---
masses = [
    (140.0, 0.0, -10.6),   # display module
    (58.0, 0.0, -9.4),     # shell
    (21.0, 0.0, 4.0),      # case_bottom
    (46.0, 0.0, 6.7),      # Raspberry Pi 4
    (33.0, 0.0, 20.0),     # lid
]

# ============================================================
# SPRING SIZING (tilt-independent)
# ============================================================
detent_run = detent_h / math.tan(math.radians(detent_face))
detent_span = detent_top + detent_run       # bump width, from its vertical face

# The bump bears on the middle of its flat top. Distance from there to the
# tongue's root is the working cantilever length when seated.
arm_eff = tongue_len - tongue_lead - detent_top / 2.0
_I = leg_w * tongue_t ** 3 / 12.0
preload = 3.0 * E_PETG * _I * detent_h / arm_eff ** 3
strain = 3.0 * tongue_t * detent_h / (2.0 * arm_eff ** 2)

# The preload presses the lips up against the retaining ledges. A ledge at
# angle `rib_ledge` from horizontal turns that uplift F into F*tan(ledge) along
# the slide, resisted by mu*F/cos(ledge) of friction - so the joint only holds
# itself together if sin(ledge) < mu. At 60 deg (the old dovetail) it was
# 1.75F against 0.30F and the spring ejected the leg; at 10 deg it is 0.18F
# against 0.31F and it locks.
rib_ledge_rise = rib_flare * math.tan(math.radians(rib_ledge))
_eject = math.tan(math.radians(rib_ledge))
_grip = MU / math.cos(math.radians(rib_ledge))
hold_force = MU * preload + preload * (_grip - _eject)
lift_play = lift_clear

assert tongue_gap > detent_h + 0.3, "slot too shallow for the tongue to deflect"
assert strain < CREEP_LIMIT, \
    f"tongue would creep: {100*strain:.2f}% sustained strain"
assert preload > 3.0, "preload too light to take up the lift play"
assert hold_force > 2.0, "not enough friction to hold a dangling leg"
assert math.sin(math.radians(rib_ledge)) < 0.7 * MU, \
    "retaining ledge too steep: the leg's own spring would eject it"
assert lift_clear < 0.5 * rib_flare, \
    "lift play comparable to the undercut depth - the lips would clear it"
# the leg's own lip, below the pocket's retaining face, must be a real block
assert rib_h - rib_lip - rib_ledge_rise - lift_clear > 1.0, \
    "the leg's lip would be thinner than a couple of layers"
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
    """Clearance for one rib whose load face is at x_r.

    The rib travels from x_r + travel (offered up) to x_r (seated), so the
    pocket is that swept region plus clearances. Its -x side reproduces the
    rib's retaining ledge, sitting lift_clear below it: that overlap is what
    the tongue's spring pulls the leg up against, and because the ledge is
    nearly flat the reaction is almost pure lift with no ejecting component.
    """
    right = x_r + rib_t + travel + fit
    top = rib_h + fit
    return [
        (x_r - side_clear, 0.0),
        (right, 0.0),
        (right, top),
        (x_r - rib_flare - side_clear, top),
        (x_r - rib_flare - side_clear, rib_h - rib_lip - lift_clear),
        (x_r - side_clear, rib_h - rib_lip - rib_ledge_rise - lift_clear),
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
    x_tip = x_bump - tongue_lead                  # tongue's free end
    x_root = x_tip + tongue_len

    lo_end = x_lo + rib_t + travel + fit          # +x end of the lower pocket
    hi_end = x_hi + rib_t + travel + fit          # +x end of the upper pocket
    hi_start = x_hi - side_clear - rib_flare

    # How much plastic is left over the upper pocket. The arm's outline there
    # is the strut edge running back from the tip, so the depth available
    # shrinks toward the tip and has nothing to do with arm_t.
    strut_slope = foot_len * c / (arm_len - foot_len * s)
    ligament = (arm_len - hi_end) * strut_slope - (rib_h + fit)

    assert x_tip > lo_end + 2.0, "tongue tip clashes with the lower pocket"
    assert x_root + 2.0 < hi_start, "tongue root clashes with the upper pocket"
    # the bump must stay under the tongue over the WHOLE stroke, or the spring
    # unloads part way and the leg goes slack
    assert x_bump > x_tip, "bump is off the tongue's tip when seated"
    assert x_bump + travel + detent_span < x_root - 1.0, \
        "bump runs off the tongue's root when the leg is offered up"
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

    # The tongue: a flush leaf, freed by the slot above it. There is NO relief
    # under it - the bump rides on the tongue's underside for the whole stroke
    # and never drops away, which is what keeps the spring loaded when seated.
    leg = _cut(leg, [(x_tip, tongue_t), (x_root, tongue_t),
                     (x_root, tongue_t + tongue_gap),
                     (x_tip, tongue_t + tongue_gap)])
    # break the slot out through the tip so the leaf is a cantilever, not a
    # bridge: a shallow notch from the tip up into the slot
    leg = _cut(leg, [(x_tip - 1.6, 0.0), (x_tip, 0.0),
                     (x_tip, tongue_t + tongue_gap),
                     (x_tip - 1.6, tongue_t + tongue_gap)])

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
              f"{x_tip:.1f}..{x_root:.1f}, bump {x_bump:.1f}..{x_bump+travel:.1f} "
              f"over the stroke, arm over pocket {ligament:.2f}, "
              f"tip margin {com_h - h_front:.1f}")
    return leg, report


# ============================================================
# EXPORT
# ============================================================
print(f"stand v{VERSION}: tongue sprung {detent_h}mm permanently -> "
      f"{preload:.1f}N preload, {hold_force:.1f}N to slide off, "
      f"{100*strain:.2f}% sustained strain ({100*CREEP_LIMIT:.1f}% ceiling); "
      f"lip {rib_lip}mm thick grips {rib_flare - side_clear:.2f}mm at "
      f"{rib_ledge:.0f} deg, ejects {_eject:.2f}F vs {_grip:.2f}F of "
      f"friction; leg lip {rib_h - rib_lip - rib_ledge_rise - lift_clear:.2f}mm, "
      f"lift play {lift_play:.2f}mm")
for t in tilts:
    solid, line = build_leg(t)
    name = f"stand_{int(t)}.stl"
    cq.exporters.export(solid, name, tolerance=0.01, angularTolerance=0.1)
    print(f"  {name}: {line}")
