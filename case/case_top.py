"""Ventilated lid (case-top) for the Touch Display 2 (5") stargazing case.

Remix of RonnyS's "Raspberry Pi Touch Display 2 Case" (Printables 1377047,
CC-BY), re-worked for the 5" panel + Raspberry Pi 4.

The lid continues the case-bottom's wall profile upward: its skirt has the same
footprint as that wall and seats on top of it, so the two form one continuous
side. It is retained by four M2.5 screws that pass through the top face into
M2.5 male-female standoffs, which in turn screw into the extenders through the
Pi's own mounting holes (58 x 49). There are therefore NO lid towers and NO
heat-set inserts - one screw chain does the whole stack.

Port apertures are the upper half of an opening whose lower half is the gap in
the case-bottom's wall; the two must agree in X.

MODELLED IN ASSEMBLY COORDINATES (Z = 0 at the shell back plate's outer face,
+Z rearward) and flipped to print orientation only at export - the outer face
ends up on the bed. Modelling in print orientation previously meant mirroring
every side feature by hand, which is how the port apertures ended up on the
wrong side once already.

Stack: Pi PCB top 7.4 | standoff 20 -> lid inner face 27.4 | outer face 30.4
"""

import cadquery as cq

VERSION = "0.5.0"

# ============================================================
# PARAMETERS - all mm, assembly coordinates.
# ============================================================
# --- Footprint: MUST match case_bottom's wall (it seats on it) ---
out_x0, out_x1 = -48.5, 46.5    # = case_bottom wall_x0 / wall_x1
out_hy = 32.0                   # = case_bottom wall_hy
in_x0, in_x1 = -46.0, 44.0      # = case_bottom bay_x0 / bay_x1
in_hy = 29.5                    # = case_bottom bay_hy
out_r, in_r = 5.5, 3.0

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
usb_hy = 26.5         # +X face: USB / Ethernet, half-span in Y
usb_z1 = 25.0         # top of the aperture (USB cans reach 23.4)
pwr_x0, pwr_x1 = -36.0, 18.0    # -Y face: MUST match case_bottom gap_bottom_*
pwr_z1 = 15.0         # micro-HDMI / USB-C reach ~13.5

# --- Fan grille + optional 40x40x10 fan on the inner face ---
grille_hole_d = 4.0
grille_pitch = 6.0
grille_r = 17.0
fan_span = 32.0
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

# guards
assert z_inner > 23.4 + 1.0, "lid inner face fouls the USB connector cans"
assert usb_z1 > 23.4, "USB aperture is lower than the USB cans"
assert pwr_z1 > 13.5, "power aperture is lower than the micro-HDMI ports"
assert cbore_depth < top_t - 1.0, "counterbore leaves too little top face"
for (sx, sy) in screws:
    assert in_x0 + 4 < sx < in_x1 - 4 and abs(sy) < in_hy - 4, \
        "lid screw falls outside the top face"
# the fan hangs off the inner face; it must clear the Pi's GPIO header (15.9)
assert z_inner - 10.0 > 15.9, "40mm fan would foul the GPIO header"

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
inner = (
    cq.Workplane("XY")
    .workplane(offset=z_skirt - 1)
    .box(in_x1 - in_x0, 2 * in_hy, z_inner - z_skirt + 1,
         centered=(True, True, False))
    .edges("|Z").fillet(in_r)
    .translate(((in_x0 + in_x1) / 2, 0, 0))
)
lid = outer.cut(inner)

# +X aperture: USB / Ethernet. Open-ended downward to the skirt edge.
lid = lid.cut(
    cq.Workplane("XY")
    .workplane(offset=z_skirt - 1)
    .box(20.0, 2 * usb_hy, usb_z1 - z_skirt + 1, centered=(True, True, False))
    .translate((in_x1 + 10.0, 0, 0))
)

# -Y aperture: USB-C / micro-HDMI / audio
lid = lid.cut(
    cq.Workplane("XY")
    .workplane(offset=z_skirt - 1)
    .box(pwr_x1 - pwr_x0, 20.0, pwr_z1 - z_skirt + 1,
         centered=(True, True, False))
    .translate(((pwr_x0 + pwr_x1) / 2, -(in_hy + 10.0), 0))
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
cq.exporters.export(printable, "case_top.stl",
                    tolerance=0.01, angularTolerance=0.1)
print(f"case_top v{VERSION}: {out_x1-out_x0:.0f} x {2*out_hy:.0f} x "
      f"{height:.1f}mm, seats at Z{z_skirt}, inner face Z{z_inner}, "
      f"{len(grille_pts)} grille holes, screws on {ext_span_x}x{ext_span_y}")
