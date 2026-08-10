# 🖥️ Stand — Raspberry Pi Touch Display 2 (10.1")

A 3D-printable desk stand for the **10.1-inch** Raspberry Pi Touch Display 2
with a Raspberry Pi 5 mounted on its back. One printed part, two screws, a 10°
backward lean.

The 10.1" panel needs no enclosure — the Pi bolts to the standard 58 × 49 mm
pattern in the middle of the back plate, and its active cooler wants free air.
Only a way to stand the panel on a desk is missing.

**Highlights**

- One part, two M2.5 screws, no other fasteners.
- About 45 g of PETG, roughly 2¼ hours, no supports and no brim.
- The panel hangs clear of the desk, so nothing shows below the bezel.
- Bolts to the lower bracket pair only, clear of the DSI ribbon.
- Two moulded-in collars carry the power lead down the back to the desk.

![Six views of the stand: an L in section, 140 mm across, with an upright leaning back 10 degrees carrying two gabled windows and a screw hole in each outer column, and a foot reaching 65 mm backward with two rectangular windows. Two cable collars stand proud of the upright's back face at one outer edge, each a split ring on a tapered plinth, one near the top and one near the foot.](stand10_preview.png)

## ⚠️ Panel orientation

> [!WARNING]
> **The panel mounts 180° from the way it arrives.** The part does not fit the
> other way up.

The two bracket pairs sit at different offsets from their nearest short edge,
and the Pi is not centred vertically. Mounted as delivered, only 14 mm of back
plate is clear above the lower brackets before the board begins. Turned over,
59 mm is clear.

The image and touch mapping are turned to match by `build10/display.py`
(`ROTATE_DEG = 180`). **No change to `/boot/firmware/config.txt` is required.**

> [!NOTE]
> The DSI overlay's `rotation=180` has no effect on this display, which writes
> straight to `/dev/fb0`. Its `invx,invy` do work, but must not be set as well
> — they cancel against the software mapping and invert every tap.

## 🔧 Requirements

| | |
|---|---|
| Panel | Raspberry Pi Touch Display 2, 10.1", Pi already mounted |
| Screws | **2 × M2.5 × 12 mm**, pan or socket head |
| Power lead | 4 mm across the jacket — see [Cable routing](#-cable-routing) |
| Filament | PETG, about 45 g |
| Print bed | 140 × 65 mm minimum, 88 mm height |

M2.5 × 12 is confirmed on hardware. The bosses are threaded 8 mm deep and the
pad is 5 mm thick, giving 7 mm of engagement without bottoming out.

## 🖨️ Printing

```
PETG, 0.2 mm layer, 3 walls, 20% infill, no supports.
Orientation: foot flat on the bed, upright rising — as modelled, no rotation.
```

PETG rather than PLA because the panel is an always-on device in a warm room:
PETG's glass transition is ~80 °C against PLA's ~60 °C.

No supports and no brim are needed. The upright leans 10°, the window gables
are pitched past 45°, and the foot puts about 4,600 mm² on the bed. The only
downward-facing surfaces are the two screw bores, which span 2.9 mm and bridge.

The cable collars keep that true. Each is a ring extruded along the panel's own
up direction, so it leans back with the upright rather than presenting a new
overhang, and each sits on a plinth sloped at 50° that carries its projection
back to the wall. `check_stand10.py` measures the result: the downward-facing
area is the same 22.4 mm² with the collars as without them.

## 🔩 Assembly

1. Rest the panel face-down on something soft, turned 180° from its delivered
   orientation — the Pi's port face at the **top**.
2. Offer the stand up to the lower bracket pair. The flat pads around the screw
   holes sit on the bosses; the faces above and below them come to rest against
   the back plate itself.
3. Run an M2.5 × 12 through each hole into the boss. Firm, not tight — there is
   no washer face, and PETG dishes if over-torqued.
4. Stand the assembly up.
5. Press the power lead into the two collars — see below.

The panel ends up hanging about 2 mm clear of the desk. Its weight is carried
by the two screws in shear.

## 🔌 Cable routing

Without help the power lead leaves the Pi at the top of the panel and hangs out
to the side and behind. Two collars on the back of the upright take it down to
the desk instead.

Bring the lead down the same side of the panel as the Pi's power socket, then
press it into the upper collar and the lower one in turn. Each mouth is 3.6 mm
against a 4 mm lead, so the jacket has to squeeze slightly going in; that is
what stops it falling out again.

**The two mouths deliberately face opposite ways.** The lead cannot leave
without moving in two directions at once, so retention does not depend on a
lip springing open and shut — which matters, because PETG at this section does
not flex much. If the mouths prove too tight in practice, raising `clip_mouth`
above `clip_bore` turns them into plain open channels and the opposed
directions still hold the lead in place.

The collars sit as far outboard as they fit on the bolt column, because the
lead's overmould and its own stiffness need room to turn: the further out the
run, the wider the radius it can take. The upper collar stops 10 mm short of
the top of the upright for the same reason.

> [!NOTE]
> There are two collars rather than three because of the bolt line. Counting
> its plinth, each collar occupies about 24 mm of vertical run, and the bolt
> head has to stay reachable — which leaves room for one collar below it and
> none between it and the upper collar.

## 📐 Key dimensions

All in the mounted orientation, i.e. after the 180° turn.

| | |
|---|---|
| Stand | 140 × 65 × 88 mm |
| Panel outline | 167 × 247 mm |
| Lower bosses | 121.8 mm apart, 41 mm up from the bottom edge |
| Bosses | M2.5, 3 mm proud of the back plate, 8 mm thread depth |
| Pi, port face to SD end | 100 – 187 mm up the back plate |
| Mass, panel + Pi | 558 g |

## 🛠️ Troubleshooting

**The assembly rocks on the desk.** The front face is meant to touch the back
plate both above and below the screws. If only one side is touching, check that
the pads are seated squarely on the bosses and that neither screw is
over-tightened.

**The stand fits, but at the wrong end of the display.** The panel is the wrong
way up — see [Panel orientation](#️-panel-orientation).

**The top of the stand fouls the DSI ribbon.** The ribbon loops under the board
and hangs below it. The upright stops at 87 mm to clear it; a taller value in
`stand10.py` will press on the loop.

**The lead will not go into the collars.** The mouths are 0.4 mm narrower than
a 4 mm lead by design. A thicker lead needs `CABLE_D` set to its own diameter
and the part reprinted; a lead that will not squeeze needs `clip_mouth` raised
above `clip_bore`, which leaves the opposed mouths doing the retaining.

**The collars are on the wrong side.** They are on one bolt column only. Flip
`clip_x_sign` in `stand10.py` and reprint.

**Taps land diagonally opposite the finger.** Both the software mapping and the
overlay's `invx,invy` are inverting the touchscreen. Remove the overlay
parameters.

## ⚙️ Parameters

Every dimension is a parameter at the top of `stand10.py`. Rebuild and verify
with:

```bash
python stand10.py && python check_stand10.py
```

| Parameter | Default | Effect |
|---|---|---|
| `tilt` | 10.0 | Backward lean, degrees |
| `foot_depth` | 65.0 | Rearward reach; sized for the hanging cable, not the panel |
| `clear_z` | 2.0 | Gap between the panel's bottom edge and the desk |
| `stand_w` | 140.0 | Width across; stays hidden behind the 167 mm panel |
| `bear_s1` | 87.0 | Top of the upright; limited by the DSI ribbon |
| `hole_d` | 2.9 | M2.5 clearance |
| `CABLE_D` | 4.0 | Power lead across the jacket; sets the bore and the mouth |
| `clip_mouth` | 3.6 | Gap the lead is pushed through; raise past `clip_bore` for open channels |
| `clip_x_sign` | −1.0 | Which bolt column carries the collars; −1 is the right hand side seen from behind |
| `clip_top_clear` | 10.0 | Upper collar's distance below the top of the upright |
| `clip_ramp` | 50.0 | Plinth slope under each collar, in the printer's frame |

## 📄 Licence and credits

**GPL-3.0**, as the rest of this repository. This differs from
[`case/`](../case), which is CC BY as a remix of RonnyS's Touch Display 2 case.
Nothing here derives from that work, so the attribution requirement does not
apply. Credit is welcome, not required.

Issues and suggestions are welcome via the repository's issue tracker.
