"""Pi 4 case-bottom for the Touch Display 2 (5") stargazing case.

Remix of RonnyS's "Raspberry Pi Touch Display 2 Case" (Printables 1377047,
CC-BY), re-worked for the 5" panel + Raspberry Pi 4.

The case-bottom stacks onto the shell's back plate. The Pi is NOT carried by
the case: the display's built-in 15.9mm standoffs (58 x 49) carry it, via
M2.5 6+6 male-female extenders that rise through the central bay and relay
the mount plane ~3.5mm above this part's plate. Structure (RonnyS style):
  - central open BAY: extenders, Pi underside, DSI ribbon fold and JST
    jumper all live here; no pass-through holes needed
  - perimeter WALL around the bay with open gaps on the port edges
    (USB/Ethernet out the +X short edge, USB-C/HDMI/audio out the -Y edge).
    The lid seats on this wall and continues its profile upward; there are
    no lid towers - the lid is retained by M2.5 male-female standoffs that
    screw into the extenders through the Pi's own mounting holes.
  - 103.7 x 51 clearance holes for the M2.5 case screws
    (here -> shell back -> display screw bosses)
  - cleat ribs on the rear face of each X flange: the easel legs SNAP on,
    no screws. Two half-dovetail ribs capture each leg's lips and a detent
    bump latches it. Nothing may protrude from the plate's FRONT face, which
    clamps against the shell's back plate - so the whole interface lives on
    the rear face, where it also prints without supports.

Landscape: X = long axis, Y = short axis, centred on origin to match the
shell. Pi long edge along X; USB/Ethernet faces +X, power/HDMI faces -Y,
DSI faces -X. The Pi BOARD is offset +10mm in X relative to its own hole
pattern (holes sit 3.5mm from the DSI end, 23.5mm from the USB end).

Print orientation: plate flat on the bed, wall up. No supports.
"""

import cadquery as cq

VERSION = "0.10.0"

# ============================================================
# PARAMETERS - all mm.
# ============================================================
# --- Display's built-in Pi standoffs (the 15.9mm towers on the panel rear) ---
# The M2.5 6+6 extenders screw into these; the Pi then bolts to the extenders.
# NOT the 103.7 x 51 screw bosses below - those are a separate, lower pattern.
ext_span_x = 58.0     # pattern along the landscape long axis
ext_span_y = 49.0     # pattern along the landscape short axis
# MEASURED on the panel: along the long axis the standoffs are 34mm from the
# DSI-end edge and 51.5mm from the other (34 + 58 + 51.5 = 143.5 ~ 143.4); along
# the short axis both are 21mm from the edge (21 + 49 + 21 = 91 ~ 91.46), i.e.
# centred. So the pattern sits 8.7mm toward the DSI end in X.
ext_off_x = -8.7      # (-143.4/2 + 34) + 29
ext_off_y = 0.0       # centred within measurement tolerance

# --- Raspberry Pi 4 board (derived position, for clearance checks) ---
pi_w = 85.0
pi_h = 56.0
pi_hole_inset = 3.5   # holes 3.5 from the DSI end and both long edges

# --- Display mount (case screws) ---
disp_span_x = 103.7
disp_span_y = 51.0
disp_hole_d = 2.9     # M2.5 clearance
disp_head_d = 4.7     # M2.5 head OD - the legs must clear these, see below

# --- Base plate ---
base_t = 2.5
base_r = 3.0
half_x = 64.5         # X flanges reach past the lid skirt for the stand legs
half_y = 38.0

# --- Central bay ---
bay_x0 = -46.0        # ~5mm past the Pi's DSI edge so the ribbon can wrap
bay_x1 = 44.0         # just past the Pi's port end (43.8)
bay_hy = 29.5         # half-height; Pi long edges (+-28) overhang slightly
bay_r = 3.0

# --- Perimeter wall ---
wall_t = 2.5
wall_h = 8.0          # clears the Pi plane (~3.5 above plate) + lid seat
# port gaps (wall omitted): USB/Ethernet on +X, power/HDMI/audio on -Y
gap_right_hy = 29.5   # +X wall fully open: the Pi (y +-28) overhangs the bay
                      # edge here, so any wall would foul the PCB at Z 6..7.4
# -Y wall gap: must span USB-C (-30) .. audio (12.8) with margin. MUST match
# the lid's aperture - these two halves form one opening. Getting this wrong
# is what buried the power socket on the first print.
gap_bottom_x0 = -36.0
gap_bottom_x1 = 18.0
# --- DSI FFC (for clearance checks; see shell.py) ---
# Display FFC at x ~= -35.2, i.e. ~2mm from the Pi's own DSI socket (-37.2) -
# but note it sits UNDER the Pi board (which starts at -41.2), so the ribbon
# rises through the bay, wraps around the board's DSI edge and folds back onto
# the socket on the top face. The bay extends ~5mm past that edge for the wrap.
ffc_x = -35.2
ffc_hw = 3.0
ffc_hy = 9.0

# --- Stand-leg cleat interface (MUST match stand.py) ---
# The legs snap on. Two half-dovetail ribs per flange capture the leg's lips
# against pull-off; the leg slides UP (+Y) to engage, which is the direction
# the case's own weight drives it, so load seats the joint rather than
# working it loose. A detent bump then latches the leg against sliding back
# down when the case is lifted.
#
# cleat_x is set by the M2.5 case-screw HEADS at x = +-51.85: they stand off
# this same rear face and reach to x 54.2, so a leg starting at x 54 would
# rock on them. The flange therefore moved outboard (half_x 63 -> 64.5).
cleat_x = 59.5        # rib centre in X; the leg is 8mm wide -> x 55.5..63.5
cleat_len = 8.0       # rib length along X = leg width
cleat_span_y = 56.0   # spacing of the ribs' -Y base edges (the load faces)
rib_t = 3.0           # rib base thickness along Y
rib_h = 3.5           # rib height off the rear face
rib_flare = 2.0       # undercut at the top, toward -Y (30 deg from vertical:
                      # steep enough to print, shallow enough that the leg
                      # only lifts ~0.5mm off the face before the flares bite)
detent_y = 0.0        # detent bump apex in Y
detent_h = 1.2        # bump height; 45 deg faces both sides

# ============================================================
# DERIVED
# ============================================================
ex, ey = ext_span_x / 2, ext_span_y / 2
ext_pts = [(ext_off_x + sx * ex, ext_off_y + sy * ey)
           for sx in (1, -1) for sy in (1, -1)]

# Pi board outline from the hole pattern
pi_x0 = ext_off_x - ex - pi_hole_inset            # -32.5
pi_x1 = pi_x0 + pi_w                              # +52.5
pi_hy = pi_h / 2                                  # +-28 (pattern-centred in Y)
# Pi PCB sits on the 6mm extender bodies: Z 6.0..7.4 (wall top is 10.5)

dmx, dmy = disp_span_x / 2, disp_span_y / 2       # 51.85, 25.5
disp_mounts = [(dmx, dmy), (-dmx, dmy), (dmx, -dmy), (-dmx, -dmy)]

cleat_xs = (cleat_x, -cleat_x)
cleat_ys = (cleat_span_y / 2, -cleat_span_y / 2)   # rib -Y base edge = load face

bay_w = bay_x1 - bay_x0
bay_cx = (bay_x0 + bay_x1) / 2
wall_x0, wall_x1 = bay_x0 - wall_t, bay_x1 + wall_t
wall_hy = bay_hy + wall_t

# guards
for (px, py) in ext_pts:
    assert bay_x0 + 3 < px < bay_x1 - 3 and abs(py) < bay_hy - 3, \
        "extender falls outside the bay"
assert bay_hy > pi_hy + 1.0, "wall would collide with the Pi long edges"
assert dmx > wall_x1 + disp_hole_d / 2, "case screw under the wall"
# the -Y wall gap and the lid's aperture form ONE opening: it must span every
# port on that edge (USB-C at pi_x0+11.2 through audio at pi_x0+54)
assert gap_bottom_x0 < pi_x0 + 11.2 - 4 and gap_bottom_x1 > pi_x0 + 54 + 4, \
    "-Y wall gap does not span the power/HDMI/audio ports"
# the bay must clear the FFC connector so the ribbon rises straight through
assert bay_x0 < ffc_x - ffc_hw - 1.0, "bay edge fouls the FFC connector"
assert ffc_hy < bay_hy, "FFC connector wider than the bay"
# the Pi PCB (Z 6.0..7.4) passes over the +X bay edge, below the wall top,
# so no wall may remain within the Pi's footprint
assert gap_right_hy >= pi_hy, "+X wall fouls the Pi PCB corners"
assert bay_hy > pi_hy, "side walls foul the Pi long edges"
# the leg's mounting face lies on this rear face, so it must clear both the
# case-screw heads standing off it and the lid skirt seated inboard of it
assert cleat_x - cleat_len / 2 > dmx + disp_head_d / 2 + 0.5, \
    "stand leg would rock on the case-screw heads"
assert cleat_x - cleat_len / 2 > wall_x1 + 2.0, "stand leg fouls the lid skirt"
assert cleat_x + cleat_len / 2 < half_x - 0.5, "cleat rib overhangs the flange"
for _cy in cleat_ys:
    assert abs(_cy) + rib_t + 2.0 < half_y, "cleat rib runs off the plate"
assert -cleat_span_y / 2 - rib_flare < detent_y - detent_h and \
       cleat_span_y / 2 > detent_y + detent_h, "detent bump collides with a rib"

# ============================================================
# MODEL  (plate on the bed at Z=0, wall/towers up +Z)
# ============================================================
part = (
    cq.Workplane("XY")
    .box(2 * half_x, 2 * half_y, base_t, centered=(True, True, False))
    .edges("|Z").fillet(base_r)
)

# central bay
bay = (
    cq.Workplane("XY")
    .workplane(offset=-1)
    .box(bay_w, 2 * bay_hy, base_t + 2, centered=(True, True, False))
    .edges("|Z").fillet(bay_r)
    .translate((bay_cx, 0, 0))
)
part = part.cut(bay)

# perimeter wall = outer ring minus bay, with port gaps cut out
wall_outer = (
    cq.Workplane("XY")
    .workplane(offset=base_t)
    .box(wall_x1 - wall_x0, 2 * wall_hy, wall_h, centered=(True, True, False))
    .edges("|Z").fillet(bay_r + wall_t)
    .translate(((wall_x0 + wall_x1) / 2, 0, 0))
)
wall_inner = (
    cq.Workplane("XY")
    .workplane(offset=base_t - 1)
    .box(bay_w, 2 * bay_hy, wall_h + 2, centered=(True, True, False))
    .edges("|Z").fillet(bay_r)
    .translate((bay_cx, 0, 0))
)
wall = wall_outer.cut(wall_inner)

# +X gap (USB/Ethernet pass through the wall here)
gap_r = (
    cq.Workplane("XY")
    .workplane(offset=base_t - 1)
    .box(wall_t + 4, 2 * gap_right_hy, wall_h + 2, centered=(True, True, False))
    .translate((bay_x1 + wall_t / 2, 0, 0))
)
wall = wall.cut(gap_r)

# -Y gap (USB-C / HDMI / audio)
gap_b = (
    cq.Workplane("XY")
    .workplane(offset=base_t - 1)
    .box(gap_bottom_x1 - gap_bottom_x0, wall_t + 4, wall_h + 2,
         centered=(True, True, False))
    .translate(((gap_bottom_x0 + gap_bottom_x1) / 2, -(bay_hy + wall_t / 2), 0))
)
wall = wall.cut(gap_b)
part = part.union(wall)

# display-mount clearance holes
for (cx, cy) in disp_mounts:
    part = part.cut(
        cq.Workplane("XY").workplane(offset=-1)
        .circle(disp_hole_d / 2).extrude(base_t + 2)
        .translate((cx, cy, 0))
    )

# stand-leg cleat: two half-dovetail ribs + one detent bump per X flange.
# Each profile is drawn in (Y, Z-above-the-rear-face) and extruded along X, so
# every feature is prismatic in the print direction and the only overhang is
# the ribs' own 19 deg undercut.
def _flange_feature(pts, cx):
    return (
        cq.Workplane("YZ")
        .polyline([(y, base_t + z) for (y, z) in pts]).close()
        .extrude(cleat_len)
        .translate((cx - cleat_len / 2, 0, 0))
    )


def _rib_profile(cy):
    return [(cy, 0.0), (cy + rib_t, 0.0), (cy + rib_t, rib_h),
            (cy - rib_flare, rib_h)]


# catch a workplane sign flip before it reaches the STL: the rib must grow
# along +X from the flange, stand off the REAR face, and flare toward -Y.
_bb = _flange_feature(_rib_profile(cleat_ys[0]), cleat_x).val().BoundingBox()
assert abs(_bb.xmin - (cleat_x - cleat_len / 2)) < 1e-6, "rib extruded wrong in X"
assert abs(_bb.zmax - (base_t + rib_h)) < 1e-6, "rib is not on the rear face"
assert abs(_bb.ymin - (cleat_ys[0] - rib_flare)) < 1e-6, "flare points wrong in Y"

for cx in cleat_xs:
    for cy in cleat_ys:
        part = part.union(_flange_feature(_rib_profile(cy), cx))
    part = part.union(_flange_feature(
        [(detent_y - detent_h, 0.0), (detent_y + detent_h, 0.0),
         (detent_y, detent_h)], cx))

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(part, "case_bottom.stl", tolerance=0.01, angularTolerance=0.1)
print(f"case_bottom v{VERSION}: plate {2*half_x:.1f} x {2*half_y:.1f}, "
      f"bay {bay_w:.0f} x {2*bay_hy:.0f}, wall h{wall_h} "
      f"(outer x {wall_x0:.1f}..{wall_x1:.1f}, y +-{wall_hy:.1f}), "
      f"-Y gap {gap_bottom_x0:.0f}..{gap_bottom_x1:.0f}, "
      f"cleat ribs at x +-{cleat_x} y +-{cleat_span_y/2:.0f} h{rib_h}")
