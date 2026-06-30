import cadquery as cq

# ============================================================
# PARAMETERS - Edit these to customize the model
# ============================================================
# CadQuery port of the Inky case frame (was Fusion 360 inky_case.f3d Body1 /
# inky_case_frame.stl). Geometry reverse-engineered from the original STL by
# cross-sectioning - see project_inky_case_design memory. Origin is centered
# in X/Y; the front bezel (show face) is at Z=0, the open back is at Z=16.
#
# Companion part: case_riser_v2.py (the tilting back panel + foot). The riser's
# corner screw holes and PCB retention posts are sized to mate with this frame.

# --- Outer shell ---
frame_w = 117.6        # mm - outer width  (X)
frame_h = 89.5         # mm - outer height (Y)
frame_t = 16.0         # mm - overall thickness / depth (Z, front face at 0)
corner_r = 2.0         # mm - vertical-edge fillet on the outer corners

# --- Front bezel + display window ---
bezel_t = 2.0          # mm - front wall thickness (the show face, Z 0..bezel_t)
window_w = 86.0        # mm - display cut-out width  (active area)
window_h = 54.0        # mm - display cut-out height (active area)
window_cy = 2.15       # mm - window centre Y offset above frame centre.
#                        Shifted down 0.5mm from the as-built +2.65 (user
#                        request): the top bezel (opposite the cable notch)
#                        grows 0.5mm and the notch-side bezel shrinks 0.5mm.
#                        Window height unchanged at 54mm.

# --- PCB pocket (open to the back) ---
pocket_w = 97.6        # mm - PCB pocket width  (96.8 PCB + 0.4/side clearance)
pocket_h = 69.5        # mm - PCB pocket height (68.7 PCB + 0.4/side clearance)
#                        wall thickness = (frame_w - pocket_w)/2 = 10mm all round

# --- Cable slot (notch in the bottom wall, open to the back) ---
cable_slot_x_left  = -18.7   # mm from centre - matches frame STL + riser slot
cable_slot_x_right =  -6.3   # mm from centre
cable_slot_floor_z =   7.2   # mm - slot floor height from the front face;
#                              material below this remains as a sill

# --- Corner screw holes (blind pilot holes, drilled from the back) ---
screw_x = 53.8         # mm - +/- from centre
screw_y = 39.75        # mm - +/- from centre
screw_pilot_d = 2.0    # mm - M2.5 self-tapping pilot (matches STL)
screw_depth = 5.0      # mm - blind depth from the back face (Z 11..16)

eps = 0.02             # mm - oversize on through-cuts to avoid coplanar faces

# ============================================================
# MODEL
# ============================================================
# Outer block, bottom (front bezel) at Z=0, rounded vertical edges.
frame = (
    cq.Workplane("XY")
    .box(frame_w, frame_h, frame_t, centered=(True, True, False))
    .edges("|Z").fillet(corner_r)
)

# PCB pocket: remove everything from the back of the bezel (Z=bezel_t) through
# to the open back, leaving 10mm perimeter walls. Cut slightly past the back.
pocket = (
    cq.Workplane("XY")
    .workplane(offset=bezel_t)
    .box(pocket_w, pocket_h, frame_t - bezel_t + eps,
         centered=(True, True, False))
)
frame = frame.cut(pocket)

# Display window: open the 2mm bezel only, over the active display area.
window = (
    cq.Workplane("XY")
    .workplane(offset=-eps)
    .center(0, window_cy)
    .box(window_w, window_h, bezel_t + 2 * eps, centered=(True, True, False))
)
frame = frame.cut(window)

# Cable slot: notch the bottom wall from its floor up to the open back, so a
# cable can pass from the PCB pocket out through the bottom edge. Spans from
# inside the pocket out past the outer edge in Y.
slot_w = cable_slot_x_right - cable_slot_x_left
slot_cx = (cable_slot_x_left + cable_slot_x_right) / 2
slot = (
    cq.Workplane("XY")
    .workplane(offset=cable_slot_floor_z)
    .center(slot_cx, -frame_h / 2)   # straddle the bottom wall
    .box(slot_w, (frame_h - pocket_h) / 2 + 2 * eps,
         frame_t - cable_slot_floor_z + eps, centered=(True, False, False))
    .translate((0, -eps, 0))
)
frame = frame.cut(slot)

# Corner screw holes: blind pilot holes from the back face (Z=frame_t) going
# forward by screw_depth. Built as cylinders then subtracted.
screw_pts = [(sx, sy) for sx in (-screw_x, screw_x) for sy in (-screw_y, screw_y)]
screws = (
    cq.Workplane("XY")
    .workplane(offset=frame_t + eps)
    .pushPoints(screw_pts)
    .circle(screw_pilot_d / 2)
    .extrude(-(screw_depth + eps))
)
frame = frame.cut(screws)

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(frame, "case_frame_v2.stl",
                    tolerance=0.01, angularTolerance=0.1)
print(f"Exported case_frame_v2.stl: outer {frame_w}x{frame_h}x{frame_t}mm, "
      f"window {window_w}x{window_h}mm @Y+{window_cy}, "
      f"pocket {pocket_w}x{pocket_h}mm")
