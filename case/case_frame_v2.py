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

VERSION = "3.0"        # case rev - 3.0 adds the WS2812B LED bezel ring

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
# The strip sits in a channel behind the 2mm front wall, LEDs facing forward
# through small holes (front-firing dots). The channel is open to the back so
# the strip drops in during assembly; snap tabs hold it forward against the
# wall. Four straight channels (one per side); the corners stay solid because
# the corner screws (+/-screw_x, +/-screw_y) block the channel path.
led_pitch = 16.7          # mm - WS2812B 60 LEDs/m pitch
strip_w = 10.0            # mm - strip width  (measure the actual reel; 10mm PCB)
strip_th = 2.0            # mm - strip thickness (PCB + 5050 LED)
led_ch_w = strip_w + 0.6  # mm - channel width (0.3/side clearance)
led_count_tb = 6          # LEDs along the top and along the bottom
led_count_lr = 4          # LEDs along the left and along the right

# Light exit: a continuous slot per side (not per-LED holes) so every LED
# contributes, with a white diffuser insert behind it for an even glow.
diff_t = 1.5              # mm - diffuser insert thickness (thin white translucent)
slot_w = 7.0              # mm - visible slot width; < led_ch_w so the front-wall
#                           shoulders retain the diffuser (see case_diffusers_v1.py)
# Stack behind the front wall (front -> back): diffuser, then LED strip; tabs
# hold the strip, which presses the diffuser forward against the wall shoulders.
led_ch_clear_z = diff_t + strip_th + 0.3   # mm - front-wall back -> tab underside

# Snap-tab retention
tab_proj = 1.5            # mm - how far each tab overhangs into the channel
tab_len = 4.0             # mm - tab length along the channel
tab_h = 1.2              # mm - tab thickness (Z)

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

# --- Channels: open-to-back moats, one per side ---
def _channel(cx, cy, lx, ly):
    return (cq.Workplane("XY").workplane(offset=bezel_t)
            .center(cx, cy)
            .box(lx, ly, frame_t - bezel_t + eps, centered=(True, True, False)))

for chan in (
    _channel(0,  band_cy, 2 * tb_ch_half, led_ch_w),   # top
    _channel(0, -band_cy, 2 * tb_ch_half, led_ch_w),   # bottom
    _channel(-band_cx, 0, led_ch_w, 2 * lr_ch_half),   # left
    _channel(band_cx, 0, led_ch_w, 2 * lr_ch_half),    # right
):
    frame = frame.cut(chan)

# --- Continuous light slots through the 2mm front wall, one per side ---
# Each slot spans the LEDs on that side (outermost LED + half a pitch). It is
# slot_w wide - narrower than the channel - so the remaining front-wall
# shoulders on either side retain the diffuser insert that sits behind it.
slot_half_tb = abs(xs_tb[-1]) + led_pitch / 2
slot_half_lr = abs(ys_lr[-1]) + led_pitch / 2


def _slot(cx, cy, lx, ly):
    return (cq.Workplane("XY").workplane(offset=-eps)
            .center(cx, cy)
            .box(lx, ly, bezel_t + 2 * eps, centered=(True, True, False)))


for slot in (
    _slot(0, band_cy, 2 * slot_half_tb, slot_w),    # top
    _slot(0, -band_cy, 2 * slot_half_tb, slot_w),   # bottom
    _slot(-band_cx, 0, slot_w, 2 * slot_half_lr),   # left
    _slot(band_cx, 0, slot_w, 2 * slot_half_lr),    # right
):
    frame = frame.cut(slot)

# --- Snap tabs: small overhangs on both channel walls that hold the strip
#     forward against the front wall. Placed near both ends and the middle. ---
tab_z = bezel_t + led_ch_clear_z
w = led_ch_w / 2
tab_pos_tb = [-tb_ch_half + tab_len / 2 + 1, 0.0, tb_ch_half - tab_len / 2 - 1]
tab_pos_lr = [-lr_ch_half + tab_len / 2 + 1, 0.0, lr_ch_half - tab_len / 2 - 1]


def _tab(cx, cy, lx, ly):
    return (cq.Workplane("XY").workplane(offset=tab_z)
            .center(cx, cy).box(lx, ly, tab_h, centered=(True, True, False)))


for sy in (band_cy, -band_cy):                 # top & bottom: tabs run along X
    for tx in tab_pos_tb:
        frame = frame.union(_tab(tx, sy - w + tab_proj / 2, tab_len, tab_proj))
        frame = frame.union(_tab(tx, sy + w - tab_proj / 2, tab_len, tab_proj))
for sx in (band_cx, -band_cx):                 # left & right: tabs run along Y
    for ty in tab_pos_lr:
        frame = frame.union(_tab(sx - w + tab_proj / 2, ty, tab_proj, tab_len))
        frame = frame.union(_tab(sx + w - tab_proj / 2, ty, tab_proj, tab_len))

# --- Corner jumper-wire notches: shallow L-grooves in the back of each solid
#     corner, routed outboard of the screw pilots, so the 3-wire jumper linking
#     adjacent strip segments can pass across the corner. Cut only from the back
#     (Z frame_t-notch_depth .. frame_t) and kept clear of the screw pilots in
#     X/Y, so screw engagement is untouched. ---
notch_w = 3.0            # mm - groove width (fits a 3-conductor jumper)
notch_depth = 3.0        # mm - groove depth from the back face
route_x = 57.0           # mm - X the vertical leg sits at (outboard of screw_x)
route_y = 45.0           # mm - Y the horizontal leg sits at (outboard of screw_y)
assert route_y > screw_y + screw_pilot_d / 2 + notch_w / 2, "corner notch clips a screw pilot"
assert route_x > screw_x + screw_pilot_d / 2 + notch_w / 2, "corner notch clips a screw pilot"


def _notch_leg(cx, cy, lx, ly):
    return (cq.Workplane("XY").workplane(offset=frame_t - notch_depth)
            .center(cx, cy)
            .box(lx, ly, notch_depth + eps, centered=(True, True, False)))


for sx in (1, -1):
    for sy in (1, -1):
        # horizontal leg: top/bottom channel end -> (route_x, route_y)
        frame = frame.cut(_notch_leg(
            sx * (tb_ch_half + route_x) / 2, sy * route_y,
            route_x - tb_ch_half, notch_w))
        # vertical leg: left/right channel end -> (route_x, route_y)
        frame = frame.cut(_notch_leg(
            sx * route_x, sy * (lr_ch_half + route_y) / 2,
            notch_w, route_y - lr_ch_half))

# ============================================================
# EXPORT
# ============================================================
cq.exporters.export(frame, "case_frame_v2.stl",
                    tolerance=0.01, angularTolerance=0.1)
n_leds = 2 * led_count_tb + 2 * led_count_lr
print(f"Exported case_frame_v2.stl (v{VERSION}): outer {frame_w}x{frame_h}x{frame_t}mm, "
      f"window {window_w}x{window_h}mm @Y+{window_cy}, "
      f"pocket {pocket_w}x{pocket_h}mm, diffused LED ring {n_leds} LEDs "
      f"({led_count_tb} top/bottom, {led_count_lr} sides), slot {slot_w}mm")
