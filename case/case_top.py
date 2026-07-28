"""Ventilated lid (case-top) for the Touch Display 2 (5") stargazing case.

Remix of RonnyS's "Raspberry Pi Touch Display 2 Case" (Printables 1377047,
CC-BY), re-worked for the 5" panel + Raspberry Pi 4.

The lid closes the rear of the Pi compartment: its skirt seats on the
case-bottom's perimeter wall (8mm plane) and its four internal corner bosses
land on the lid towers (23mm plane); M3x16 cap screws pass through
counterbores into the towers' heat-set inserts. Openings:
  - +X skirt: USB / Ethernet aperture (connectors protrude slightly)
  - -Y skirt: USB-C power / 2x micro-HDMI / audio aperture
  - top face: fan grille (hole array) over the 40mm fan position
  - -X / +Y skirts: passive vent slots

MODELLED IN PRINT ORIENTATION: top face down on the bed at Z=0, skirt
rising +Z. In the assembly this part is ROTATED 180 deg ABOUT THE Y AXIS
(assembly x = -print x, assembly z = 32 - print z, y unchanged). So
side features are placed MIRRORED IN X here: the USB/Ethernet aperture
(assembly +X) is modelled at -X; the passive vents (assembly -X) at +X.
The -Y power aperture and symmetric features are unaffected.
No supports: port/vent apertures are open-ended toward the skirt edge.

Stack-up (assembly Z from the case-bottom plate top):
  wall top 8.0 | tower top 23.0 | Pi PCB top ~5.1 | USB cans to ~21.1 |
  fan top ~26 | lid underside 29.5 | lid outer face 32.0
"""

import cadquery as cq

VERSION = "0.4.0"

# ============================================================
# PARAMETERS - all mm.  Print orientation: top face at Z=0.
# ============================================================
# --- Footprint / heights ---
half_x = 53.0         # skirt outer; case-bottom X flanges stay exposed
half_y = 40.5
corner_r = 4.0
top_t = 2.5
height = 24.0         # total part height = assembly 8..32
skirt_t = 2.5

# --- Corner bosses -> case-bottom towers (M3 x 16 cap screws) ---
tower_x = 46.0        # must match case_bottom.py
tower_y = 33.5
boss_d = 8.0
boss_h = 6.5          # print Z 2.5..9  (assembly 23..29.5)
screw_hole_d = 3.4    # M3 clearance
cbore_d = 6.0         # cap head counterbore in the outer face
cbore_depth = 3.0

# --- +X aperture: USB / Ethernet ---
usb_hy = 26.5         # half-span in Y
usb_z0 = 10.0         # print Z (assembly: cans end ~21.1 -> print 10.9)

# --- -Y aperture: USB-C / HDMI / audio ---
# Pi board now spans x -41.2..43.8 (measured standoff offset), so the -Y ports
# sit at: USB-C -30.0, HDMI0 -15.2, HDMI1 -1.7, audio 12.8
pwr_x0, pwr_x1 = -36.0, 18.0
pwr_z0 = 19.0         # print Z (assembly 8..13 covers ports at 5.1..11.6
                      # together with the case-bottom wall gap below 8)

# --- Fan grille (40mm fan centred on the extender pattern = origin) ---
grille_hole_d = 4.0
grille_pitch = 6.0
grille_r = 17.0       # holes kept within this radius

# --- Fan mounting (40x40x10, OPTIONAL) ---
# The fan hangs straight off the lid's inner face (assembly Z 19.5..29.5),
# clearing the Pi's GPIO header by 3.6mm. RonnyS's separate Pi-mounted plate
# is not used here: on the 5" stack a plate + fan leaves only ~1.1mm of total
# slack between the header and the lid, which is too tight for FDM.
# Screws go in from OUTSIDE, through the lid, self-tapping into the fan frame.
fan_span = 32.0       # 40mm fan screw pattern
fan_screw_d = 3.4     # M3 clearance
fan_cbore_d = 6.5     # head counterbore in the outer face
fan_cbore_depth = 2.0

# --- Vent slots on the closed skirts ---
vent_w = 3.0
vent_z0, vent_z1 = 8.0, 20.0   # print Z
vent_pitch = 8.0
vent_n_left = 5       # -X skirt (slots spread along Y)
vent_n_top = 5        # +Y skirt (slots spread along X)

# ============================================================
# DERIVED
# ============================================================
bosses = [(tower_x, tower_y), (-tower_x, tower_y),
          (tower_x, -tower_y), (-tower_x, -tower_y)]

fh = fan_span / 2
fan_holes = [(fh, fh), (-fh, fh), (fh, -fh), (-fh, -fh)]

# grille: a circular field of holes, minus any that the fan screw
# counterbores would break into (the diagonal corners are the tight ones)
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

vent_left_ys = [(i - (vent_n_left - 1) / 2) * vent_pitch
                for i in range(vent_n_left)]
vent_top_xs = [(i - (vent_n_top - 1) / 2) * vent_pitch
               for i in range(vent_n_top)]

# guards
for (bx, by) in bosses:
    assert abs(bx) + boss_d / 2 < half_x - skirt_t + 0.6, "boss hits skirt X"
    assert abs(by) + boss_d / 2 < half_y - skirt_t + 0.6, "boss hits skirt Y"
assert usb_hy + 1 < half_y - skirt_t, "USB aperture reaches the corners"
# fan screws must not break into the grille holes
_gap = min(((fx - gx) ** 2 + (fy - gy) ** 2) ** 0.5
           for fx, fy in fan_holes for gx, gy in grille_pts)
assert _gap > fan_cbore_d / 2 + grille_hole_d / 2 + 0.8, \
    "fan screw counterbore breaks into a grille hole"

# ============================================================
# MODEL  (print orientation: outer top face down at Z=0)
# ============================================================
outer = (
    cq.Workplane("XY")
    .box(2 * half_x, 2 * half_y, height, centered=(True, True, False))
    .edges("|Z").fillet(corner_r)
)
inner = (
    cq.Workplane("XY")
    .workplane(offset=top_t)
    .box(2 * (half_x - skirt_t), 2 * (half_y - skirt_t), height,
         centered=(True, True, False))
    .edges("|Z").fillet(max(0.5, corner_r - skirt_t))
)
lid = outer.cut(inner)

# corner bosses down to the towers, then screw holes + counterbores
lid = lid.union(
    cq.Workplane("XY")
    .workplane(offset=top_t)
    .pushPoints(bosses)
    .circle(boss_d / 2)
    .extrude(boss_h)
)
for (cx, cy) in bosses:
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=-1)
        .circle(screw_hole_d / 2).extrude(top_t + boss_h + 2)
        .translate((cx, cy, 0))
    )
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=-1)
        .circle(cbore_d / 2).extrude(cbore_depth + 1)
        .translate((cx, cy, 0))
    )

# USB / Ethernet aperture: assembly +X = print -X (Y-axis flip)
lid = lid.cut(
    cq.Workplane("XY").workplane(offset=usb_z0)
    .box(skirt_t + 4, 2 * usb_hy, height, centered=(True, True, False))
    .translate((-(half_x - skirt_t / 2), 0, 0))
)

# -Y aperture (USB-C / HDMI / audio); X-span mirrored for the flip
lid = lid.cut(
    cq.Workplane("XY").workplane(offset=pwr_z0)
    .box(pwr_x1 - pwr_x0, skirt_t + 4, height, centered=(True, True, False))
    .translate((-(pwr_x0 + pwr_x1) / 2, -(half_y - skirt_t / 2), 0))
)

# fan grille through the top face
for (gx, gy) in grille_pts:
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=-1)
        .circle(grille_hole_d / 2).extrude(top_t + 2)
        .translate((gx, gy, 0))
    )

# fan screw holes + counterbores in the outer face (the bed side, Z=0)
for (fx, fy) in fan_holes:
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=-1)
        .circle(fan_screw_d / 2).extrude(top_t + 2)
        .translate((fx, fy, 0))
    )
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=-1)
        .circle(fan_cbore_d / 2).extrude(fan_cbore_depth + 1)
        .translate((fx, fy, 0))
    )

# vent slots: assembly -X = print +X skirt (along Y), and +Y skirt (along X)
for vy in vent_left_ys:
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=vent_z0)
        .box(skirt_t + 4, vent_w, vent_z1 - vent_z0,
             centered=(True, True, False))
        .translate((half_x - skirt_t / 2, vy, 0))
    )
for vx in vent_top_xs:
    lid = lid.cut(
        cq.Workplane("XY").workplane(offset=vent_z0)
        .box(vent_w, skirt_t + 4, vent_z1 - vent_z0,
             centered=(True, True, False))
        .translate((vx, half_y - skirt_t / 2, 0))
    )

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(lid, "case_top.stl", tolerance=0.01, angularTolerance=0.1)
print(f"case_top v{VERSION}: {2*half_x:.0f} x {2*half_y:.0f} x {height:.0f}mm, "
      f"{len(grille_pts)} grille holes, bosses at (+-{tower_x}, +-{tower_y}), "
      f"fan screws at +-{fh:.0f} (clearance to grille {_gap:.1f}mm)")
