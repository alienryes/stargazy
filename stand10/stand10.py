"""Desk stand for the Raspberry Pi Touch Display 2 (10.1") stargazing display.

Original work, not a remix - see stand10/README.md. GPL-3.0, unlike case/,
which is a CC-BY remix of RonnyS's 5" case.

The 10.1" panel needs no enclosure: the Pi bolts to the standard 58 x 49 mm
pattern in the middle of the back plate and is properly mounted on its own,
with an active cooler that wants free air. All that is missing is a way for the
panel to stand on a desk. That is this part.

SHAPE - an L in section, extruded across the panel's width:

  - an UPRIGHT lying against the panel's back plate, leaning back 10 degrees
  - a FOOT leaving the upright's lower end and lying in the desk plane

ONE PART SPANNING BOTH BOSSES, not two separate legs. The panel offers only
two bosses along its lower edge, so a leg per side would carry a single bolt
each and could rotate about it, resisted by nothing but friction. Both bolts
on one part removes that freedom entirely.

THE PANEL HANGS CLEAR OF THE DESK. Its weight goes through the two M2.5 bolts
in shear and nothing but the stand's own foot touches the desk. Neither the
panel's bottom edge nor any printed lip appears below the bezel.

THE FRONT FACE IS STEPPED, AND THE STEP IS THE WHOLE TRICK. The bosses stand
3 mm proud of the back plate, so a part bolted flat against them is held 3 mm
off the plate everywhere, touching nothing but two small annular faces. The
front face therefore reaches back across that 3 mm to touch the plate itself -
and it does so on BOTH SIDES of the bolt line, so the pad band is a recess
between two bearing faces with the bosses sitting in it.

Both sides, because two screws in a line are an axis and the assembly will
pivot on it. Bearing only above the bolts, which is what v0.3.x did, leaves
the centre of mass holding that face in contact and nothing at all resisting
rotation the other way; on the desk it rocked. Faces above and below make a
couple that resists both senses, and because both lie on the same plane they
cannot compete for the seat.

The version that bore only above it was not an oversight but a bad trade: the
worry was that a face low down might print proud, become a pivot, and lift the
upper one off. That risk is real and small. It was traded against a defect
that turned out to be certain.

NOTHING HERE IS SIZED BY STRESS. The bearing face carries about 2.1 N, each
bolt about 2.1 N of tension and 2.7 N of shear, and the upright's root sees
roughly 0.36 MPa against PETG's ~50 MPa yield. Sections are set by print
reliability, stiffness and the size of the windows they frame; treating any of
them as structural minima when editing would be a misreading.

MODELLED IN THE DESK FRAME:
    Y = backward, away from the viewer      Z = up from the desk
    X = across the panel's width, zero on the panel's vertical centreline
The panel is located by (s, t): s runs up the back plate from the panel's
bottom edge, t runs out from the plate. `panel_to_desk` is the only place the
tilt appears, so every dimension below can be read against the caliper
measurements rather than against a rotated frame. Features that belong to the
panel - the bolt holes, the upright's windows - are sketched in (X, s) and
swept through the plate by `panel_prism`, so they too stay readable.

PRINT ORIENTATION: foot flat on the bed, upright rising. The upright's 10 deg
lean is a 10 deg overhang, so it needs no support, and the 140 x 65 mm foot
gives the bed contact a part this tall wants. Every window is roofed at 45 deg
or steeper for the same reason - see `window_profile`.
"""

import math
from pathlib import Path

import cadquery as cq

VERSION = "0.4.0"

# ============================================================
# PARAMETERS - all mm / degrees.
# ============================================================

# --- The panel. Every figure here was measured with calipers on the real
# --- article (2026-08-06), not taken from the product brief, whose stated
# --- 161.76 mm width is wrong by about 5 mm.
PANEL_W = 167.0        # outline across
PANEL_H = 247.0        # outline up
BOSS_DX = 121.8        # bottom bosses, centre to centre across
# Bottom bosses, up from the panel's bottom edge.
#
# ⇒ THE PANEL MOUNTS ROTATED 180 DEGREES FROM THE ORIENTATION IT ARRIVES IN.
# This is not arbitrary and it is what makes the part fit. The two boss pairs
# sit at DIFFERENT offsets - 41 mm from one short edge, 46 from the other, 159
# apart - and the Pi is NOT vertically centred: measured on the panel, it spans
# 60 to 147 mm from one edge, so it sits hard against that end. Mounted that way
# up, the pair 46 mm from the bottom leaves only 14 mm of clear plate before the
# Pi begins, and no stand can reach a bearing face past that. Turned over, the
# same board spans 100 to 187, the stand bolts to the pair now 41 mm up, and
# there is 59 mm of clear plate to work in.
#
# The orientation also puts the Pi's port end 60 mm from the TOP edge, which is
# where both cables want to leave from and the reason this panel needs no
# cable-strain lift. The image is turned to match in the render path, not in
# the DSI overlay: the overlay's rotation= sets a KMS property, which a process
# writing bytes straight at /dev/fb0 never sees.
BOSS_S = 41.0
BOSS_PROUD = 3.0       # boss faces stand this far off the back plate
BOSS_THREAD = 8.0      # M2.5 thread depth available in the boss
# The Pi's lower edge, up the back plate, in the mounted orientation. MEASURED,
# not derived: the earlier 95.5 came from assuming the board was 56 mm tall and
# vertically centred, and it is neither - it is 87 mm from port face to SD end
# and sits well off centre. The arithmetic happened to land close enough to the
# truth here that nothing failed, which is exactly why it survived; on the other
# way up the same assumption hid a 45 mm collision.
PI_S0 = 100.0

# --- Stance
tilt = 10.0            # backward lean from vertical
clear_z = 2.0          # panel's bottom edge above the desk
foot_depth = 65.0      # how far the foot reaches behind the panel's bottom edge

# --- Section
stand_w = 140.0        # across; the panel is 167, so this stays hidden behind it
up_t = 5.0             # upright thickness, and so the pad the screw threads through
foot_t = 5.0           # foot thickness
root_fillet = 6.0      # where the upright's back face meets the foot

# --- Where the front face does what, in s. Reading up the plate: it touches,
# --- steps back onto the boss plane, then touches again - so the pad band is a
# --- recess between two bearing faces and the bosses sit in it.
lo_bear_s1 = 35.0      # lower bearing face runs from the bottom up to here
pad_s0 = 38.5          # boss plane starts, after a ramp back off the plate
pad_s1 = 46.0          # and runs up to here: the boss needs flat around it
bear_s0 = 49.5         # upper bearing face starts, above the bolt line
# ...and stops here. Not set by the Pi, whose port face is at 100, but by the
# DSI ribbon, which loops UNDER the board and hangs below it. At 90 the top of
# the stand pressed on the loop; 87 clears it. Measured by fitting, because
# nothing about the board's own footprint predicts where a flexible cable sits.
bear_s1 = 87.0

# --- Fasteners
hole_d = 2.9           # M2.5 clearance, print-tolerant

# --- Lightening. The columns carry the bolts, the rib splits the windows so
# --- neither the bearing rail nor the foot spans the full width unsupported.
# --- Material is taken out by WIDENING these windows rather than by thinning
# --- up_t or foot_t: bending stiffness falls linearly with width but with the
# --- cube of thickness, so at equal volume removed a window costs about a
# --- third of what thinning costs. Nothing here is near a stress limit, but
# --- the panel should not visibly flex when the screen is touched.
col_in = 52.0          # bolt columns run from here out to the edge
rib_hw = 6.0           # half-width of the centre rib
win_s0 = 12.0          # upright window, bottom
win_apex_s = 84.0      # upright window, tip of the gable; the rail runs above it
gable_slope = 1.15     # gable rise per unit half-width - see window_profile
foot_win_y0 = 17.0     # foot window, front edge
foot_win_y1 = 59.0     # foot window, back edge
foot_rail_w = 10.0     # foot side rails, measured in from each edge

# ============================================================
# GEOMETRY
# ============================================================

_A = math.radians(tilt)
_BACK_T = BOSS_PROUD + up_t          # the back face, a single flat plane
_SWEEP = 40.0                        # half-length used to sweep panel features


def panel_to_desk(s, t):
    """A point on the panel, (up the plate, out from the plate), in desk (Y, Z)."""
    return (s * math.sin(_A) + t * math.cos(_A),
            clear_z + s * math.cos(_A) - t * math.sin(_A))


def s_at_z(t, z):
    """How far up the plate the line at depth `t` crosses desk height `z`."""
    return (z - clear_z + t * math.sin(_A)) / math.cos(_A)


def panel_prism(sketch):
    """Sweep a sketch drawn in (X, s) right through the plate.

    The sketch is built on XY as (x, y) = (X, s) and extruded both ways, then
    carried onto the panel by a single rotation about X. Sweeping symmetrically
    is what lets one rotation do the job: the map from (X, s, t) to the desk
    frame is left-handed, so a one-sided extrusion would come out on the wrong
    side of the plate, and a symmetric one cannot.
    """
    return (sketch.extrude(_SWEEP, both=True)
            .rotate((0, 0, 0), (1, 0, 0), 90.0 - tilt)
            .translate((0, 0, clear_z)))


def profile():
    """The L in the desk's YZ plane, walked front-bottom to back-bottom.

    The front face touches the plate BOTH SIDES of the bolt line. Bearing only
    above it - which is what v0.3.x did - leaves the assembly free to pivot on
    the screw axis, and it rocked on the desk. The centre of mass holds the
    upper face in contact, but nothing at all resisted rotation the other way.
    Two faces straddling the bolts make a couple that resists both, and since
    both sit on the same plane they cannot fight each other for the seat.

    The reasoning that produced the one-sided version was that a face low down
    might print proud and become a pivot, lifting the upper one off. That risk
    is real but small, and it was traded against a defect that turned out to be
    certain.
    """
    return [
        panel_to_desk(s_at_z(0.0, 0.0), 0.0),                 # front, on the desk
        panel_to_desk(lo_bear_s1, 0.0),                       # top of the lower face
        panel_to_desk(pad_s0, BOSS_PROUD),                    # back onto the boss plane
        panel_to_desk(pad_s1, BOSS_PROUD),                    # top of the boss plane
        panel_to_desk(bear_s0, 0.0),                          # foot of the upper face
        panel_to_desk(bear_s1, 0.0),                          # top of the upper face
        panel_to_desk(bear_s1, _BACK_T),                      # over the top
        panel_to_desk(s_at_z(_BACK_T, foot_t), _BACK_T),      # down onto the foot
        (foot_depth, foot_t),
        (foot_depth, 0.0),
    ]


def window_profile(x0, x1):
    """One upright window in (X, s): a rectangle under a gable.

    The gable is what makes the window printable. Printing foot-down, the
    window's top edge would otherwise be a 46 mm unsupported bridge; two slopes
    meeting at a point need no support and no bridge at all.

    `gable_slope` is above 1.0 on purpose. A 45 degree gable drawn in (X, s)
    does NOT come out at 45 degrees on the bed: s is the panel's own axis, and
    it projects onto Z shortened by cos(tilt), so an apparently 45 degree roof
    prints at 44.6 and lands the wrong side of the rule. The slope is defined
    against the half-width so the margin does not move when the window does.
    """
    half = (x1 - x0) / 2.0
    top = win_apex_s - gable_slope * half
    return [
        (x0, win_s0), (x1, win_s0), (x1, top),
        ((x0 + x1) / 2.0, win_apex_s), (x0, top),
    ]


def build():
    part = (
        cq.Workplane("YZ")
        .polyline(profile())
        .close()
        .extrude(stand_w)
        .translate((-stand_w / 2.0, 0, 0))
    )

    # Fillet the root before anything is cut into it - the concave edge where
    # the upright's back face lands on the foot. Both windows stay well clear.
    y_root, z_root = panel_to_desk(s_at_z(_BACK_T, foot_t), _BACK_T)
    part = part.edges(cq.NearestToPointSelector((0, y_root, z_root))).fillet(root_fillet)

    # Windows through the upright, either side of the centre rib.
    for x0, x1 in ((rib_hw, col_in), (-col_in, -rib_hw)):
        cutter = panel_prism(cq.Workplane("XY").polyline(window_profile(x0, x1)).close())
        part = part.cut(cutter)

    # Windows through the foot. These are plain vertical holes in a flat plate,
    # so they need no roof.
    x_edge = stand_w / 2.0 - foot_rail_w
    for x0, x1 in ((rib_hw, x_edge), (-x_edge, -rib_hw)):
        part = part.cut(
            cq.Workplane("XY")
            .moveTo((x0 + x1) / 2.0, (foot_win_y0 + foot_win_y1) / 2.0)
            .rect(x1 - x0, foot_win_y1 - foot_win_y0)
            .extrude(foot_t + 2.0)
        )

    # The two bolt holes, on the panel's normal. No counterbore: the head sits
    # on the flat back face, which keeps the screw's engagement at 12 - 5 = 7 mm
    # against the boss's 8 mm of thread, so it clamps rather than bottoming out.
    holes = panel_prism(
        cq.Workplane("XY")
        .pushPoints([(BOSS_DX / 2.0, BOSS_S), (-BOSS_DX / 2.0, BOSS_S)])
        .circle(hole_d / 2.0)
    )
    part = part.cut(holes)

    return part


if __name__ == "__main__":
    part = build()
    bb = part.val().BoundingBox()
    print(f"stand10 v{VERSION}  tilt {tilt} deg")
    print(f"  bbox  X {bb.xmin:.2f}..{bb.xmax:.2f}  "
          f"Y {bb.ymin:.2f}..{bb.ymax:.2f}  Z {bb.zmin:.2f}..{bb.zmax:.2f}")
    print(f"  size  {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm")
    vol = part.val().Volume() / 1000.0
    print(f"  volume {vol:.1f} cm3   (PETG solid {vol * 1.27:.0f} g)")
    for name, s, t in (("bolt", BOSS_S, BOSS_PROUD),
                       ("bearing bottom", bear_s0, 0.0),
                       ("bearing top", bear_s1, 0.0),
                       ("Pi lower edge", PI_S0, 0.0)):
        y, z = panel_to_desk(s, t)
        print(f"  {name:<16} s={s:>5.1f}  ->  Y {y:>6.2f}  Z {z:>6.2f}")

    # Written beside this file rather than into the working directory, so
    # building from the repo root does not leave a stray STL there.
    out = Path(__file__).with_name("stand10.stl")
    cq.exporters.export(part, str(out), tolerance=0.01, angularTolerance=0.1)
    print(f"Exported: {out}")
