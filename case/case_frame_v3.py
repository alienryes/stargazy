import math

import cadquery as cq

# ============================================================
# PARAMETERS - Edit these to customize the model
# ============================================================
# CadQuery port of the Inky case frame (was Fusion 360 inky_case.f3d Body1 /
# inky_case_frame.stl). Geometry reverse-engineered from the original STL by
# cross-sectioning - see project_inky_case_design memory. Origin is centered
# in X/Y; the front bezel (show face) is at Z=0, the open back is at Z=16.
#
# Companion part: case_riser_v3.py (the tilting back panel + foot). The riser's
# corner screw holes and PCB retention posts are sized to mate with this frame.

VERSION = "3.2"        # 3.0 added the LED bezel ring; 3.1 opened the corner
#                        wire trenches to the back; 3.2 drops the unfittable
#                        corner-adjacent snap tab at one end of each channel

# --- Outer shell ---
# Frame grown +4mm per side (from 117.6x89.5) to host a 10mm-wide WS2812B LED
# strip in the front bezel band: the band widens 10mm -> 14mm (2mm outer wall +
# 10mm strip channel + 2mm inner wall). The display window and PCB pocket are
# unchanged and stay centred, so the validated display/PCB fit is preserved.
frame_w = 125.6        # mm - outer width  (X)   [was 117.6]
frame_h = 97.5         # mm - outer height (Y)   [was 89.5]
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
# LED BEZEL RING (v3.0) - WS2812B 60/m strip in the front bezel band
# ============================================================
# Light exits a continuous slot per side, filled by a translucent diffuser
# window printed INTO the frame with the MMU (exported as
# case_frame_v3_window.stl - no separate insert). Within the channel band the
# front is thickened to slot_front_t (diffuser window + air gap); the strip
# seats against its back, so it sits led_gap behind the diffuser and the light
# spreads before reaching it. The channel is open to the back so the strip drops
# in; snap tabs hold it. Four straight channels (one per side); the corners stay
# solid (the screws +/-screw_x/screw_y block them).
led_pitch = 16.7          # mm - WS2812B 60 LEDs/m pitch
strip_w = 10.0            # mm - strip width  (measure the actual reel; 10mm PCB)
strip_th = 2.0            # mm - strip thickness (PCB + 5050 LED)
led_ch_w = strip_w + 0.6  # mm - channel width (0.3/side clearance)
led_count_tb = 6          # LEDs along the top and along the bottom
led_count_lr = 4          # LEDs along the left and along the right

# Light exit: a continuous slot per side (not per-LED holes) so every LED
# contributes; the slot is filled by an MMU-printed translucent diffuser window.
diff_t = 0.8             # mm - diffuser window thickness (0.8-1.2mm; at the face)
led_gap = 3.0            # mm - air gap between the LEDs and the diffuser window so
#                           the light spreads before it hits it (no hotspots)
slot_front_t = diff_t + led_gap   # mm - thickened front within the channel band
#                           (3.8mm = window + gap); the strip seats against its
#                           back, a positive stop led_gap behind the diffuser.
slot_w = 7.0             # mm - light slot width (< led_ch_w; shoulders stop the strip)
strip_back_z = slot_front_t + strip_th   # mm - strip back face (front seats at slot_front_t)

# Snap-tab retention (stop the strip dropping back out of the channel)
tab_proj = 1.8            # mm - how far each tab overhangs the strip edge
tab_len = 4.0             # mm - tab length along the channel
tab_h = 1.2              # mm - tab thickness (Z)
tab_spacing = 22.0        # mm - max gap between tabs along a channel

# Radial centre of the 14mm bezel wall on each side (channel centre-lines)
band_cx = (pocket_w / 2 + frame_w / 2) / 2   # L/R channels run in Y at +/-band_cx
band_cy = (pocket_h / 2 + frame_h / 2) / 2   # T/B channels run in X at +/-band_cy


def _sym(count, pitch):
    """count LED positions symmetric about 0 at the given pitch."""
    start = -(count - 1) * pitch / 2.0
    return [start + i * pitch for i in range(count)]


xs_tb = _sym(led_count_tb, led_pitch)   # X positions for top & bottom rows
ys_lr = _sym(led_count_lr, led_pitch)   # Y positions for left & right columns

# Channel half-lengths cover the strip (outermost LED + half a pitch of tail)
ch_end_margin = 1.0
tb_ch_half = abs(xs_tb[-1]) + led_pitch / 2 + ch_end_margin
lr_ch_half = abs(ys_lr[-1]) + led_pitch / 2 + ch_end_margin
# Fail loudly if a channel would run into a corner screw pilot.
assert tb_ch_half < screw_x - screw_pilot_d / 2 - 1.0, "top/bottom channel hits corner screw"
assert lr_ch_half < screw_y - screw_pilot_d / 2 - 1.0, "left/right channel hits corner screw"

# --- Channels: open-to-back moats, one per side. They start at slot_front_t
#     (behind the thickened front), so the strip seats against that shoulder. ---
def _channel(cx, cy, lx, ly):
    return (cq.Workplane("XY").workplane(offset=slot_front_t)
            .center(cx, cy)
            .box(lx, ly, frame_t - slot_front_t + eps, centered=(True, True, False)))

for chan in (
    _channel(0,  band_cy, 2 * tb_ch_half, led_ch_w),   # top
    _channel(0, -band_cy, 2 * tb_ch_half, led_ch_w),   # bottom
    _channel(-band_cx, 0, led_ch_w, 2 * lr_ch_half),   # left
    _channel(band_cx, 0, led_ch_w, 2 * lr_ch_half),    # right
):
    frame = frame.cut(chan)

# --- Continuous light slots (straight, over the LEDs) + a continuous diffuser
#     window ring. Each straight slot spans the LEDs on that side (outermost LED
#     + half a pitch), slot_w wide, and carries light through the thickened front
#     to the air gap. The diffuser window is a single filleted ring round the
#     whole frame (exported for the MMU); its corners are a decorative inlay -
#     solid behind, no light - that softens the frame's corners. ---
slot_half_tb = abs(xs_tb[-1]) + led_pitch / 2
slot_half_lr = abs(ys_lr[-1]) + led_pitch / 2
slot_specs = [
    (0, band_cy, 2 * slot_half_tb, slot_w),    # top
    (0, -band_cy, 2 * slot_half_tb, slot_w),   # bottom
    (-band_cx, 0, slot_w, 2 * slot_half_lr),   # left
    (band_cx, 0, slot_w, 2 * slot_half_lr),    # right
]
for cx, cy, lx, ly in slot_specs:
    frame = frame.cut(
        cq.Workplane("XY").workplane(offset=-eps)
        .center(cx, cy)
        .box(lx, ly, slot_front_t + 2 * eps, centered=(True, True, False)))

# Diffuser window ring (translucent, MMU) - a filleted band round the whole
# frame, corners rounded to echo the frame's outer corners.
window_r = corner_r      # ring corner fillet (match the frame's outer corner)
win_out_hx, win_out_hy = band_cx + slot_w / 2, band_cy + slot_w / 2
win_in_hx, win_in_hy = band_cx - slot_w / 2, band_cy - slot_w / 2


def _window_ring(z0, thickness):
    outer = (cq.Workplane("XY").workplane(offset=z0)
             .box(2 * win_out_hx, 2 * win_out_hy, thickness, centered=(True, True, False))
             .edges("|Z").fillet(window_r))
    inner = (cq.Workplane("XY").workplane(offset=z0 - eps)
             .box(2 * win_in_hx, 2 * win_in_hy, thickness + 2 * eps, centered=(True, True, False))
             .edges("|Z").fillet(window_r))
    return outer.cut(inner)


windows = _window_ring(0.0, diff_t)
# Recess the front face to seat the ring - adds the corner pockets (the straight
# sections are already open from the slots above).
frame = frame.cut(_window_ring(-eps, diff_t + eps))

# --- Snap tabs: small overhangs on both channel walls that hold the strip back
#     against its front-stop shoulder. Placed near both ends and the middle. ---
tab_z = strip_back_z + 0.3
w = led_ch_w / 2


def _tab_positions(half):
    """Evenly spaced tab centres along a channel, symmetric about 0, no wider
    apart than tab_spacing, with the outermost tabs just inside the ends."""
    reach = half - tab_len / 2 - 1
    n = max(2, int(math.ceil(2 * reach / tab_spacing)) + 1)
    return [-reach + i * (2 * reach) / (n - 1) for i in range(n)]


tab_pos_tb = _tab_positions(tb_ch_half)
tab_pos_lr = _tab_positions(lr_ch_half)


def _tab(cx, cy, lx, ly):
    return (cq.Workplane("XY").workplane(offset=tab_z)
            .center(cx, cy).box(lx, ly, tab_h, centered=(True, True, False)))


# Drop the corner-adjacent snap tab at ONE end of each channel: once the strip is
# seated under the inner tabs it can't flex enough to tuck under a tab right by
# the corner, so that one was unfittable. It's a single end per channel in a
# 180-deg-rotational pattern (consistent insertion direction): top -> its -X (left)
# end, bottom -> its +X (right) end, right -> its +Y (top) end, left -> its -Y
# (bottom) end. The opposite end of each channel keeps its tab.
for sy, drop_tx in ((band_cy, tab_pos_tb[0]), (-band_cy, tab_pos_tb[-1])):
    for tx in tab_pos_tb:                       # top & bottom: tabs run along X
        if tx == drop_tx:
            continue
        frame = frame.union(_tab(tx, sy - w + tab_proj / 2, tab_len, tab_proj))
        frame = frame.union(_tab(tx, sy + w - tab_proj / 2, tab_len, tab_proj))
for sx, drop_ty in ((band_cx, tab_pos_lr[-1]), (-band_cx, tab_pos_lr[0])):
    for ty in tab_pos_lr:                       # left & right: tabs run along Y
        if ty == drop_ty:
            continue
        frame = frame.union(_tab(sx - w + tab_proj / 2, ty, tab_proj, tab_len))
        frame = frame.union(_tab(sx + w - tab_proj / 2, ty, tab_proj, tab_len))

# --- Corner wire trenches (v3.1): OPEN-TO-BACK L-shaped trenches connecting each
#     side channel to the next, routed around the OUTBOARD side of the corner
#     screw. Because they break through to the back (like the side channels), the
#     whole strip + corner-jumper assembly can be soldered FIRST and then dropped
#     in from behind. The earlier design ran an enclosed diagonal tunnel straight
#     across the corner at strip level - it passed in front of the screw, but was
#     bored (closed on all sides), so a pre-soldered jumper could not be pulled
#     through it. The front stays solid (Z 0..slot_front_t) so the diffuser ring
#     is untouched; the screw boss keeps full material on its front, inboard and
#     pocket sides - only the outboard/outer quadrant is trenched. ---
trench_w = 3.0           # mm - trench width (one silicone jumper, laid in open)
trench_screw_clr = 1.0   # mm - min wall between the trench and the screw pilot hole
trench_z0 = slot_front_t
trench_z1 = frame_t      # open all the way through to the back face

# Push the L's elbow outboard of the screw so trench_w/2 + hole radius +
# trench_screw_clr of wall sits between the trench and the pilot on each leg.
link_off = trench_w / 2 + screw_pilot_d / 2 + trench_screw_clr
link_x = screw_x + link_off    # X of the vertical (L/R) leg, outboard of the screw
link_y = screw_y + link_off    # Y of the horizontal (T/B) leg, outboard of the screw
ch_overlap = 4.0         # mm - how far each leg reaches back into its channel

# Keep-out checks - fail loudly rather than silently nick the screw or outer wall.
assert link_y - trench_w / 2 - screw_pilot_d / 2 >= screw_y + trench_screw_clr - 1e-6, \
    "horizontal corner trench too close to screw"
assert link_x - trench_w / 2 - screw_pilot_d / 2 >= screw_x + trench_screw_clr - 1e-6, \
    "vertical corner trench too close to screw"
assert link_y + trench_w / 2 <= frame_h / 2 - 1.0, "corner trench breaks the outer wall (Y)"
assert link_x + trench_w / 2 <= frame_w / 2 - 1.0, "corner trench breaks the outer wall (X)"
# Each leg must sit inside its channel band so it merges with that open moat.
assert abs(link_y - band_cy) <= led_ch_w / 2, "horizontal leg misses the T/B channel"
assert abs(link_x - band_cx) <= led_ch_w / 2, "vertical leg misses the L/R channel"


def _trench(cx, cy, lx, ly):
    return (cq.Workplane("XY").workplane(offset=trench_z0)
            .center(cx, cy)
            .box(lx, ly, trench_z1 - trench_z0 + eps, centered=(True, True, False)))


for sx in (1, -1):
    for sy in (1, -1):
        # Horizontal leg: from inside the top/bottom channel out to the elbow.
        hx0, hx1 = sx * (tb_ch_half - ch_overlap), sx * link_x
        frame = frame.cut(_trench((hx0 + hx1) / 2, sy * link_y, abs(hx1 - hx0), trench_w))
        # Vertical leg: from the elbow down into the left/right channel.
        vy0, vy1 = sy * (lr_ch_half - ch_overlap), sy * link_y
        frame = frame.cut(_trench(sx * link_x, (vy0 + vy1) / 2, trench_w, abs(vy1 - vy0)))

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(frame, "case_frame_v3.stl",
                    tolerance=0.01, angularTolerance=0.1)
# Translucent diffuser windows - co-print with the frame in the MMU's second
# extruder (load in PrusaSlicer as a part of the frame object; they are already
# aligned in the frame's coordinates).
cq.exporters.export(windows, "case_frame_v3_window.stl",
                    tolerance=0.01, angularTolerance=0.1)
n_leds = 2 * led_count_tb + 2 * led_count_lr
print(f"Exported case_frame_v3.stl (v{VERSION}): outer {frame_w}x{frame_h}x{frame_t}mm, "
      f"window {window_w}x{window_h}mm @Y+{window_cy}, "
      f"pocket {pocket_w}x{pocket_h}mm, diffused LED ring {n_leds} LEDs "
      f"({led_count_tb} top/bottom, {led_count_lr} sides), continuous window ring")
print(f"Exported case_frame_v3_window.stl: MMU diffuser windows, "
      f"{diff_t}mm translucent in the front of each slot")
