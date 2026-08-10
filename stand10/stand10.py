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

NO PRINTED PART APPEARS BELOW THE BEZEL. `clear_z` holds the panel's bottom edge
2 mm above the desk in the model, so no lip or toe is needed under the screen.

On the assembled article that edge comes to rest on the desk rather than hanging
clear, so the desk shares the load with the two M2.5 bolts instead of the bolts
carrying all of it in shear. Bolt-hole clearance, plate flex and the lean all
push the same way and the cause has not been isolated; the part works, so it has
not been chased. `clear_z` is therefore a modelled clearance, not a measured gap
- do not treat it as one when editing.

THE FRONT FACE IS STEPPED. The bosses stand 3 mm proud of the back plate, so a
part bolted flat against them is held 3 mm off the plate everywhere, touching
nothing but two small annular faces. The front face therefore reaches back
across that 3 mm to touch the plate itself, and does so on BOTH SIDES of the
bolt line - the pad band is a recess between two bearing faces, with the bosses
sitting in it.

Both sides are required because two screws in a line form an axis the assembly
can pivot on. Bearing only above the bolts, as v0.3.x did, leaves the centre of
mass holding that face in contact with nothing resisting rotation the other
way; the printed part rocked on the desk. Faces above and below form a couple
that resists both senses, and both lie on the same plane so they cannot compete
for the seat.

The one-sided version guarded against a face low down printing proud, becoming
a pivot and lifting the upper one off. That failure is possible but was not
observed; the rocking was.

THE POWER LEAD IS CLIPPED DOWN THE BACK. Two collars run up one bolt column,
taking the lead from the Pi down to the desk instead of letting it hang out to
the side and behind. They are on the column rather than the centre rib, and as
far outboard on it as they go without overhanging the edge, because the lead's
overmould and its own stiffness need room to turn: the further out the run, the
wider the radius it can take.

TWO IS WHAT FITS, and the bolt line is the reason - see `clip_s0`. Each collar
costs 23.8 mm of vertical run once its ramp is counted, and the bolt head has
to stay reachable, which leaves room for one collar below it and none above.

Each collar is a ring in (X, t) extruded along s, so it rises with the upright
and inherits the same 10 degree lean, which is an overhang the part already has
everywhere. A collar wrapping the lead any other way up would need a bridge
over the bore and a roof over the mouth.

THE MOUTHS ALTERNATE, and that is what retains the lead rather than a snap fit.
Adjacent collars open opposite ways, so the lead cannot leave without moving
two directions at once. Each mouth is also narrower than the lead, which a soft
PVC jacket squeezes through easily - the lip does not have to spring, which is
what makes a 2 mm PETG section acceptable here. Widening `clip_mouth` past
`clip_bore` turns them into plain channels and leaves the alternation doing all
the work, which is the fallback if the mouths prove tight in practice.

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

VERSION = "0.5.0"

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
# The part does not fit the other way up. The two boss pairs sit at DIFFERENT
# offsets - 41 mm from one short edge, 46 from the other, 159 apart - and the
# Pi is NOT vertically centred: measured on the panel, it spans
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
clear_z = 2.0          # modelled gap under the panel's bottom edge - see the
                       # header; the assembled edge rests on the desk
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

# --- Cable clips, up one bolt column. `clip_x_sign` picks the column: -1 is
# --- the right hand side seen from BEHIND the panel, which is the side the
# --- Pi's power lead comes down. X is measured with +X to the right of a
# --- viewer in FRONT of the screen, so the two are opposite signs.
CABLE_D = 4.0          # measured across the lead's jacket
clip_wall = 2.0
clip_bore = CABLE_D + 0.6    # a running fit; the collar routes, it does not grip
clip_mouth = CABLE_D - 0.4   # the gap the lead is pushed through - see the header
clip_h = 8.0           # collar height, up the plate
clip_ramp = 50.0       # underside slope, MEASURED IN THE DESK FRAME
clip_x_sign = -1.0
clip_top_clear = 10.0  # top collar held this far below the upright's top, so the
                       # overmould has room to turn into it
# Collar bottoms, up the plate. TWO, NOT THREE, AND THE BOLT LINE IS WHY. The
# ramp reaches 15.8 mm below a collar, so each one occupies 23.8 mm of run. The
# bolt sits at s=41 and its head and driver have to stay reachable, which leaves
# 33.8 mm of usable run below it - exactly one collar - and 9.0 mm above it
# under the top collar, which is not enough for anything. A third collar can
# only be had by moving the top one down off its 10 mm.
#
# The upper figure is `clip_top_clear`; the lower is a free choice, set to clear
# the root fillet, with its own ramp landing on the foot.
clip_s0 = (20.0, bear_s1 - clip_top_clear - clip_h)
clip_mouth_sign = (-1.0, 1.0)   # alternating, which is what retains the lead

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

_CLIP_R = clip_bore / 2.0 + clip_wall                  # collar outer radius
_CLIP_X = clip_x_sign * (stand_w / 2.0 - _CLIP_R)      # outer wall flush with the edge
_CLIP_T = _BACK_T + clip_wall + clip_bore / 2.0        # bore centre, out from the plate
_CLIP_ROOT_T = _BACK_T - 0.5         # collars start inside the wall, so the union
                                     # is an overlap rather than a tangent line
_CLIP_DROP = 16.0                    # extruded this far below each collar; the ramp
                                     # cut takes back whatever it does not need


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


def clip_solid(s0, mouth_sign):
    """One cable collar, positioned in the desk frame.

    Drawn in (X, t) and extruded along s, then carried onto the panel by a
    single rotation about X. The extrusion axis is the panel's own up
    direction, so the collar leans back with the upright and adds no overhang
    the part did not already have.

    The outer boundary is a disc merged with a rectangle reaching back into the
    plate. The disc alone would meet the flat back face along one tangent line,
    which is a knife edge rather than an attachment; the rectangle gives the
    collar a base the full 2 * `_CLIP_R` across.

    Everything is extruded from `_CLIP_DROP` below `s0`, and `ramp_cutter`
    then removes whatever falls under the ramp. Over-extruding is free: the cut
    plane passes through the wall at exactly `s0`, so any surplus goes with it.
    """
    h = clip_h + _CLIP_DROP
    disc = cq.Workplane("XY").moveTo(_CLIP_X, _CLIP_T).circle(_CLIP_R).extrude(h)
    base = (cq.Workplane("XY")
            .moveTo(_CLIP_X, (_CLIP_ROOT_T + _CLIP_T) / 2.0)
            .rect(2.0 * _CLIP_R, _CLIP_T - _CLIP_ROOT_T)
            .extrude(h))
    bore = (cq.Workplane("XY")
            .moveTo(_CLIP_X, _CLIP_T).circle(clip_bore / 2.0).extrude(h))
    # The mouth runs from the bore centre out through the wall, so it is open
    # whatever the wall thickness happens to be.
    reach = _CLIP_R + 1.0
    mouth = (cq.Workplane("XY")
             .moveTo(_CLIP_X + mouth_sign * reach / 2.0, _CLIP_T)
             .rect(reach, clip_mouth)
             .extrude(h))

    solid = disc.union(base).cut(bore).cut(mouth).translate((0, 0, s0 - _CLIP_DROP))
    # Local (x, y, z) is (X, t, s); this rotation is the only place that is
    # turned into desk coordinates.
    return solid.rotate((0, 0, 0), (1, 0, 0), -tilt).translate((0, 0, clear_z))


def ramp_cutter(s0):
    """Everything below one collar's 45-degree-or-steeper underside.

    A collar protruding ~9 mm from a near-vertical wall presents a downward
    face that is almost horizontal, which is the one thing this part is meant
    never to need support for. The ramp rises going backward, so the collar
    grows out of the wall rather than starting in mid air.

    ANCHORED AT THE COLLAR'S OUTER BOTTOM CORNER, not where it meets the back
    face. Anchoring at the wall looks like the natural choice and is wrong: the
    plane then climbs the collar's whole projection before it reaches the outer
    edge, which is further than a collar this tall can climb, and the cut takes
    the outer four fifths of every collar with it. From the outer corner the
    plane can only fall going forward, and the bottom face falls with it - the
    panel's own tilt sees to that - so the full section survives by
    construction and the taper lands entirely below `s0`.

    `clip_ramp` IS MEASURED IN THE DESK FRAME, not in (X, s). The gables have
    to correct for the panel's tilt because they are sketched in the panel's
    own axes; this plane is built in the frame the printer works in, so the
    angle it is given is the angle that prints.
    """
    y0, z0 = panel_to_desk(s0, _CLIP_T + _CLIP_R)
    big = 400.0
    below = (cq.Workplane("XY")
             .box(big, big, big, centered=(True, True, False))
             .translate((0, 0, -big)))
    return below.rotate((0, 0, 0), (1, 0, 0), clip_ramp).translate((0, y0, z0))


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

    # Cable collars last, so neither the root fillet nor any window has to be
    # computed against them.
    for s0, mouth_sign in zip(clip_s0, clip_mouth_sign):
        part = part.union(clip_solid(s0, mouth_sign).cut(ramp_cutter(s0)))

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
    print(f"  clips at X {_CLIP_X:.1f}, bore {clip_bore} at t={_CLIP_T:.1f}, "
          f"mouth {clip_mouth}")
    for s0, mouth_sign in zip(clip_s0, clip_mouth_sign):
        y, z = panel_to_desk(s0, _CLIP_T)
        print(f"    s {s0:>5.1f}..{s0 + clip_h:<5.1f} opens "
              f"{'-X' if mouth_sign < 0 else '+X'}  ->  Y {y:>6.2f}  Z {z:>6.2f}")

    # Written beside this file rather than into the working directory, so
    # building from the repo root does not leave a stray STL there.
    out = Path(__file__).with_name("stand10.stl")
    cq.exporters.export(part, str(out), tolerance=0.01, angularTolerance=0.1)
    print(f"Exported: {out}")
