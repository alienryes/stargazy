"""Bolt-on desk stand for the Touch Display 2 (5") stargazing case.

Remix of RonnyS's "Raspberry Pi Touch Display 2 Case" (Printables 1377047,
CC-BY), re-worked for the 5" panel. TWO of these are printed per stand, one on
each X flange of the case-bottom, and each bolts on with that side's two M2.5
case screws - the same screws that already clamp case_bottom -> shell ->
display. No extra fasteners, and nothing self-tapping.

SHAPE - an L, not a triangle, and that distinction is the whole design:

  - a flat STRAP lying on the case-bottom's rear face, carrying both screws
  - a STRUT leaving the strap's -Y end and lying IN the desk plane

There is deliberately no diagonal brace from the strut back up to the strap.
A brace would have to cross the +X port band, which is what killed the
previous side-flange leg: its arm sat at Z 2.5-11.5 while the Pi's USB and
Ethernet plugs start at Z 6.65, so the bottom of every plug fouled it.
Everything here either stays under the plugs (the strap) or stays outboard of
them in Y (the strut).

WHY THE STRAP CAN BE THIN: the strut's root is itself a desk contact - the
toe at leg (0, 0) touches the desk - so the strut runs load straight to ground
in compression and the strap barely sees bending. The strap is thickened past
the port band anyway, where there is room, so that a lifted toe (print
tolerance) still leaves a healthy margin.

MODELLED IN PRINT ORIENTATION: profile flat on the bed (x = along the mounting
face, y = away from the case, z = strap width). Every profile feature is
prismatic in z, so the part prints as one stack of identical layers - no
supports and no downward-facing faces. The screw holes run along y and so
print as horizontal bores; their roofs droop slightly, which is why the
counterbore is opened up a little.

Assembly mapping (leg frame -> case frame):
    case_Y = face_y0 + x     case_Z = FACE_Z0 + y
so the mounting face (y=0) lands on the case-bottom's rear face (Z=2.5) and
the desk plane passes through the leg's origin. `face_y0` is DERIVED per tilt
from whichever case corner is lowest once tilted - the shell's rear-bottom
corner governs at 20 deg, but the lid's takes over past ~28 deg.
"""

import math

import cadquery as cq
from shapely.geometry import Polygon
from shapely.geometry import box as shapely_box

VERSION = "1.4.0"

# ============================================================
# PARAMETERS - all mm / degrees.
# ============================================================
tilts = (15.0, 20.0, 30.0)   # one stand exported per angle

# --- Interface to case_bottom.py (MUST match) ---
FACE_Z0 = 2.5         # case Z of the flange's rear face - the mounting plane
strap_x0 = 49.0       # inboard edge in case X: clears the -X wall at -48.5
strap_x1 = 63.0       # outboard edge = case_bottom half_x, flush with the plate
disp_span_x = 103.7   # case-screw spacing along X (103.7 x 51 pattern)
disp_span_y = 51.0    # case-screw spacing along Y
# Outer face of case_bottom's perimeter wall on the -X side. That side runs the
# full length of the plate, so it - not the +X side, whose wall is cut away
# across the port gap - is what limits how far inboard the strap may reach.
wall_x = 48.5

# --- Screws: the display's own M2.5 case screws pass through the strap ---
screw_d = 2.9         # M2.5 clearance
screw_head_d = 4.7    # M2.5 head OD
cbore_d = 5.4         # head + 0.7: the bore is horizontal in print orientation,
                      # so its roof droops slightly and wants the extra room
cbore_depth = 2.0
screw_head_h = 2.5    # M2.5 socket cap; pan head is 1.9, so this is the worst case
strap_end = 5.5       # strap tail past the upper screw

# --- Strap ---
# Thin across the port band because the plugs sit just above it; thick past
# the band, where the strut lands and the bending actually is.
strap_t_thin = 3.0
strap_t_thick = 6.0
# The step between them is chamfered to take the stress riser out of the
# corner where the strut lands. It runs BACKWARDS into the thick section, so
# the thin section still begins exactly at x_step and neither the plug-band
# limit nor the counterbore limit moves. 3.0 over a 3.0 step = 45 deg.
step_chamfer = 3.0
# Fillet on the inside of the L, where the strut's inner edge meets the thick
# strap. That corner carries whatever bending the strut does not take in pure
# compression, so it is the one place a stress riser matters.
#
# This is a CEILING, not the value used. The corner's empty wedge is
# (90 - tilt) deg, so the fillet's tangent point sits r/tan(wedge/2) back along
# the strap - 5.20mm at 30 deg for r=3, against only 4.52mm of flat strap
# before the chamfer begins. The radius is therefore derived per tilt from the
# run actually available and capped here; at 30 deg it comes out at 2.3.
join_fillet = 3.0

# --- Strut ---
foot_len = 45.0       # contact length along the desk, from the toe
foot_t = 9.0          # strut thickness at the root, measured off the desk plane
# The strut steps down to a thinner section for its outer half, mirroring what
# the strap does - same 45 deg chamfer, same 2:1 ratio. Its bending moment is
# largest at the root and zero at the tip, so the material out there was doing
# nothing. It also moves the strut's inner edge further from the Pi's plug
# band, which is what limits the 30 deg variant.
foot_t_thin = 4.5
foot_step = 20.0      # distance along the desk, from the toe, where it thins

# --- Desk plane ---
desk_clear = 3.0      # the stands carry the case; it never rests on its own corner
# Extra height, purely to get the power lead out. The USB-C socket faces down at
# the -Y edge and even a right-angle lead's overmould was longer than the gap
# under the case. Lifting perpendicular to the desk buys lift/cos(tilt) of room
# along the plug axis, which is why it fixes all three tilts at once - unlike
# leaning further back, which moves the socket TOWARD the desk.
lift = 10.0
# (case_Y, case_Z) corners that could reach the desk once tilted. Validated
# against the assembled shell / case_bottom / case_top meshes: this list
# reproduces the true silhouette minimum at all three tilts.
case_corners = [
    (-48.73, 0.0),     # shell, bottom rear (back plate outer face)
    (-48.73, -18.9),   # shell, bottom front (glass side)
    (-38.0, 2.5),      # case_bottom, bottom rear
    (-32.0, 30.4),     # case_top, bottom rear (lid outer face)
]

# --- Raspberry Pi 4 plug keepout, in case coordinates ---
# MEASURED off the reference Pi 4 model, not assumed from the PCB top face:
# the +X connector shells hang 0.75mm BELOW the PCB's upper surface, so the
# band under them is 4.15mm, not the 4.9mm the board stack-up suggests.
# Plugs project further in +X than the sockets do, so there is no escaping
# this band by moving outboard - only by staying under it or clear in Y.
plug_y0, plug_y1 = -26.45, 25.70
plug_z0, plug_z1 = 6.65, 23.00
# Margin against ext_off_y, the one Pi-position number never verified on the
# real panel. 2mm of Y error still leaves the strut clear.
port_margin = 2.0

# --- Mass model, for the tipping check only (grams, at case (Y, Z)) ---
masses = [
    (140.0, 0.0, -10.6),   # display module
    (58.0, 0.0, -9.4),     # shell
    (21.0, 0.0, 4.0),      # case_bottom
    (46.0, 0.0, 6.7),      # Raspberry Pi 4
    (33.0, 0.0, 20.0),     # lid
]

# ============================================================
# DERIVED
# ============================================================
leg_w = strap_x1 - strap_x0
screw_ys = (-disp_span_y / 2, disp_span_y / 2)
# Position of the screw axis ACROSS the strap, in leg coordinates. This is NOT
# the strap's mid-width: the screws sit at case X 51.85 while the strap spans
# 49..63, so the axis is 2.85mm in from the inboard edge and 11.15mm from the
# outboard one. v1.1.0 put the bores at leg_w/2 and the holes came out 4.15mm
# outboard of the screws - the leg then had to be slid inboard to reach them,
# which drove its edge into the -X wall. Derive it, never centre it.
strap_z = disp_span_x / 2 - strap_x0
# highest case_Y any material may occupy while inside the plug band
port_keep_y = plug_y0 - port_margin

assert strap_t_thin + FACE_Z0 < plug_z0, \
    "strap is thicker than the gap under the Pi's +X connectors"
# The head bears on the counterbore FLOOR, so it may stand slightly proud of
# the strap; what it must not do is reach the plugs.
head_z = FACE_Z0 + strap_t_thin - cbore_depth + screw_head_h
assert head_z < plug_z0, \
    f"screw head reaches Z {head_z:.2f}, into the plug band at {plug_z0}"
assert strap_t_thin - cbore_depth >= 0.8, "counterbore floor too thin"
assert cbore_d >= screw_head_d + 0.5, \
    "counterbore too tight for the screw head once the bore roof droops"
assert strap_x0 >= wall_x + 0.5, "strap would sit on the case's -X wall"
assert strap_z + screw_d / 2 < leg_w, "screw hole breaks out of the strap"


def profile(tilt):
    """Return (points, info) for the leg profile at the given lean-back angle.

    Leg coordinates: x runs up the mounting face, y away from the case. The
    desk plane is the line y = x / tan(tilt) through the origin, so material
    must satisfy y <= x / tan(tilt) - the toe at (0, 0) is the near contact.
    """
    s, c = math.sin(math.radians(tilt)), math.cos(math.radians(tilt))

    # Desk plane: the lowest case corner, once tilted, clears it by
    # desk_clear + lift.
    v_min = min(cy * c - cz * s for (cy, cz) in case_corners)
    face_y0 = (v_min - desk_clear - lift + FACE_Z0 * s) / c

    # unit vectors: along the desk, and perpendicular into the material
    d = (s, c)
    n = (c, -s)

    def pt(u, off):
        """Point u along the desk from the toe, off mm in off the desk face."""
        return (u * d[0] + off * n[0], u * d[1] + off * n[1])

    x_screw_lo = screw_ys[0] - face_y0
    x_screw_hi = screw_ys[1] - face_y0
    x_top = x_screw_hi + strap_end

    # Where the strap steps down to its thin section. Two independent limits:
    # it must be clear of the plug band, and it must not run into the lower
    # screw's counterbore (a step under a counterbore gives it a split floor).
    x_step = min(port_keep_y - face_y0,
                 x_screw_lo - cbore_d / 2 - 2.0)

    # Strut: out along the desk to the tip, in by the thin thickness, back
    # along the thin inner edge, chamfer out to the full thickness, then back
    # to where the inner edge meets the thick strap at y = strap_t_thick.
    u_join = (strap_t_thick + foot_t * s) / c
    p_join = pt(u_join, foot_t)

    pts = [
        (0.0, 0.0),                                 # toe
        pt(foot_len, 0.0),                          # tip, on the desk
        pt(foot_len, foot_t_thin),                  # tip, inner face
        pt(foot_step, foot_t_thin),                 # end of the thin section
        pt(foot_step - step_chamfer, foot_t),       # start of the chamfer
        p_join,
        (x_step - step_chamfer, strap_t_thick),
        (x_step, strap_t_thin),
        (x_top, strap_t_thin),
        (x_top, 0.0),
    ]
    # Largest fillet that fits at the strut root. The corner has TWO legs and
    # the radius is limited by the shorter: along the thick strap to the start
    # of its step chamfer, and along the strut's inner edge to the start of its
    # chamfer. Only the strap side used to be checked - it was the tighter of
    # the two until the strap grew, after which the strut side silently became
    # binding and OCC failed the fillet outright at 30 deg.
    # 0.9 keeps the tangent point off the vertex.
    run_strap = (x_step - step_chamfer) - p_join[0]
    run_strut = (foot_step - step_chamfer) - u_join
    run = min(run_strap, run_strut)
    r_join = min(join_fillet,
                 0.9 * run * math.tan(math.radians(90.0 - tilt) / 2))

    info = dict(face_y0=face_y0, x_step=x_step, x_top=x_top,
                x_screw_lo=x_screw_lo, x_screw_hi=x_screw_hi,
                p_join=p_join, r_join=r_join, u_join=u_join, s=s, c=c)
    return pts, info


def check(pts, info, tilt):
    """Numeric checks on the profile. Returns a one-line report."""
    s, c, face_y0 = info["s"], info["c"], info["face_y0"]
    poly = Polygon(pts)
    assert poly.is_valid, "profile self-intersects"

    # --- 1. plug band: no material may reach past port_keep_y in case Y ---
    band = shapely_box(-1e3, plug_z0 - FACE_Z0, 1e3, plug_z1 - FACE_Z0)
    inband = poly.intersection(band)
    if inband.is_empty:
        worst_y = -1e9
    else:
        worst_y = face_y0 + max(x for x, _ in inband.exterior.coords)
    assert worst_y <= port_keep_y, (
        f"stand reaches case Y {worst_y:.2f} inside the plug band "
        f"(limit {port_keep_y:.2f}) at {tilt} deg")

    # --- 2. the profile must stay on the case side of the desk plane ---
    for (x, y) in pts:
        assert y <= x / math.tan(math.radians(tilt)) + 1e-6, \
            f"point ({x:.2f}, {y:.2f}) is below the desk at {tilt} deg"

    # --- 3. strap geometry ---
    assert info["p_join"][0] + 2.0 < info["x_step"] - step_chamfer, \
        "chamfer eats back into the strut root - no flat thick strap left"
    assert info["r_join"] >= 1.0, \
        f"only room for a {info['r_join']:.2f}mm fillet at the strut root"
    # the strut's own chamfer must start outboard of where it meets the strap,
    # or the two transitions collide and the root loses its full section
    assert foot_step - step_chamfer > info["u_join"] + 2.0, \
        (f"strut chamfer starts at u {foot_step - step_chamfer:.2f}, too close "
         f"to the strap junction at u {info['u_join']:.2f}")
    assert foot_step + 2.0 < foot_len, "strut thins too near its tip"
    assert info["x_step"] < info["x_screw_lo"] - cbore_d / 2 - 1.0, \
        "strap step runs into the lower counterbore"
    assert info["x_screw_hi"] + cbore_d / 2 + 1.0 < info["x_top"], \
        "upper counterbore breaks out of the strap's end"
    assert strap_z + cbore_d / 2 + 1.0 < leg_w, \
        "counterbore breaks out of the strap's outboard edge"
    assert face_y0 + info["x_top"] <= 38.0, "strap runs off the case_bottom plate"

    # --- 4. desk clearance and tipping, in world coords ---
    def world_h(cy, cz):
        return cy * s + cz * c

    v_min = min(cy * c - cz * s for (cy, cz) in case_corners)
    clear = v_min - (face_y0 * c - FACE_Z0 * s)
    assert abs(clear - (desk_clear + lift)) < 1e-6, \
        "desk clearance derivation is wrong"

    m_tot = sum(m for (m, _, _) in masses)
    com_h = sum(m * world_h(cy, cz) for (m, cy, cz) in masses) / m_tot
    h_front = world_h(face_y0, FACE_Z0)
    h_back = h_front + foot_len
    assert h_front + 5.0 < com_h < h_back - 5.0, \
        f"tips over at {tilt} deg: CoM {com_h:.1f} vs feet {h_front:.1f}..{h_back:.1f}"

    return (f"face_y0 {face_y0:6.2f}, r_join {info['r_join']:4.2f}, "
            f"step at x {info['x_step']:5.2f} "
            f"(case Y {face_y0 + info['x_step']:6.2f}), "
            f"plug gap {port_keep_y - worst_y + port_margin:5.2f}, "
            f"tip margins {com_h - h_front:5.1f} fore / {h_back - com_h:5.1f} aft")


def _bore(x, dia, y0, y1):
    """A cylinder along +y (out of the mounting face), on the screw axis.

    On an XZ workplane a POSITIVE extrude runs toward -Y, so the length is
    negated to grow away from the case. The bounding box is asserted below
    rather than trusted - this sign has bitten the project before.
    """
    return (
        cq.Workplane("XZ")
        .circle(dia / 2)
        .extrude(-(y1 - y0))
        .translate((x, y0, strap_z))
    )


def _cbore(x, y0, y1):
    """Counterbore, opened out through the strap's INBOARD edge.

    The screw axis is only 2.85mm from that edge, so a plain circular
    counterbore would leave a 0.15mm fin standing 2mm tall - it would simply
    break off. Running the pocket out to the edge instead gives a clean slot;
    the head still lands on the full 1mm floor, and the through-hole is what
    locates the screw laterally in any case.
    """
    circle = _bore(x, cbore_d, y0, y1)
    mouth = (
        cq.Workplane("XZ")
        .rect(cbore_d, strap_z + 1.0, centered=(True, False))
        .extrude(-(y1 - y0))
        .translate((x, y0, -1.0))
    )
    return circle.union(mouth)


_bb = _bore(10.0, 4.0, 1.0, 5.0).val().BoundingBox()
assert abs(_bb.ymin - 1.0) < 1e-6 and abs(_bb.ymax - 5.0) < 1e-6, \
    "bore extruded the wrong way in Y"
assert abs(_bb.zmin - (strap_z - 2.0)) < 1e-6, "bore is not on the screw axis"
# and the same thing stated in CASE coordinates, which is where it went wrong
assert abs((strap_x0 + strap_z) - disp_span_x / 2) < 1e-9, \
    "screw hole does not land on the case screw"


def build(tilt):
    pts, info = profile(tilt)
    report = check(pts, info, tilt)
    leg = (
        cq.Workplane("XY")
        .polyline(pts).close()
        .extrude(leg_w)
    )

    # Fillet before cutting: filleting edges created by a cut tends to fail.
    jx, jy = info["p_join"]
    leg = leg.edges(
        cq.NearestToPointSelector((jx, jy, leg_w / 2))
    ).fillet(info["r_join"])

    # Screw holes, run from the mounting face out through the strap. The
    # counterbore is cut from the outer face inward, so the head lands on its
    # floor. Both bores are horizontal in print orientation and their roofs
    # will droop a little - hence cbore_d carrying +0.2 over the head.
    for x in (info["x_screw_lo"], info["x_screw_hi"]):
        leg = leg.cut(_bore(x, screw_d, -1.0, strap_t_thin + 1.0))
        leg = leg.cut(_cbore(x, strap_t_thin - cbore_depth, strap_t_thin + 1.0))

    bb = leg.val().BoundingBox()
    return leg, (f"tilt {tilt:.0f} deg: {bb.xlen:.1f} x {bb.ylen:.1f} x "
                 f"{bb.zlen:.1f}mm, {report}")


# ============================================================
# EXPORT
# ============================================================
print(f"stand v{VERSION}: strap {strap_t_thin}mm across the port band "
      f"(clears the plugs by {plug_z0 - FACE_Z0 - strap_t_thin:.2f}mm), "
      f"{strap_t_thick}mm past it; strut {foot_len}mm long, {foot_t}mm at the "
      f"root stepping to {foot_t_thin}mm past u{foot_step}; "
      f"width {leg_w}mm at case X {strap_x0}..{strap_x1}; "
      f"screw head tops at Z {head_z:.2f} vs plugs at {plug_z0}")
# The two stands are HANDED. The screw axis sits 2.85mm from the strap's
# inboard edge and 11.15mm from its outboard one, so the -X stand is a mirror
# image - and an L-shaped profile has no mirror symmetry in either axis, so no
# rotation can stand in for it. (v1.1.0 appeared to need only one part; that
# was purely an artefact of the bores being wrongly centred.)
for t in tilts:
    solid, line = build(t)
    mirrored = solid.mirror("XY").translate((0, 0, leg_w))

    _m = mirrored.val().BoundingBox()
    assert abs(_m.zmin) < 1e-6 and abs(_m.zmax - leg_w) < 1e-6, \
        "mirrored stand did not land back in 0..leg_w"

    for name, part in ((f"stand_{int(t)}_usb.stl", solid),
                       (f"stand_{int(t)}_dsi.stl", mirrored)):
        cq.exporters.export(part, name, tolerance=0.01, angularTolerance=0.1)
    print(f"  stand_{int(t)}_usb/_dsi.stl: {line}")
