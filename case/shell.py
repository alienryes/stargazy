"""5" display shell for the Raspberry Pi Touch Display 2 stargazing case.

A remix of RonnyS's "Raspberry Pi Touch Display 2 Case"
(https://www.printables.com/model/1377047, CC-BY) re-worked for the 5"
Touch Display 2 (the original targets the 7" panel). Same architecture:
shallow tray + bolt-on Pi 4 clamshell housing + Y-leg desk stand.

This part is a shallow tray: a thin outer wall frames the panel (the panel's
own glass border is the visible bezel), and a BACK PLATE rests on the tips of
the display's four BUILT-IN Pi standoffs (the 15.9mm-deep towers, 58 x 49
pattern). Two fastening systems pass through the plate:
  - 58 x 49: M2.5 6+6 male-female extender standoffs screw through the plate
    into the built-in standoffs, clamping the plate and relaying the Pi mount
    plane rearward (the display carries the Pi, the case never does).
  - 103.7 x 51: M2.5 case screws (stand -> case-bottom -> here -> display).
    The display's screw bosses sit 5.5mm BELOW the standoff-tip plane
    (measured), so the plate carries internal bosses reaching 5.5mm down to
    seat on them.
The back plate keeps a central opening for the DSI FFC + power JST.

Display runs landscape (1280x720 content). Dimensions from the official RPi
Touch Display 2 mechanical drawing, 5" variant. See memory hw-touch-display2.

Print orientation: back plate DOWN on the bed, open front up - the back plate
is a clean first layer and the walls need no support.
"""

import cadquery as cq

VERSION = "0.11.0"

# ============================================================
# PARAMETERS - all mm. Landscape: X = 143.4 axis, Y = 91.46 axis.
# ============================================================
# --- 5" display module (portrait native 91.46 x 143.4, used landscape) ---
disp_w = 143.4        # long edge -> case X
disp_h = 91.46        # short edge -> case Y
disp_r = 5.0          # display outline corner radius (R5)
disp_depth = 15.9     # glass front to module back (excl. 0.7 lens)

# --- Active display area (landscape) - for clearance checks only ---
active_w = 110.4
active_h = 63.1

# --- Structure ---
wall = 3.0            # side wall thickness around the panel
back_t = 2.5          # back plate thickness
fit_clear = 0.5       # per-side clearance in the display pocket (PETG: PLA
                      # would be 0.4; PETG is stickier and prints slightly
                      # proud, so the pocket is opened up 0.1/side)

# --- Rear mounting: screws into the display's own 103.7 x 51 holes ---
mount_span_x = 103.7  # centre-to-centre along the long axis
mount_span_y = 51.0   # centre-to-centre along the short axis
mount_hole_d = 2.9    # M2.5 screw clearance
mount_boss_d = 7.0    # internal boss OD around each mount hole
mount_boss_reach = 5.5  # measured: screw bosses sit 5.5 below the standoff tips

# --- Built-in Pi standoffs (display's own, 15.9mm towers) ---
# The plate rests on their tips; M2.5 6+6 extenders screw through into them.
pi_span_x = 58.0      # Pi hole pattern along the landscape long axis
pi_span_y = 49.0      # Pi hole pattern along the landscape short axis
pi_off_x = -8.7       # MEASURED: standoffs 34mm from the DSI-end edge
pi_off_y = 0.0        # MEASURED: 21mm from each long edge, i.e. centred
pi_hole_d = 2.9       # clearance for the extender's M2.5 male thread

# --- Rear connector / clearance opening in the back plate ---
# Must stay clear of the mount holes so they keep solid material around them.
rear_open_w = 92.0
rear_open_h = 40.0
rear_open_r = 3.0

# --- DSI FFC position (for clearance checks) ---
# Portrait: horizontally centred, ~39mm up from the bottom edge. Landscape
# (connector edge at -X): x ~= -32.5, y ~= 0 - i.e. almost directly under the
# Pi's own DSI socket (x ~= -28.5), so the ribbon runs near-vertically and
# needs no notch; the main rear opening already clears it.
# VERIFY against the real panel before the first print.
ffc_x = -35.2
ffc_hw = 3.0          # connector half-depth along X
ffc_hy = 9.0          # connector half-length along Y

# ============================================================
# DERIVED
# ============================================================
pocket_w = disp_w + 2 * fit_clear      # 144.2
pocket_h = disp_h + 2 * fit_clear       # 92.26
pocket_r = disp_r + fit_clear           # 5.4
pocket_d = disp_depth + fit_clear       # 16.3 - panel sits on the back plate

out_w = disp_w + 2 * wall               # 149.4
out_h = disp_h + 2 * wall               # 97.46
out_r = wall + pocket_r                 # 8.4 - keeps the corner wall a true 3mm

total_d = back_t + pocket_d             # 18.8

mx, my = mount_span_x / 2, mount_span_y / 2      # 51.85, 25.5
mounts = [(mx, my), (-mx, my), (mx, -my), (-mx, -my)]

px, py = pi_span_x / 2, pi_span_y / 2            # 29, 24.5
pi_holes = [(pi_off_x + sx * px, pi_off_y + sy * py)
            for sx in (1, -1) for sy in (1, -1)]

# guards
assert pocket_w > active_w and pocket_h > active_h, "wall occludes active area"
assert mx < disp_w / 2 and my < disp_h / 2, "mount holes fall outside the panel"
assert mx > rear_open_w / 2 and my > rear_open_h / 2, \
    "rear opening swallows the mount holes - no material to screw into"
for (hx, hy) in pi_holes:
    assert abs(hx) > rear_open_w / 2 + pi_hole_d or \
           abs(hy) > rear_open_h / 2 + pi_hole_d, \
        "extender pass-through falls inside the rear opening"
assert mount_boss_reach < pocket_d, "mount boss deeper than the pocket"
# the rear opening must clear the DSI FFC connector outright
assert ffc_x - ffc_hw > -rear_open_w / 2 and ffc_x + ffc_hw < rear_open_w / 2 \
    and ffc_hy < rear_open_h / 2, \
    "rear opening does not clear the FFC connector - a notch is needed"

# ============================================================
# MODEL  (back plate at Z=0 on the bed, open front toward +Z)
# ============================================================
shell = (
    cq.Workplane("XY")
    .box(out_w, out_h, total_d, centered=(True, True, False))
    .edges("|Z").fillet(out_r)
)

# panel pocket cut from the front, leaving the back plate at the bottom
pocket = (
    cq.Workplane("XY")
    .workplane(offset=back_t)
    .box(pocket_w, pocket_h, pocket_d + 1, centered=(True, True, False))
    .edges("|Z").fillet(pocket_r)
)
shell = shell.cut(pocket)

# central rear opening through the back plate
rear = (
    cq.Workplane("XY")
    .workplane(offset=-1)
    .box(rear_open_w, rear_open_h, back_t + 2, centered=(True, True, False))
    .edges("|Z").fillet(rear_open_r)
)
shell = shell.cut(rear)

# internal bosses rising from the plate to reach the display's screw bosses
# (which sit 5.5mm shy of the standoff-tip plane the plate rests on)
bosses = (
    cq.Workplane("XY")
    .workplane(offset=back_t)
    .pushPoints(mounts)
    .circle(mount_boss_d / 2)
    .extrude(mount_boss_reach)
)
shell = shell.union(bosses)

# four M2.5 clearance holes through plate + boss
for (cx, cy) in mounts:
    hole = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .circle(mount_hole_d / 2)
        .extrude(back_t + mount_boss_reach + 2)
        .translate((cx, cy, 0))
    )
    shell = shell.cut(hole)

# pass-through holes for the M2.5 6+6 extender standoffs (built-in Pi
# standoff tips seat against the plate around these)
for (cx, cy) in pi_holes:
    hole = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .circle(pi_hole_d / 2)
        .extrude(back_t + 2)
        .translate((cx, cy, 0))
    )
    shell = shell.cut(hole)

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(shell, "shell.stl", tolerance=0.01, angularTolerance=0.1)
print(f"shell v{VERSION}: outer {out_w:.1f} x {out_h:.1f} x {total_d:.1f}mm, "
      f"rear opening {rear_open_w:.0f} x {rear_open_h:.0f}mm, "
      f"mounts {mount_span_x} x {mount_span_y}mm")
