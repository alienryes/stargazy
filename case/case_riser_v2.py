import math

import cadquery as cq

# ============================================================
# PARAMETERS - Edit these to customize the model
# ============================================================
VERSION = "3.0"        # case rev - 3.0 matches the LED-ring frame growth

# Overall dimensions - matches the Inky case frame footprint.
# Panel grown +4mm per side (from 117.6x89.5) to match the LED-ring frame
# (case_frame_v2.py v3.0). Screw holes, posts and base_width are unchanged -
# they are driven by the (unchanged) screw/PCB positions, not the panel size,
# so the mate to the frame is preserved. The end overhang just grows 10->14mm.
panel_width = 125.6    # mm - full frame width   [was 117.6]
panel_height = 97.5    # mm - full frame height (covers the frame's back face)  [was 89.5]
panel_thickness = 3.0  # mm - back panel thickness

base_depth = 20.0      # mm - depth of the flat foot resting on the table
corner_r = 2.0         # mm - fillet radius on panel corners, measured from inky_case_frame.stl
base_width = 97.6      # mm - base narrower than panel to expose lower screw holes (screw-driven, unchanged)

# Cable slot cut through the base (full Y depth, full Z thickness)
# Positioned to align with the cable slot on the frame
cable_slot_x_left  = -18.7  # mm from center - matched to frame STL slot left wall
cable_slot_x_right =  -6.3  # mm from center - matched to frame STL slot right wall

# Lean angle, measured from vertical, leaning forward over the base
# (the back panel - and therefore the whole frame attached to it - tilts
# back by this angle, achieved by physically rotating the panel itself)
lean_angle_deg = 15.0

# Corner screw clearance holes (M2.5), positions measured from frame
# center, taken from the existing frame's corner screw boss sketches
screw_x = 53.8          # mm - +/- from center
screw_y = 39.75         # mm - +/- from center
screw_hole_d = 2.9       # mm - M2.5 clearance

# PCB retention posts, positions measured from frame center, taken from
# the existing frame's retention post sketches
post_x = 44.4            # mm - +/- from center
post_y = 30.35            # mm - +/- from center
post_d = 6.0              # mm - post diameter
post_protrusion = 11.0    # mm - reach from panel's front face to the PCB's
                           # back face (box_depth=16mm frame thickness,
                           # front_wall=2mm bezel, pcb_thickness=2.5mm:
                           # 16 - 2 - 2.5 = 11.5mm; reduced to 11.0mm by user)

# Ventilation grid - holes through the back panel over the Pi to let heat from
# the Pi (and the LEDs) escape. Centred over the PCB pocket, kept inside the
# retention posts (+/-post_x/post_y) and clear of the screws and cable notch.
vent_hole_d = 4.0         # mm - vent hole diameter
vent_pitch = 9.0          # mm - grid spacing
vent_half_x = 36.0        # mm - grid half-extent in X (posts at +/-44.4)
vent_half_y = 22.0        # mm - grid half-extent in world-Y (posts at +/-30.35)

# ============================================================
# MODEL
# ============================================================
# Build the back panel + holes + posts flat, lying along +Y with its
# pivot edge (the bottom, where it meets the base) at local Y=0 and its
# far edge at local Y=panel_height. Local X matches real-world X exactly
# (rotation is about the X axis). Local Y maps to real-world frame Y via
# local_Y = world_Y + panel_height/2, since the frame is centered at 0.
panel = (
    cq.Workplane("XY")
    .box(panel_width, panel_height, panel_thickness, centered=(True, False, False))
    .edges("|Z").fillet(corner_r)
)

# Local Y for each feature, mapped from real-world frame-centered Y
# (local_y = world_y + panel_height/2, since the box's own Y starts at 0
# rather than being centered - see box(centered=(True, False, False)))
screw_points = [
    (sx, sy + panel_height / 2)
    for sx in (-screw_x, screw_x)
    for sy in (-screw_y, screw_y)
]
post_points = [
    (px, py + panel_height / 2)
    for px in (-post_x, post_x)
    for py in (-post_y, post_y)
]

# Use an absolute workplane at the original XY plane (Z=0, not a
# face-derived workplane) so (x, y) coordinates match the box's own
# global coordinate system exactly - a `.faces(">Z").workplane()` would
# instead re-center its local origin on that face's own bounding box,
# and also risks picking the wrong face once posts/holes already exist.
#
# Posts protrude from local Z=0 (not Z=panel_thickness) - this is the
# face that ends up facing the frame after rotation; the previous
# version had this backwards, putting posts on the panel's rear face.
bottom_wp = cq.Workplane("XY")

# Cable slot notch at the bottom edge of the panel, same X as the base slot.
# Extends panel_thickness mm up from local Y=0 (the pivot/bottom edge),
# through the full panel thickness in local Z, so the cable can pass through
# the base slot and up through the panel without obstruction.
slot_notch_w = cable_slot_x_right - cable_slot_x_left
slot_notch_cx = (cable_slot_x_left + cable_slot_x_right) / 2
panel = panel.cut(
    cq.Workplane("XY")
    .center(slot_notch_cx, panel_thickness / 2)
    .box(slot_notch_w, panel_thickness, panel_thickness + 0.02, centered=(True, True, False))
    .translate((0, 0, -0.01))
)

# Screw clearance holes, straight through the panel thickness
panel = panel.cut(
    bottom_wp.pushPoints(screw_points)
    .circle(screw_hole_d / 2)
    .extrude(panel_thickness)
)

# Ventilation grid, straight through the panel thickness (world-centred grid,
# mapped to local Y). Region stays inside the posts, so no filtering needed.
_nx = int(vent_half_x // vent_pitch)
_ny = int(vent_half_y // vent_pitch)
vent_points = [
    (i * vent_pitch, j * vent_pitch + panel_height / 2)
    for i in range(-_nx, _nx + 1)
    for j in range(-_ny, _ny + 1)
]
panel = panel.cut(
    bottom_wp.pushPoints(vent_points)
    .circle(vent_hole_d / 2)
    .extrude(panel_thickness)
)

# Retention posts, protruding from the panel's front face (local -Z,
# which after rotation faces forward toward the frame)
posts = bottom_wp.pushPoints(post_points).circle(post_d / 2).extrude(-post_protrusion)
panel = panel.union(posts)

# Rotate the whole panel (with its holes and posts) up about its own
# bottom-front edge (local origin) by (90 + lean_angle_deg), so it leans
# forward over the base toward the front, same convention validated in
# stand.py.
rotation_deg = 90.0 + lean_angle_deg
panel_rotated = panel.rotate((0, 0, 0), (1, 0, 0), rotation_deg)

# Align the panel's front face at its base junction with the base's
# top-back corner (Y=base_depth, Z=panel_thickness). This makes the joint
# flush: the upright's front surface is exactly coplanar with the base's
# back edge at the top surface, with no protrusion.
# The panel's minimum world Z after this translation is
# panel_thickness + z_rot_min = 3 - 0.776 = 2.224mm > 0, so the panel
# never dips below the desk; the base covers Z=0..panel_thickness anyway.
panel_positioned = panel_rotated.translate((0, base_depth, panel_thickness))

# Base: flat foot resting on the table.
# Narrower than the panel (97.6mm vs 125.6mm) - 14mm cut from each end to
# leave the lower screw holes on the upright accessible from the sides.
base = (
    cq.Workplane("XY")
    .box(base_width, base_depth, panel_thickness, centered=(True, False, False))
)

# Cable slot through full base thickness and depth, aligned with frame cable slot.
# Slot is made 0.02mm oversized in Y and Z and shifted -0.01mm in each to avoid
# co-planar faces with the base (OCC boolean hangs on exact co-planar cuts).
slot_cx = (cable_slot_x_left + cable_slot_x_right) / 2
slot_w  = cable_slot_x_right - cable_slot_x_left
eps = 0.02
cable_slot = (
    cq.Workplane("XY")
    .center(slot_cx, base_depth / 2)
    .box(slot_w, base_depth + eps, panel_thickness + eps, centered=(True, True, False))
    .translate((0, 0, -eps / 2))
)
base = base.cut(cable_slot)

result = base.union(panel_positioned)

# Skirts: vertical panels that drop from Z=panel_thickness down to Z=0 at the
# X positions of the three base cuts, so the cuts are hidden when viewed from
# the front. Each skirt is flush with the panel's front face (Y=base_depth)
# and panel_thickness deep in Y.
overhang = (panel_width - base_width) / 2   # = 14mm each end
skirt_specs = [
    (-(base_width / 2 + overhang / 2), overhang),  # left end overhang
    (+(base_width / 2 + overhang / 2), overhang),  # right end overhang
    (slot_cx, slot_w),                              # cable slot
]
for cx, w in skirt_specs:
    skirt = (
        cq.Workplane("XY")
        .center(cx, base_depth - panel_thickness / 2)
        .box(w, panel_thickness, panel_thickness, centered=(True, True, False))
    )
    result = result.union(skirt)

# Cut the cable notch all the way down to Z=0 through the skirt and panel
# bottom, so the cable can pass from desk level up through the back plate.
# Applied in world coordinates after all unions so it clears skirt material too.
notch_ext = (
    cq.Workplane("XY")
    .center(slot_notch_cx, base_depth - panel_thickness / 2)
    .box(slot_notch_w, panel_thickness + eps, panel_thickness + eps, centered=(True, True, False))
    .translate((0, 0, -eps / 2))
)
result = result.cut(notch_ext)

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(result, "case_riser_v2.stl", tolerance=0.01, angularTolerance=0.1)

tip_y = base_depth - panel_height * math.sin(math.radians(lean_angle_deg))
tip_z = panel_height * math.cos(math.radians(lean_angle_deg))
print(f"Exported case_riser_v2.stl (v{VERSION}): panel {panel_width}x{panel_height}x{panel_thickness}mm, "
      f"base_depth={base_depth}mm, lean_angle={lean_angle_deg} deg, "
      f"{len(vent_points)} vent holes")
print(f"Panel top edge position: Y={tip_y:.2f}mm, Z={tip_z:.2f}mm (from base front edge / table)")
