# Case — Raspberry Pi Touch Display 2 (5") + Raspberry Pi 4 or Pi 5

A 3D-printable desk case for the **5-inch** Raspberry Pi Touch Display 2 with a
Raspberry Pi 4 or Pi 5 mounted behind it, used landscape. Four printed parts, an
easel stand at a 20° lean, and an optional 40 mm fan.

The two boards share an outline and a mounting pattern, so only the port
openings differ. Print the files for your board — see
[Choosing the board variant](#choosing-the-board-variant), and read it before
committing to a Pi 5: **the Pi 5 variant has not been built on hardware**, and
its display ribbon routing is genuinely different.

## Credits and licence

This is a **remix of "Raspberry Pi Touch Display 2 Case" by RonnyS** —
<https://www.printables.com/model/1377047-raspberry-pi-touch-display-2-case> —
used under **CC BY**. The original targets the **7-inch** panel (its shell
pocket is 187 × 118 mm, matching the 7-inch outline of 189.32 × 120.24 mm); the
5-inch panel is 91.46 × 143.4 mm, so none of the original parts fit it. The
architecture is RonnyS's — shallow shell, bolt-on Pi clamshell, swappable
stand, optional fan — re-drawn parametrically in CadQuery at 5-inch scale.

This remix is released under **CC BY** as well. Credit RonnyS and this project.

The Raspberry Pi board models shown in the assembly diagrams are by
**Pyro_Industries** — <https://www.printables.com/model/727545-raspberry-pi-4>
and <https://www.printables.com/model/727155-raspberry-pi-5>, CC0. They are used
for illustration and for measuring connector positions, and are not
redistributed here.

Differences from the original, beyond scale:

- **No lid towers and no heat-set inserts.** The original bolts its lid to four
  M3-insert towers on the case-bottom, which forces a wider lid and a second
  screw chain. Here the lid screws into M2.5 male-female standoffs sitting on
  the Pi's own mounting holes, so one chain runs the whole stack and the lid
  continues the case-bottom's wall profile instead of straddling it.
- **The lid is located by four spigots, not by its screws.** The original's lid
  bolts into towers rising from its own plate — a short, stiff chain that needs
  no help. Ours bolts into standoffs stacked on the Pi, which is stacked on
  extenders, so the screws alone let the lid slide sideways on its seat. Four
  Ø3 pins on the wall top drop into blind sockets in the skirt and take that
  load instead. Measuring the original confirmed it has no register of its own:
  seated, the two parts meet in a plain butt joint with 0.00 mm of overlap.
- **Per-connector openings on the USB/Ethernet edge.** A continuous sill runs
  under the connectors and full-height dividers stand between them, so each
  connector gets its own window instead of one long slot. The sill is the
  original's idiom (its +X wall stops at Z 9.1 against a 12.4 wall top); the
  dividers are not — RonnyS leaves that edge as a single span.
- **The power/HDMI edge gets the sill but no dividers**, and that asymmetry is
  deliberate. On the USB/Ethernet edge the connectors protrude past the wall's
  outer face (to x 47.79 against 46.5), so a plug never touches the case and the
  sockets alone set the spacing. On the power/HDMI edge they stop at the wall's
  *inner* face, so the plug's overmould passes through the opening — and the two
  micro-HDMI sockets are only 13.5 mm apart, which is already tight for two
  cables on a bare Pi 4. Anything between them would likely stop both going in.
- The fan is **hung off the lid** instead of a separate Pi-mounted bracket —
  a Pi-mounted plate plus fan does not fit the 5-inch stack's headroom.
  Measured against the board models, the fan clears the GPIO header by only
  **1.10 mm**; check it on the real thing before relying on it. It does **not**
  clear a Pi 5 active cooler at all — see below.
- **The stand's foot is a plain blade, not a Y-fork.** The original splays each
  foot into two arms about 56 mm apart, which is what gives a narrow stand its
  sideways stability. Here the two stands are already 103.7 mm apart, so the
  fork earns nothing — and dropping it keeps the part a pure 2-D extrusion in
  print orientation, with no overhanging faces at all. Everything else about
  the fastening matches the original: a flat counterbored strap sharing that
  side's two display case screws.
- The shell keeps **discrete pass-through holes** for the standoffs rather than
  one large rear opening. On the 5-inch panel the case-screw bosses (y ±25.5)
  and the display's own Pi standoffs (y ±28.5) fall in the same band, so an
  opening big enough to clear the standoffs would swallow the screw bosses.
- No wall/V-slot brackets, and no Pi 3 variant.

## Parts and printing

Print in **PETG**. An enclosed Pi 4 can creep toward PLA's glass transition
(~60 °C); PETG's is ~80 °C. It also takes heat-set inserts better and gives the
the stands stronger layer adhesion.

| File | Qty | Size (mm) | ~Mass | Orientation |
|---|---|---|---|---|
| `shell.stl` | 1 | 149.4 × 97.5 × 18.9 | 58 g | back plate **down** |
| `case_bottom_pi4.stl` *or* `_pi5` | 1 | 126 × 76 × 13.5 | 23 g | plate **flat**, wall up |
| `case_top_pi4.stl` *or* `_pi5` | 1 | 95 × 71 × 19.9 | 36 g | outer face **down** (as exported) |
| `stand_20_usb.stl` | 1 | 82 × 42.3 × 14.0 | 9 g | **flat** on the profile |
| `stand_20_dsi.stl` | 1 | 82 × 42.3 × 14.0 | 9 g | **flat** on the profile |

`shell.stl` and the stands are the same for both boards — only `case_bottom`
and `case_top` are cut per model, and they must be a matching pair.

Pick one lean angle and print **both** files for it — one per side:

| Files | Lean | Stand size (mm) | Assembly depth on the desk |
|---|---|---|---|
| `stand_15_usb` + `stand_15_dsi` | 15° | 82.2 × 43.5 × 14.0 | 68.5 mm |
| `stand_20_usb` + `stand_20_dsi` | 20° | 82.0 × 42.3 × 14.0 | 73.9 mm |
| `stand_30_usb` + `stand_30_dsi` | 30° | 82.6 × 39.0 × 14.0 | 83.1 mm |

**The stands are handed** — `_usb` goes on the USB/Ethernet side, `_dsi` on the
ribbon side. They are mirror images, and an L-shaped profile has no mirror
symmetry in either axis, so no amount of turning one round will substitute for
the other. The screw holes sit 2.85 mm from the strap's inboard edge and
11.15 mm from its outboard one; fit the wrong one and the holes simply miss the
case screws by 8.3 mm, so the mistake is obvious rather than subtle.

Why not one symmetric part? The screw is at case X 51.85 and the case's −X wall
is at 48.5, so a symmetric strap could be at most 5.7 mm wide — narrower than
the Ø5.4 counterbore, which would leave the strap as a 1 mm web at both screws.

At every angle the foot stops **inside** the case's own silhouette (3.5 mm in at
15°, 21 mm at 30°), so the stand never sticks out behind the case; the depths
above are set by the leaning case, not by the foot.

Settings: 0.2 mm layer, 3 walls, 20 % infill, **no supports** — every part is
oriented so nothing overhangs beyond 45°.

The tolerances assume PETG. For PLA, drop `fit_clear` in `shell.py` from 0.5 to
0.4 mm.

## Choosing the board variant

Both boards are 85 × 56 mm on the same 58 × 49 mounting pattern, so the shell,
the stands and the whole screw stack are shared. What differs is the ports.
Connector positions were measured off the reference board models rather than
taken from the board drawings, and live in `pi_models.py`; both scripts derive
their openings from that one table, so the wall gap and the lid aperture cannot
drift apart.

| | Pi 4 | Pi 5 |
|---|---|---|
| USB / Ethernet order on the +X edge | USB2, USB3, Ethernet | Ethernet, USB3, USB2 |
| 3.5 mm audio jack | yes | none |
| Display FPC connector | −X short edge | **−Y long edge** (x 6.7…15.2) |
| Display FPC type | 15-pin | 22-pin (0.5 mm) |
| Tallest point above the PCB | 16.8 mm | 17.7 mm |
| Clearance under the lid | 3.20 mm | 2.26 mm |
| Works with the optional 40 mm fan | yes | only **without** the active cooler |

Build the pair for your board:

```bash
python case_bottom.py pi5 && python case_top.py pi5
```

### Read this before choosing a Pi 5

**Not built on hardware.** The Pi 4 case is assembled and in service; the Pi 5
variant is derived from the board model and checked in software only. Feedback
welcome.

**The display ribbon does not route the same way.** On the Pi 4 the DSI socket
is on the short edge nearest the display's own FPC, so the ribbon rises through
the bay and folds straight onto it over about 20 mm. The Pi 5 has nothing on
that edge — both its MIPI connectors are on the −Y long edge, roughly 45 mm
further along — so the ribbon has to run across the top of the board to reach
one. There is room above the PCB for it, but you will need a longer cable than
the panel's own, **and** a 22-to-15-pin adapter, since the Pi 5 uses the
narrower 22-pin FPC. Work this out before printing.

**The active cooler and the lid fan are mutually exclusive.** The cooler stands
20.90 mm above the case floor where the fan hangs at 17.40 mm — a 3.5 mm clash.
The cooler costs no lid height otherwise (it sits below the USB cans, which
still set the tallest point), so fit the cooler and leave the fan out. The
grille holes still vent.

## Hardware

| Item | Qty | Notes |
|---|---|---|
| M2.5 × 6+6 male-female standoff | 4 | extenders; relay the Pi mount plane past the case |
| M2.5 × 20 male-female standoff | 4 | clamp the Pi **and** take the lid screws |
| M2.5 × 6 screw | 4 | lid into the 20 mm standoffs |
| M2.5 × 16 screw | 4 | case screws: stand → case-bottom → shell → display |
| 40 × 40 × 10 mm 5 V fan | 1 | **optional** |
| M3 self-tapping screw | 4 | fan, from outside through the lid — optional |
| **Right-angle USB-C power lead** | 1 | see below — a straight one will foul the desk |

**No heat-set inserts and no soldering iron** — everything threads into a
standoff. Screw lengths are calculated from the stack-up; confirm the
M2.5 × 16 against your panel, since the thread depth of the display's own
screw bosses is not published.

The stands add only **1.0 mm** to the case-screw stack — the strap is 3 mm
thick but 2 mm of that is counterbore, so the head drops most of the way in.
The same M2.5 × 16 therefore still works, with about 10 mm of thread in the
display's boss instead of 11 mm. If yours feel short, go to × 18.

The Pi is **not** carried by the case. The display's four built-in 15.9 mm
standoffs carry it, via the extenders. One screw chain runs the whole stack:

```
display standoff → 6+6 extender → Pi → 20 mm standoff → lid screw
```

The 20 mm standoff length sets the case height (lid inner face lands at
Z 27.4, clearing the USB connector cans by 4 mm). Substituting a different
length means changing `standoff` in `case_top.py` and re-running it.

## Assembly

![Exploded assembly diagram](assembly_pi4.png)

The numbered callouts match the steps below. The diagram is generated from the
part STLs by `assembly_diagram.py`, so it cannot drift from the geometry —
re-run that script after changing any part.

1. Drop the display into the **shell** from the front. It is retained by the
   sandwich, not screwed to the shell.
2. Screw the four **M2.5 6+6 extenders** through the shell's back plate into the
   display's built-in standoffs (58 × 49 pattern).
3. Fit the **case-bottom** over the extenders, lay a **stand** on each side
   flange with its strut pointing down and back — `_usb` on the USB/Ethernet
   side, `_dsi` on the other — and run the four **case screws** (103.7 × 51
   pattern) through both into the display's screw bosses. Each stand's
   counterbore slots open toward the **middle** of the case; if they face
   outward you have the pair swapped. A driver reaches all four screws even with the
   Pi and lid fitted, provided the +X cables are unplugged, so you can change
   the lean angle later without taking the case apart.
4. Plug the **DSI ribbon** into the display, then seat the Pi on the extenders.
   The display's socket sits under the board, so bring the ribbon up through
   the bay, **wrap it around the board's DSI edge** and fold it onto the socket
   on the Pi's top face. Lay the slack **flat over the top of the Pi**. Do not
   bunch it underneath. *(Pi 5: the socket is on the long edge instead — run
   the ribbon across the top of the board to reach it.)*
5. Screw the four **M2.5 × 20 standoffs** down through the Pi's mounting holes
   into the extenders. These clamp the Pi and provide the lid's threads.
6. Optional: screw the **fan** to the lid from the outside (32 × 32 pattern).
7. Fit the **lid**. Line the four **sockets in the skirt** up with the four
   spigots on the wall top and press it down — the skirt seats on the wall and
   the spigots take up the side play. If it will not sit flush, a spigot has
   missed its socket; do not force it down with the screws. Then secure with
   four **M2.5 × 6** screws through the top face into the standoffs.

The spigots are a Ø3.0 pin in a Ø3.5 socket, so the lid can still shift about
0.25 mm before they bite — enough to assemble reliably in PETG, which prints
slightly proud. If yours end up too tight to seat, or too loose to feel like
they are doing anything, change `spigot_fit` in `case_top.py` and re-print the
lid; the pin is not affected.

## The stands

Each stand is an **L**: a flat strap that lies on the case-bottom's rear face
and carries both case screws, and a strut that leaves the strap's bottom end
and lies flat in the desk plane. There is deliberately **no diagonal brace**
between the two.

That absence is the whole design. A brace would have to cross the Pi's +X port
band, which is what sank the previous side-flange leg: its arm occupied
Z 2.5–11.5 while the USB and Ethernet **connector shells start at Z 6.65** —
0.75 mm *below* the PCB's top face, not level with it — so the bottom of every
plug fouled it. Here nothing crosses that band. The strap passes underneath it
(3 mm thick, clearing the plugs by 1.15 mm) and the strut stays outboard of it
in Y, by 4.9 mm at every angle.

Both members step in thickness, with the same 45° chamfer and the same 2:1
ratio. The strap is **3 mm across the port band and 6 mm past it**; the strut
is **9 mm at its root and 4.5 mm beyond 20 mm along the desk**. The strut's
bending moment is largest where it meets the strap and zero at the tip, so the
material out there was doing nothing — and thinning it also pulls the strut's
inner edge away from the plug band, which is what used to limit the 30°
variant to 2.9 mm of clearance. It can afford to be thin because the strut's root is itself a
desk contact — the toe touches down right where the strut meets the strap — so
the strut carries its load straight to the desk in compression and the strap
sees almost no bending. The thick section exists for the case where a print
tolerance lifts the toe slightly and the strap does have to take it.

Screw heads sit in **Ø5.4 × 2 mm counterbores**, which puts the head top at
Z 6.00 against the plugs at 6.65 even for a tall socket-cap head. The
counterbore is 0.7 mm wider than the head because it is a horizontal bore in
print orientation and its roof droops a little. Each counterbore is **opened
out through the strap's inboard edge**: the screw axis is only 2.85 mm from
that edge, so a plain circular pocket would leave a 0.15 mm fin standing 2 mm
tall, which would just break off. The head still lands on the full 1 mm floor,
and the Ø2.9 through-hole is what locates the screw.

Nothing here is compliant — no spring, no latch, no sustained strain — so
unlike the snap-on design it replaces, there is no creep to design around and
nothing whose grip depends on holding a 0.2 mm clearance.

**Releasing an Ethernet cable needs a small screwdriver.** The Pi 4's RJ45 jack
has its retention clip on the *underside*, and the strap passes 1.15 mm beneath
it, so there is no room for a fingertip — lift the clip with a thin blade
instead. Confirmed on hardware; easy enough, just not obvious. This is mostly
inherent to the case rather than the stand: with the strap removed entirely the
gap would only grow to 4.15 mm, because the case-bottom's own plate is at
Z 2.50. Both USB and Ethernet cables otherwise plug in and seat normally.

**Use a right-angle USB-C power lead.** The power socket faces down toward the
desk, and the case is deliberately low, so there is not much room beneath it:

| Lean | Room from the socket face to the desk |
|---|---|
| 15° | 17.4 mm |
| 20° | **16.6 mm** |
| 30° | 15.7 mm |

A straight plug's overmould plus the bend the lead needs before it can run flat
is typically longer than that, so it lands on the desk and lifts the case off
its stands. A right-angle lead turns immediately and clears easily. Note that
leaning **further back makes this worse, not better** — the socket gets closer
to the desk, not further from it.

This is the one place the 5-inch scale bites that the 7-inch original does not:
RonnyS's case is tall enough to swallow a straight plug. The alternative fix is
to lengthen the stands' straps, which raises the whole case — about 19 mm of
extension to gain 20 mm of room. That would actually *improve* the front tipping
margin (the toe moves down and forward faster than the centre of mass rises,
taking it from 12.0 to 18.2 mm at 20°), so it is a viable route if you would
rather not be tied to a particular lead. It is not the shipped geometry.

To change the lean angle, unplug the +X cables, undo the four case screws, swap
both stands and do them back up. The Pi and lid can stay where they are.

## Panel geometry

The **built-in Pi standoffs** — the four 15.9 mm towers on the panel's rear, in
the Pi's 58 × 49 pattern, which the extenders screw into — are **not centred**
on the panel. Measured on a real 5-inch unit:

- along the **long** axis: **34 mm** from the DSI/connector edge, 51.5 mm from
  the other (34 + 58 + 51.5 = 143.5)
- along the **short** axis: **21 mm** from each edge (21 + 49 + 21 = 91), i.e.
  centred

That gives `ext_off_x = -8.7`, `ext_off_y = 0` in `case_bottom.py` and
`shell.py`, placing the Pi board at x −41.2 … 43.8. Everything downstream — the
bay, the wall positions and the lid's port apertures — follows from it, so if
your panel measures differently, change those two values and re-run all three
scripts.

Do not confuse these with the **103.7 × 51 screw bosses**, which sit 5.5 mm
lower on the panel and take the case screws.

One consequence worth knowing: the display's DSI socket ends up *underneath*
the Pi board (2 mm from the Pi's own DSI socket), so the ribbon rises through
the bay, wraps around the board's DSI edge — there is 4.8 mm of bay past that
edge for the fold — and lands on the socket on the top face.

The DSI connector position (`ffc_x`) needs no check — the display's socket sits
essentially directly below the Pi's, and the bay clears it by 4.5–8.5 mm across
that range.

## Adjusting

Every part is a parametric CadQuery script; edit the `PARAMETERS` block and
re-run to regenerate the STL:

```bash
python shell.py
```

Useful knobs:

| Parameter | File | Effect |
|---|---|---|
| `tilts` | `stand.py` | which lean angles to export (default 15/20/30°) |
| `fit_clear` | `shell.py` | display pocket clearance (PETG 0.5, PLA 0.4) |
| `foot_len` | `stand.py` | stand depth — how far back the foot reaches |
| `foot_t`, `foot_t_thin`, `foot_step` | `stand.py` | strut thickness at the root, past the step, and where it steps |
| `strap_t_thin` | `stand.py` | strap under the port band — raising it eats the 1.15 mm plug gap |
| `grille_r`, `grille_pitch` | `case_top.py` | fan grille pattern |
| `spigot_fit` | `case_top.py` | lid socket clearance — how much play before the spigots bite |
| `port_clear`, `min_divider` | both | clearance around each connector, and the thinnest divider allowed |
| `bot_sill_clear` | `case_bottom.py` | how far the power/HDMI sill sits below the sockets |

**`bot_sill_clear` is the least certain number in the case.** Nothing here
measures how far a plug's overmould hangs below its socket, so it is set to a
deliberately generous **2.0 mm**, putting the sill top at Z 5.35 on a Pi 4 and
6.00 on a Pi 5.

One flat sill spans the whole opening, so this is the margin under the **lowest**
socket — the **USB-C** on both boards, which is the one to check first if
anything fouls. Every other port on that edge gets at least as much: on a Pi 4
the micro-HDMIs and the audio jack clear the sill by 2.65 mm. If a cable of
yours still will not seat, raise this value and re-print the case-bottom.

The USB/Ethernet sill needs no such margin (0.35 mm), since no plug ever reaches
it.

Port geometry is not edited directly: it comes from the measured tables in
`pi_models.py`. Correct a connector there and both parts follow.

`strap_x0` / `strap_x1` in `stand.py` must match `stand_strap_x0` and `half_x`
in `case_bottom.py` — they are the two ends of the flange the strap sits on.

The scripts carry assertions for the clearances that matter (ribbon, Pi
footprint versus the walls, screw ligaments, fan-screw versus grille), so a
parameter change that would cause a collision fails loudly instead of producing
a bad STL. `stand.py` additionally checks its whole profile against the Pi's
measured plug keepout at every tilt, allowing 2 mm for the one Pi-position
number never verified on a real panel.
