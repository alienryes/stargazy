# Stand — Raspberry Pi Touch Display 2 (10.1")

A 3D-printable desk stand for the **10.1-inch** Raspberry Pi Touch Display 2
with a Raspberry Pi 5 mounted on its back. One printed part, two screws, a 10°
backward lean.

This is not a case. The 10.1" panel does not need one: the Pi bolts to the
standard 58 × 49 mm pattern in the middle of the back plate and is properly
mounted on its own, and its active cooler wants free air. The only thing
missing is a way for the panel to stand on a desk.

![Six views of the stand: an L in section, 140 mm across, with an upright leaning back 10 degrees carrying two gabled windows and a screw hole in each outer column, and a foot reaching 65 mm backward with two rectangular windows.](stand10_preview.png)

## Licence

**GPL-3.0**, the same as the rest of this repository.

Note that this differs from [`case/`](../case), which is **CC BY** because it is
a remix of RonnyS's Touch Display 2 case. Nothing here derives from that work —
the 10.1" panel mounts differently enough that no part of the 5" design carries
over — so it is not encumbered by the attribution requirement. Credit is
welcome, not required.

## ⚠ The panel mounts upside down

**Turn the display 180° from the way it arrives, and rotate the image to match.**
This is not a preference — the part does not fit the other way up.

The panel's two bracket pairs sit at *different* offsets (41 mm from one short
edge, 46 mm from the other), and the Pi is **not vertically centred**: it spans
60–147 mm from the edge with the 46 mm pair. Mounted that way up, there is only
**14 mm** of clear back plate above the lower brackets before the Pi begins, and
the stand needs to reach a bearing face well past that. Turned over, the same
board spans 100–187 mm, the stand bolts to the pair now 41 mm up, and it has
**59 mm** of clear plate to work in — the part reaches 90 mm and clears the Pi
by 10.

It also puts the Pi's port face 60 mm from the **top** edge, which is where both
cables want to leave from, and is why this panel needs no cable-strain lift.

**The build already does this** — `ROTATE_DEG = 180` in `build10/display.py`
turns both the image and the touch mapping. No change to `config.txt` is needed
or wanted.

The DSI overlay's own `rotation=180` looks like the obvious place for it and
does **not** work here: that sets a KMS property, which `fbcon` honours but a
process writing bytes straight at `/dev/fb0` never sees — the hardware scans
out whatever it is handed. Its `invx,invy` *would* turn the touchscreen in the
driver, but do not set them as well or they cancel against the software
mapping and taps come back inverted.

Doing it in the render path costs 2.4 ms a frame, because the packing already
hands the image to PIL and a transpose is one more pass in C.

## What you need

| | |
|---|---|
| Filament | PETG, about **44 g**, roughly 2¼ h. (39.9 g and 2 h 5 min were measured in PrusaSlicer for v0.3.0, which was 8% smaller.) |
| Screws | **2 × M2.5 × 12 mm**, pan or socket head |
| Panel | Raspberry Pi Touch Display 2, 10.1", with the Pi already mounted |

The two screws are the only fasteners. They go through the stand's back face
into the panel's two lower bosses.

## Printing

```
PETG, 0.2 mm layer, 3 walls, 20% infill, no supports.
Orientation: foot flat on the bed, upright rising. As modelled — the STL needs
no rotation.
```

No supports and no brim. The upright leans 10°, which is a 10° overhang; the
window gables are pitched past 45°; and the foot puts about 4,200 mm² on the
bed. The only downward-facing surfaces in the whole part are the roofs of the
two screw bores, which span 2.9 mm and bridge.

PETG rather than PLA for the same reason as the 5" case: the panel is an
always-on device that lives in a warm room, and PETG's glass transition is
~80 °C against PLA's ~60 °C.

## Assembly

1. Stand the panel face-down on something soft.
2. Offer the stand up to the back plate. The two **pads** — the flat area
   around each screw hole — sit on the bosses. The **bearing face** above them,
   3 mm proud, should come to rest against the back plate itself.
3. Run an M2.5 × 12 through each hole into the boss. Firm, not tight; there is
   no washer face and PETG will dish if it is over-torqued.
4. Stand it up.

The panel ends up hanging about 2 mm clear of the desk. That is deliberate —
see below.

## How it works

### The panel hangs off the two screws

Nothing but the stand's own foot touches the desk. The panel's weight — 558 g,
about 5.5 N — goes through the two M2.5 screws in shear, which is a margin of
roughly a thousand. The alternatives were to rest the panel's bottom edge on
the desk, which puts 558 g on the panel's own frame and makes the lean angle a
property of the desk rather than of the part, or to run a printed toe underneath
it, which shows as a line under the bezel on the front face of an object whose
entire purpose is being looked at.

### The front face is stepped, and the step is the whole trick

The panel's bosses stand **3 mm proud** of the back plate. A part bolted flat
against them is therefore held 3 mm off the plate everywhere, touching nothing
but two small annular faces — which lets the panel rock.

So the stand reaches back across that 3 mm to touch the plate itself, and it
does so on **both sides of the bolt line**. The pad band is a recess between
two bearing faces, with the bosses sitting in it.

Both sides, because two screws in a line are an axis and the assembly will
pivot on it. The centre of mass is above the bosses, so it holds an upper face
in contact by itself — but nothing resists rotation the other way, and v0.3.0
rocked on the desk for exactly that reason. Faces above and below make a couple
that resists both senses, and since both lie on the same plane they cannot
compete for the seat.

*The one-sided version was a bad trade rather than an oversight: the worry was
that a face low down might print proud, become a pivot and lift the upper one
off. That risk is real and small, and it was traded against a defect that
turned out to be certain.*

### One part, not two legs

The panel offers only two bosses along its lower edge. A separate leg on each
side would carry a single screw and could rotate about it, resisted by nothing
but friction under the screw head. Both screws on one part removes that freedom
outright.

### It attaches at the bottom only

The panel has four bosses. The upper two are skipped: they add stiffness
against twist that a rigid metal back plate does not need, and the **DSI ribbon
runs beneath the Pi near the top edge**, about 20 mm down, where a part
attaching there could foul it.

### Nothing here is sized by stress

| | |
|---|---|
| Bearing face | ~2.1 N |
| Each screw | ~2.1 N tension, ~2.7 N shear |
| Upright root bending | ~0.36 MPa against PETG's ~50 MPa yield |

Sections are set by print reliability, stiffness and the windows they frame,
not by strength. When editing, do not read the 5 mm sections as structural
minima — but do note that the windows were widened rather than the sections
thinned, because bending stiffness falls linearly with width and with the
**cube** of thickness. At equal volume removed, a window costs about a third of
what thinning costs. The part went from 142.5 cm³ to 66.7 cm³ on that basis.

### The foot is 65 mm for the cable, not for the panel

The centre of mass projects 21.4 mm behind the panel's bottom edge, so the
panel alone would stand on a much shorter foot. What sets the length is that
**both cables leave this panel at the top** — power at the Pi's top left, DSI
beneath its upper edge — so a hanging lead pulls backward at the worst possible
height. At 65 mm it takes **1.93 N** of backward pull at the top of the panel to
lift the front; at 50 mm it would take 1.2 N, which a stiff USB-C lead can
plausibly reach.

## Measurements this depends on

All taken with calipers on the real panel (2026-08-06). The published product
brief is **not** a safe source here: its stated 161.76 mm width is wrong by
about 5 mm, and the drawing carries its own warning that it is not for
production data.

| | |
|---|---|
All in the **mounted** orientation, i.e. after the 180° turn described above.
Stating which way up a figure was taken is not pedantry here: the same panel
reads 41 mm and 46 mm for its two bracket pairs depending on which end you
measure from, and the Pi's clearance reads 59 mm one way and 14 mm the other.

| Panel outline | 167 × 247 mm |
|---|---|
| Lower bosses | 121.8 mm apart, 41 mm up from the bottom edge |
| Bosses | M2.5, 3 mm proud of the back plate, 8 mm thread depth |
| Pi, port face to SD end | **100 – 187 mm** up the back plate |
| Mass, panel + Pi | 558 g |

The stand stops at **87 mm** up the plate. That ceiling is set by the DSI
ribbon, which loops *under* the board and hangs below it — not by the board's
own edge at 100 mm. At 90 mm the top of the stand pressed on the loop.

## Files

| File | What it is |
|---|---|
| `stand10.py` | The model. Every dimension is a parameter at the top. |
| `stand10.stl` | Ready to slice. |
| `check_stand10.py` | Verification — run it after any edit. |

Rebuild and check with:

```bash
python stand10.py && python check_stand10.py
```

`check_stand10.py` tests the things that would otherwise only fail on the
panel: that the screw axes are **clear** (a fastener needs the absence of
material, and asking whether the pad is present at the screw position answers a
different question — one that returns true when the hole is missing); that the
step is 3.000 mm and lands the right way round, relieved below the bolt line
and touching above it; that nothing reaches into the panel or up into the Pi;
and that no surface outside the screw bores faces downward at under 45°.

## What the first print changed

v0.3.0 was printed and fitted, and two things came back that no render would
have shown:

- **It rocked**, pivoting on the screw axis, because the front face bore only
  above the bolt line. v0.4.0 bears both sides — see above.
- **The top pressed on the DSI ribbon** where it loops under the board. The
  upright is 3 mm shorter for it.

It also fitted perfectly at the wrong end of the display, which is what
established that the panel mounts upside down. **v0.4.0 has not itself been
printed.**

Still open, and only the hardware can answer it: whether hanging 2 mm clear of
the desk feels secure. If not, `clear_z = 0` plus a shallow toe is a parameter
change rather than a redesign.

## Parameters worth changing

| Parameter | Default | What it does |
|---|---|---|
| `tilt` | 10.0 | Backward lean, degrees |
| `foot_depth` | 65.0 | How far the foot reaches back — see above before shortening |
| `clear_z` | 2.0 | How far the panel hangs above the desk |
| `stand_w` | 140.0 | Across; stays hidden behind the 167 mm panel |
| `up_t`, `foot_t` | 5.0 | Section thickness — widen the windows instead |
| `hole_d` | 2.9 | M2.5 clearance |
