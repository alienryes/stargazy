"""Pi case-bottom for the Touch Display 2 (5") stargazing case.

Remix of RonnyS's "Raspberry Pi Touch Display 2 Case" (Printables 1377047,
CC-BY), re-worked for the 5" panel and a Raspberry Pi 4 or Pi 5.

The case-bottom stacks onto the shell's back plate. The Pi is NOT carried by
the case: the display's built-in 15.9mm standoffs (58 x 49) carry it, via
M2.5 6+6 male-female extenders that rise through the central bay and relay
the mount plane ~3.5mm above this part's plate. Structure (RonnyS style):
  - central open BAY: extenders, Pi underside, DSI ribbon fold and JST
    jumper all live here; no pass-through holes needed
  - perimeter WALL around the bay. On the -Y edge one gap spans the whole
    power/HDMI group. On the +X edge the wall is NOT one gap: a continuous
    SILL runs under the connectors and full-height DIVIDERS stand between
    them, so each connector gets its own opening. RonnyS does the same with
    the sill (his +X wall stops at z 9.1 against a 12.4 wall top) though not
    with the dividers.
    The lid seats on this wall and continues its profile upward; there are
    no lid towers - the lid is retained by M2.5 male-female standoffs that
    screw into the extenders through the Pi's own mounting holes. Because
    that screw chain is long and compliant (extender -> Pi -> standoff), it
    locates the lid poorly, so four SPIGOTS on the wall top drop into blind
    sockets in the lid skirt and take the sideways load instead. RonnyS has
    no such feature: his lid bolts into towers rising from his own plate,
    which is short and stiff enough not to need one.
  - 103.7 x 51 clearance holes for the M2.5 case screws
    (here -> shell back -> display screw bosses). Those same four screws also
    bolt the two desk stands to the X flanges, so the flanges carry no
    features at all - the stands simply lie on the bare rear face. Nothing
    may protrude from the plate's FRONT face, which clamps against the
    shell's back plate.

Landscape: X = long axis, Y = short axis, centred on origin to match the
shell. Pi long edge along X; USB/Ethernet faces +X, power/HDMI faces -Y,
DSI faces -X. Local Z equals assembly Z (plate 0..2.5, wall top 10.5).

Print orientation: plate flat on the bed, wall up. No supports.
"""

import sys

import cadquery as cq
import pi_models as pm

VERSION = "0.16.0"

# Which board this plate is cut for; "python case_bottom.py pi5" for the other.
# The board outline and the 58 x 49 mount pattern are identical, so only the
# port openings differ.
PI_MODEL = sys.argv[1] if len(sys.argv) > 1 else "pi4"
assert PI_MODEL in pm.PI_MODELS, f"unknown model {PI_MODEL}"

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

# --- Raspberry Pi board (derived position, for clearance checks) ---
pi_w = pm.BOARD_W
pi_h = 2 * pm.BOARD_HY
pi_hole_inset = 3.5   # holes 3.5 from the DSI end and both long edges

# --- Display mount (case screws) ---
disp_span_x = 103.7
disp_span_y = 51.0
disp_hole_d = 2.9     # M2.5 clearance

# --- Base plate ---
base_t = 2.5
base_r = 3.0
# The X flanges reach past the lid skirt so the desk stands have somewhere to
# sit; stand.py's strap spans case X 49.0..63.0 and takes half_x as its
# outboard edge. This was briefly 64.5, to push the old snap-on legs clear of
# the case-screw heads they used to straddle; the bolt-on stands sit ON those
# screws, so it is back to 63.0 and plates printed before the stand work fit.
half_x = 63.0
half_y = 38.0

# --- Central bay ---
bay_x0 = -46.0        # ~5mm past the Pi's DSI edge so the ribbon can wrap
bay_x1 = 44.0         # just past the Pi's port end (43.8)
bay_hy = 29.5         # half-height; Pi long edges (+-28) overhang slightly
bay_r = 3.0

# --- Perimeter wall ---
wall_t = 2.5
wall_h = 8.0          # clears the Pi plane (~3.5 above plate) + lid seat

# --- Port openings (all derived from the measured table in pi_models.py) ---
port_clear = 0.6      # each side of a connector, in the wall plane
sill_clear = 0.35     # between the sill top and the lowest connector underside
port_margin = 1.7     # around the whole -Y port group
min_divider = 1.8     # thinnest acceptable divider or end wall

# --- Lid locating spigots ---
# Pads bulge OUTWARD on the +/-Y walls, into the 6mm of bare flange between
# the wall (32.0) and the plate edge (38.0). They cannot go on -X (the stand
# strap starts at x 49.0, only 0.5mm clear of the wall) or on +X (ports).
spigot_x = (-40.0, 31.0)
spigot_d = 3.0
spigot_h = 3.0
pad_len = 7.0         # along X
pad_t = 6.5           # total wall thickness at a pad, replacing wall_t. Sized
                      # by the LID's socket, not this pin: 6.5 leaves 1.5mm
                      # either side of a 3.5 socket, and that wall is what
                      # takes the sideways load.

# --- DSI FFC (for clearance checks; see shell.py) ---
# Display FFC at x ~= -35.2, i.e. ~2mm from the Pi 4's own DSI socket (-37.2) -
# but note it sits UNDER the Pi board (which starts at -41.2), so the ribbon
# rises through the bay, wraps around the board's DSI edge and folds back onto
# the socket on the top face. The bay extends ~5mm past that edge for the wrap.
# NOTE: the Pi 5 has no socket on that edge at all - its two 22-pin MIPI
# connectors are on the -Y long edge (x 6.7..15.2), so a Pi 5 build routes the
# ribbon along the top of the board instead. See case/README.md.
ffc_x = -35.2
ffc_hw = 3.0
ffc_hy = 9.0

# --- Desk stands (see stand.py) ---
# Nothing is modelled here for them. The stands bolt on with the four M2.5
# case screws and lie flat on this plate's bare rear face, so the only things
# this part owes them are a flat flange and the screw holes it already has.
stand_strap_x0 = 49.0

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

bay_w = bay_x1 - bay_x0
bay_cx = (bay_x0 + bay_x1) / 2
wall_x0, wall_x1 = bay_x0 - wall_t, bay_x1 + wall_t
wall_hy = bay_hy + wall_t
wall_top = base_t + wall_h                        # 10.5

# port openings
side_ports = pm.side_ports(PI_MODEL)
sill_z = pm.side_sill_z(PI_MODEL) - sill_clear    # top of the +X sill
bot_x0, bot_x1 = pm.bottom_span(PI_MODEL)
gap_bottom_x0 = bot_x0 - port_margin
gap_bottom_x1 = bot_x1 + port_margin

# the material left standing between +X openings: the two dividers, plus an
# end wall at each end of the port band
side_solids = []
edges = [-bay_hy] + [v for e in side_ports for v in (e[1] - port_clear,
                                                     e[2] + port_clear)] + [bay_hy]
for i in range(0, len(edges), 2):
    side_solids.append((edges[i], edges[i + 1]))

# spigot pads
pad_cy = bay_hy + pad_t / 2
spigots = [(px, sy * pad_cy) for px in spigot_x for sy in (1, -1)]

# guards
for (px, py) in ext_pts:
    assert bay_x0 + 3 < px < bay_x1 - 3 and abs(py) < bay_hy - 3, \
        "extender falls outside the bay"
assert bay_hy > pi_hy + 1.0, "wall would collide with the Pi long edges"
assert dmx > wall_x1 + disp_hole_d / 2, "case screw under the wall"
# the -Y wall gap and the lid's aperture form ONE opening: both are derived
# from bottom_span() so they cannot drift apart, but check the ports anyway
for (name, x0, x1, _z0, _z1, _reach) in pm.bottom_ports(PI_MODEL):
    assert gap_bottom_x0 < x0 and gap_bottom_x1 > x1, \
        f"-Y wall gap does not clear the {name} port"
# the bay must clear the FFC connector so the ribbon rises straight through
assert bay_x0 < ffc_x - ffc_hw - 1.0, "bay edge fouls the FFC connector"
assert ffc_hy < bay_hy, "FFC connector wider than the bay"
# +X: the sill must pass UNDER every connector, and every divider and end wall
# must be thick enough to print. (This replaces an old assertion that the +X
# wall must be fully open because the Pi PCB overhung the bay edge - it has not
# overhung since ext_off_x moved the board: its +X edge is 43.8 against a bay
# edge of 44.0. Only the CONNECTORS overhang, which is what these check.)
assert sill_z > base_t + 2.0, "no room for a port sill under the connectors"
for (name, _y0, _y1, _z0, _z1, _reach, under) in side_ports:
    assert sill_z < under, f"sill fouls the underside of {name}"
for (a, b) in side_solids:
    assert b - a >= min_divider, \
        f"+X divider/end wall only {b - a:.2f}mm wide (min {min_divider})"
assert bay_hy > pi_hy, "side walls foul the Pi long edges"
# the stands lie flat on this rear face, inboard edge clear of the lid skirt
# and outboard edge on the flange, with both case screws under the strap
assert stand_strap_x0 > wall_x1 and stand_strap_x0 > -wall_x0, \
    "stand strap would sit on the perimeter wall / lid skirt"
assert stand_strap_x0 < dmx < half_x, "case screw is not under the stand strap"
# spigot pads: on the flange, clear of the -Y port gap, clear of the case screws
assert bay_hy + pad_t < half_y - 1.0, "spigot pad overhangs the plate edge"
assert pad_t >= spigot_d + 3.0, "too little material around a spigot"
for px in spigot_x:
    if not (px - pad_len / 2 > gap_bottom_x1 + 0.2
            or px + pad_len / 2 < gap_bottom_x0 - 0.2):
        raise AssertionError(f"spigot pad at x={px} runs into the -Y port gap")
    assert abs(px) + pad_len / 2 < dmx - 3.0, "spigot pad reaches a case screw"

# ============================================================
# MODEL  (plate on the bed at Z=0, wall/spigots up +Z)
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

# perimeter wall = outer ring minus bay, with port openings cut out
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

# locating-spigot pads: local outward thickening of the +/-Y walls
for (px, py) in spigots:
    wall = wall.union(
        cq.Workplane("XY").workplane(offset=base_t)
        .box(pad_len, pad_t, wall_h, centered=(True, True, False))
        .translate((px, py, 0))
    )

# +X openings: one window per connector, above a continuous sill. The material
# left between them is the divider set checked by side_solids above.
for (_name, y0, y1, _z0, _z1, _reach, _under) in side_ports:
    wall = wall.cut(
        cq.Workplane("XY")
        .workplane(offset=sill_z)
        .box(wall_t + 4, (y1 - y0) + 2 * port_clear, wall_top - sill_z + 2,
             centered=(True, True, False))
        .translate((bay_x1 + wall_t / 2, (y0 + y1) / 2, 0))
    )

# -Y gap (USB-C / micro-HDMI / audio or MIPI): one opening for the whole group
wall = wall.cut(
    cq.Workplane("XY")
    .workplane(offset=base_t - 1)
    .box(gap_bottom_x1 - gap_bottom_x0, wall_t + 4, wall_h + 2,
         centered=(True, True, False))
    .translate(((gap_bottom_x0 + gap_bottom_x1) / 2, -(bay_hy + wall_t / 2), 0))
)
part = part.union(wall)

# locating spigots, standing on the pads
for (px, py) in spigots:
    part = part.union(
        cq.Workplane("XY").workplane(offset=wall_top)
        .circle(spigot_d / 2).extrude(spigot_h)
        .translate((px, py, 0))
    )

# display-mount clearance holes
for (cx, cy) in disp_mounts:
    part = part.cut(
        cq.Workplane("XY").workplane(offset=-1)
        .circle(disp_hole_d / 2).extrude(base_t + 2)
        .translate((cx, cy, 0))
    )

# ============================================================
# EXPORT
# ============================================================
out = f"case_bottom_{PI_MODEL}.stl"
cq.exporters.export(part, out, tolerance=0.01, angularTolerance=0.1)
print(f"case_bottom v{VERSION} [{PI_MODEL}]: wrote {out}")
print(f"  plate {2*half_x:.1f} x {2*half_y:.1f}, bay {bay_w:.0f} x {2*bay_hy:.0f}, "
      f"wall h{wall_h} (outer x {wall_x0:.1f}..{wall_x1:.1f}, y +-{wall_hy:.1f})")
print(f"  +X sill top z{sill_z:.2f}, openings/dividers: "
      + ", ".join(f"{b - a:.2f}" for a, b in side_solids) + "mm of wall left")
print(f"  -Y gap {gap_bottom_x0:.2f}..{gap_bottom_x1:.2f} "
      f"(ports {bot_x0:.2f}..{bot_x1:.2f})")
print(f"  spigots Ø{spigot_d} x {spigot_h} at "
      + ", ".join(f"({px:.0f},{py:+.1f})" for px, py in spigots))
