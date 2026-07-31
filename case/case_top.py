"""Ventilated lid (case-top) for the Touch Display 2 (5") stargazing case.

Remix of RonnyS's "Raspberry Pi Touch Display 2 Case" (Printables 1377047,
CC-BY), re-worked for the 5" panel and a Raspberry Pi 4 or Pi 5.

The lid continues the case-bottom's wall profile upward: its skirt has the same
footprint as that wall and seats on top of it, so the two form one continuous
side. It is retained by four M2.5 screws that pass through the top face into
M2.5 male-female standoffs, which in turn screw into the extenders through the
Pi's own mounting holes (58 x 49). There are therefore NO lid towers and NO
heat-set inserts - one screw chain does the whole stack.

That chain is long and compliant, though (extender -> Pi -> standoff), so the
screws alone locate the lid poorly and it could slide sideways on its seat.
Four blind SOCKETS in the skirt take spigots standing on the case-bottom's wall
and carry the sideways load instead. The pads that house them are the only
places the footprint departs from the wall below.

Port apertures are the upper half of an opening whose lower half is the gap in
the case-bottom's wall; both halves are derived from pi_models.py so they
cannot drift apart. On the +X face there is one window per connector rather
than a single span, matching the dividers in the wall below.

MODELLED IN ASSEMBLY COORDINATES (Z = 0 at the shell back plate's outer face,
+Z rearward) and flipped to print orientation only at export - the outer face
ends up on the bed. Modelling in print orientation previously meant mirroring
every side feature by hand, which is how the port apertures ended up on the
wrong side once already.

Stack: Pi PCB top 7.4 | standoff 20 -> lid inner face 27.4 | outer face 30.4
"""

import sys

import cadquery as cq
import pi_models as pm

VERSION = "0.6.0"

# Which board this lid is cut for; "python case_top.py pi5" for the other.
PI_MODEL = sys.argv[1] if len(sys.argv) > 1 else "pi4"
assert PI_MODEL in pm.PI_MODELS, f"unknown model {PI_MODEL}"

# ============================================================
# PARAMETERS - all mm, assembly coordinates.
# ============================================================
# --- Footprint: MUST match case_bottom's wall (it seats on it) ---
out_x0, out_x1 = -48.5, 46.5    # = case_bottom wall_x0 / wall_x1
out_hy = 32.0                   # = case_bottom wall_hy
in_x0, in_x1 = -46.0, 44.0      # = case_bottom bay_x0 / bay_x1
in_hy = 29.5                    # = case_bottom bay_hy
out_r, in_r = 5.5, 3.0
wall_t = 2.5                    # = case_bottom wall_t

# --- Heights ---
z_skirt = 10.5        # case_bottom wall top - the lid seats here
standoff = 20.0       # M2.5 male-female standoff on top of the Pi
pi_top = 7.4
top_t = 3.0           # top face thickness (thick enough to counterbore)

# --- Lid screws -> standoffs (the Pi's own 58 x 49 pattern) ---
ext_span_x, ext_span_y = 58.0, 49.0
ext_off_x, ext_off_y = -8.7, 0.0    # measured; must match case_bottom
screw_d = 2.9         # M2.5 clearance
cbore_d = 5.2
cbore_depth = 1.5

# --- Port apertures (upper half; lower half is the case-bottom wall gap) ---
port_clear = 0.6      # each side of a connector, in the wall plane
port_clear_z = 0.8    # above a connector
port_margin = 1.7     # around the whole -Y port group  } must match
min_divider = 1.8     # thinnest acceptable divider     } case_bottom
# A window stops short of the roof to leave a lintel. Where that lintel would
# come out thinner than this, the window is taken all the way up instead - a
# 1.5mm lintel spanning a 16mm connector is worse than no lintel at all.
min_lintel = 2.0

# --- Lid locating spigots: sockets over case_bottom's pins ---
spigot_x = (-40.0, 31.0)        # must match case_bottom
spigot_d = 3.0
spigot_h = 3.0
spigot_fit = 0.25               # radial clearance, pin to socket
pad_len = 7.0
pad_t = 6.5           # 1.5mm of wall either side of the socket

# --- Fan grille + optional 40x40x10 fan on the inner face ---
grille_hole_d = 4.0
grille_pitch = 6.0
grille_r = 17.0
fan_span = 32.0
fan_thick = 10.0
fan_screw_d = 3.4
fan_cbore_d = 6.5
fan_cbore_depth = 2.0

# --- Passive vents in the -X and +Y skirts ---
vent_w = 3.0
vent_z0, vent_z1 = 14.0, 25.0
vent_pitch = 8.0
vent_n = 5

# ============================================================
# DERIVED
# ============================================================
z_inner = pi_top + standoff          # 27.4
z_outer = z_inner + top_t            # 30.4
height = z_outer - z_skirt           # 19.9

ex, ey = ext_span_x / 2, ext_span_y / 2
screws = [(ext_off_x + sx * ex, ext_off_y + sy * ey)
          for sx in (1, -1) for sy in (1, -1)]

fh = fan_span / 2
fan_holes = [(fh, fh), (-fh, fh), (fh, -fh), (-fh, -fh)]

_keepout = fan_cbore_d / 2 + grille_hole_d / 2 + 0.8
grille_pts = []
n = int(grille_r // grille_pitch) + 1
for i in range(-n, n + 1):
    for j in range(-n, n + 1):
        gx, gy = i * grille_pitch, j * grille_pitch
        if (gx * gx + gy * gy) ** 0.5 > grille_r:
            continue
        if any(((gx - fx) ** 2 + (gy - fy) ** 2) ** 0.5 < _keepout
               for fx, fy in fan_holes):
            continue
        grille_pts.append((gx, gy))

vent_offs = [(i - (vent_n - 1) / 2) * vent_pitch for i in range(vent_n)]

# port windows: (y0, y1, top) per +X connector
side_ports = pm.side_ports(PI_MODEL)
windows = []
for (_name, y0, y1, _z0, z1, _reach, _under) in side_ports:
    top = z1 + port_clear_z
    if top > z_inner - min_lintel:
        top = z_inner
    windows.append((y0 - port_clear, y1 + port_clear, top))

# material left standing between the windows (dividers) and at each end
edges = [-in_hy] + [v for w in windows for v in w[:2]] + [in_hy]
side_solids = [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2)]

bot_x0, bot_x1 = pm.bottom_span(PI_MODEL)
pwr_x0 = bot_x0 - port_margin
pwr_x1 = bot_x1 + port_margin
pwr_z1 = max(e[4] for e in pm.bottom_ports(PI_MODEL)) + port_clear_z

socket_d = spigot_d + 2 * spigot_fit
socket_depth = spigot_h + 0.6
pad_cy = in_hy + pad_t / 2
sockets = [(px, sy * pad_cy) for px in spigot_x for sy in (1, -1)]

# guards
assert z_inner > pm.max_z(PI_MODEL) + 1.0, \
    f"lid inner face fouls the tallest part of the {pm.label(PI_MODEL)}"
for (_name, _y0, _y1, _z0, z1, _reach, _under), (_a, _b, top) in zip(side_ports,
                                                                     windows):
    assert top >= z1, "+X window is lower than its connector"
for (a, b) in side_solids:
    assert b - a >= min_divider, \
        f"+X divider/end wall only {b - a:.2f}mm wide (min {min_divider})"
assert pwr_z1 > max(e[4] for e in pm.bottom_ports(PI_MODEL)), \
    "-Y aperture is lower than the ports on that edge"
assert pwr_z1 > z_skirt, "-Y aperture does not reach the skirt seat"
assert cbore_depth < top_t - 1.0, "counterbore leaves too little top face"
for (sx, sy) in screws:
    assert in_x0 + 4 < sx < in_x1 - 4 and abs(sy) < in_hy - 4, \
        "lid screw falls outside the top face"
# the fan hangs off the inner face; it must clear the tallest thing beneath it
assert z_inner - fan_thick > pm.fan_zone_z(PI_MODEL), \
    "40mm fan would foul the GPIO header"
# spigot sockets: on the pads, clear of the -Y aperture, with material around
assert pad_t >= socket_d + 3.0, "too little material around a spigot socket"
assert socket_depth + 1.0 < height, "spigot socket too deep for the skirt"
for px in spigot_x:
    assert (px - pad_len / 2 > pwr_x1 + 0.2 or px + pad_len / 2 < pwr_x0 - 0.2), \
        f"spigot pad at x={px} runs into the -Y aperture"
    for v in vent_offs:
        assert abs(px - v) > (pad_len + vent_w) / 2, \
            f"spigot pad at x={px} runs into a +Y vent"

# ============================================================
# MODEL  (assembly coordinates; flipped for printing at export)
# ============================================================
outer = (
    cq.Workplane("XY")
    .workplane(offset=z_skirt)
    .box(out_x1 - out_x0, 2 * out_hy, height, centered=(True, True, False))
    .edges("|Z").fillet(out_r)
    .translate(((out_x0 + out_x1) / 2, 0, 0))
)
# spigot pads: the same local outward thickening as the wall below
for (px, py) in sockets:
    outer = outer.union(
        cq.Workplane("XY").workplane(offset=z_skirt)
        .box(pad_len, pad_t, height, centered=(True, True, False))
        .translate((px, py, 0))
    )
inner = (
    cq.Workplane("XY")
    .workplane(offset=z_skirt - 1)
    .box(in_x1 - in_x0, 2 * in_hy, z_inner - z_skirt + 1,
         centered=(True, True, False))
    .edges("|Z").fillet(in_r)
    .translate(((in_x0 + in_x1) / 2, 0, 0))
)
lid = outer.cut(inner)

# +X apertures: one window per connector, dividers left between them
for (y0, y1, top) in windows:
    lid = lid.cut(
        cq.Workplane("XY")
        .workplane(offset=z_skirt - 1)
        .box(20.0, y1 - y0, top - z_skirt + 1, centered=(True, True, False))
        .translate((in_x1 + 10.0, (y0 + y1) / 2, 0))
    )

# -Y aperture: USB-C / micro-HDMI / audio or MIPI
lid = lid.cut(
    cq.Workplane("XY")
    .workplane(offset=z_skirt - 1)
    .box(pwr_x1 - pwr_x0, 20.0, pwr_z1 - z_skirt + 1,
         centered=(True, True, False))
    .translate(((pwr_x0 + pwr_x1) / 2, -(in_hy + 10.0), 0))
)

# blind sockets for the case-bottom's locating spigots
for (px, py) in sockets:
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=z_skirt - 0.5)
        .circle(socket_d / 2).extrude(socket_depth + 0.5)
        .translate((px, py, 0))
    )

# fan grille through the top face
for (gx, gy) in grille_pts:
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=z_inner - 1)
        .circle(grille_hole_d / 2).extrude(top_t + 2)
        .translate((gx, gy, 0))
    )

# fan screw holes, counterbored on the OUTER face
for (fx, fy) in fan_holes:
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=z_inner - 1)
        .circle(fan_screw_d / 2).extrude(top_t + 2)
        .translate((fx, fy, 0))
    )
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=z_outer - fan_cbore_depth)
        .circle(fan_cbore_d / 2).extrude(fan_cbore_depth + 1)
        .translate((fx, fy, 0))
    )

# lid screws -> standoffs, counterbored on the OUTER face
for (sx, sy) in screws:
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=z_inner - 1)
        .circle(screw_d / 2).extrude(top_t + 2)
        .translate((sx, sy, 0))
    )
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=z_outer - cbore_depth)
        .circle(cbore_d / 2).extrude(cbore_depth + 1)
        .translate((sx, sy, 0))
    )

# passive vents: -X skirt (spread along Y) and +Y skirt (spread along X)
for v in vent_offs:
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=vent_z0)
        .box(20.0, vent_w, vent_z1 - vent_z0, centered=(True, True, False))
        .translate((in_x0 - 10.0, v, 0))
    )
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=vent_z0)
        .box(vent_w, 20.0, vent_z1 - vent_z0, centered=(True, True, False))
        .translate((v, in_hy + 10.0, 0))
    )

# ============================================================
# EXPORT  (flip to print orientation: outer face down on the bed)
# ============================================================
printable = lid.rotate((0, 0, 0), (0, 1, 0), 180).translate((0, 0, z_outer))
out = f"case_top_{PI_MODEL}.stl"
cq.exporters.export(printable, out, tolerance=0.01, angularTolerance=0.1)
print(f"case_top v{VERSION} [{PI_MODEL}]: wrote {out}")
print(f"  {out_x1-out_x0:.0f} x {2*out_hy:.0f} x {height:.1f}mm "
      f"({2*(out_hy + pad_t):.0f} deep over the spigot pads), seats at "
      f"Z{z_skirt}, inner face Z{z_inner} "
      f"({z_inner - pm.max_z(PI_MODEL):.2f}mm over the board)")
print("  +X windows: " + ", ".join(
    f"y{a:.1f}..{b:.1f} to z{t:.1f}" for a, b, t in windows))
print("  dividers/end walls: "
      + ", ".join(f"{b - a:.2f}" for a, b in side_solids) + "mm")
print(f"  -Y aperture {pwr_x0:.2f}..{pwr_x1:.2f} to z{pwr_z1:.1f}; "
      f"{len(grille_pts)} grille holes; sockets Ø{socket_d:.2f}")
_cool = pm.cooler_fan_zone_z(PI_MODEL)
if _cool is not None and z_inner - fan_thick < _cool:
    print(f"  NOTE: the active cooler reaches z{_cool:.2f} but the optional "
          f"40mm fan sits at z{z_inner - fan_thick:.2f} - fit one or the other")
