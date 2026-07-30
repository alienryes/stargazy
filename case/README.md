# Case — Raspberry Pi Touch Display 2 (5") + Raspberry Pi 4

A 3D-printable desk case for the **5-inch** Raspberry Pi Touch Display 2 with a
Raspberry Pi 4 mounted behind it, used landscape. Four printed parts, an
easel stand at a 20° lean, and an optional 40 mm fan.

## Credits and licence

This is a **remix of "Raspberry Pi Touch Display 2 Case" by RonnyS** —
<https://www.printables.com/model/1377047-raspberry-pi-touch-display-2-case> —
used under **CC BY**. The original targets the **7-inch** panel (its shell
pocket is 187 × 118 mm, matching the 7-inch outline of 189.32 × 120.24 mm); the
5-inch panel is 91.46 × 143.4 mm, so none of the original parts fit it. The
architecture is RonnyS's — shallow shell, bolt-on Pi clamshell, swappable
stand, optional fan — re-drawn parametrically in CadQuery at 5-inch scale.

This remix is released under **CC BY** as well. Credit RonnyS and this project.

The Raspberry Pi 4B model shown in the assembly diagram is by
**Pyro_Industries** — <https://www.printables.com/model/727545-raspberry-pi-4>,
CC0. It is used for illustration only and is not redistributed here.

Differences from the original, beyond scale:

- **No lid towers and no heat-set inserts.** The original bolts its lid to four
  M3-insert towers on the case-bottom, which forces a wider lid and a second
  screw chain. Here the lid screws into M2.5 male-female standoffs sitting on
  the Pi's own mounting holes, so one chain runs the whole stack and the lid
  continues the case-bottom's wall profile instead of straddling it.
- The fan is **hung off the lid** instead of a separate Pi-mounted bracket —
  a Pi-mounted plate plus fan does not fit the 5-inch stack's headroom.
  Note the fan clears the GPIO header by only 1.5 mm; check it on the real
  thing before relying on it.
- **The legs snap on instead of screwing on.** The original bolts each leg
  through the case-bottom with two self-tapping screws. One of those screws
  lands inside the leg's own lightening void, where the foot rib blocks a
  driver coming straight in, so it cannot be reached once the leg is in place.
  Here the legs slide onto ribs and latch, which removes four screws and the
  access problem together, and makes swapping to a different lean angle a
  ten-second job.
- The shell keeps **discrete pass-through holes** for the standoffs rather than
  one large rear opening. On the 5-inch panel the case-screw bosses (y ±25.5)
  and the display's own Pi standoffs (y ±28.5) fall in the same band, so an
  opening big enough to clear the standoffs would swallow the screw bosses.
- No wall/V-slot brackets, no Pi 3/Pi 5 variants.

## Parts and printing

Print in **PETG**. An enclosed Pi 4 can creep toward PLA's glass transition
(~60 °C); PETG's is ~80 °C. It also takes heat-set inserts better and gives the
stand legs stronger layer adhesion.

| File | Qty | Size (mm) | ~Mass | Orientation |
|---|---|---|---|---|
| `shell.stl` | 1 | 149.4 × 97.5 × 18.9 | 58 g | back plate **down** |
| `case_bottom.stl` | 1 | 129 × 76 × 10.5 | 21 g | plate **flat**, wall up |
| `case_top.stl` | 1 | 95 × 64 × 19.9 | 33 g | outer face **down** (as exported) |
| `stand_20.stl` | **2** | 93 × 56.4 × 8 | 14 g ea | **flat** on the profile |

Pick one leg file and print two of it. The legs are interchangeable, so you can
print a second pair at a different angle and swap them without touching the
rest of the case:

| File | Lean | Depth on the desk |
|---|---|---|
| `stand_15.stl` | 15° | 58 mm |
| `stand_20.stl` | 20° | 56 mm |
| `stand_30.stl` | 30° | 52 mm |

The legs are the same part left and right — nothing is handed, and nothing is
mirrored.

Settings: 0.2 mm layer, 3 walls, 20 % infill, **no supports** — every part is
oriented so nothing overhangs beyond 45°.

The tolerances assume PETG. For PLA, drop `fit_clear` in `shell.py` from 0.5 to
0.4 mm.

## Hardware

| Item | Qty | Notes |
|---|---|---|
| M2.5 × 6+6 male-female standoff | 4 | extenders; relay the Pi mount plane past the case |
| M2.5 × 20 male-female standoff | 4 | clamp the Pi **and** take the lid screws |
| M2.5 × 6 screw | 4 | lid into the 20 mm standoffs |
| M2.5 × 16 screw | 4 | case screws: case-bottom → shell → display |
| 40 × 40 × 10 mm 5 V fan | 1 | **optional** |
| M3 self-tapping screw | 4 | fan, from outside through the lid — optional |

**No heat-set inserts and no soldering iron** — everything threads into a
standoff. Screw lengths are calculated from the stack-up; confirm the
M2.5 × 16 against your panel, since the thread depth of the display's own
screw bosses is not published.

The Pi is **not** carried by the case. The display's four built-in 15.9 mm
standoffs carry it, via the extenders. One screw chain runs the whole stack:

```
display standoff → 6+6 extender → Pi → 20 mm standoff → lid screw
```

The 20 mm standoff length sets the case height (lid inner face lands at
Z 27.4, clearing the USB connector cans by 4 mm). Substituting a different
length means changing `standoff` in `case_top.py` and re-running it.

## Assembly

![Exploded assembly diagram](assembly.png)

The numbered callouts match the steps below. The diagram is generated from the
part STLs by `assembly_diagram.py`, so it cannot drift from the geometry —
re-run that script after changing any part.

1. Drop the display into the **shell** from the front. It is retained by the
   sandwich, not screwed to the shell.
2. Screw the four **M2.5 6+6 extenders** through the shell's back plate into the
   display's built-in standoffs (58 × 49 pattern).
3. Fit the **case-bottom** over the extenders and secure the four **case screws**
   (103.7 × 51 pattern) down into the display's screw bosses.
   **Do this before fitting the Pi** — the Pi's USB corner sits over the
   right-hand pair with only 3.5 mm of clearance, and a driver will not reach.
4. Plug the **DSI ribbon** into the display, then seat the Pi on the extenders.
   The display's socket sits under the board, so bring the ribbon up through
   the bay, **wrap it around the board's DSI edge** and fold it onto the socket
   on the Pi's top face. Lay the slack **flat over the top of the Pi**. Do not
   bunch it underneath.
5. Screw the four **M2.5 × 20 standoffs** down through the Pi's mounting holes
   into the extenders. These clamp the Pi and provide the lid's threads.
6. Optional: screw the **fan** to the lid from the outside (32 × 32 pattern).
7. Fit the **lid** — its skirt seats on the case-bottom's wall — and secure with
   four **M2.5 × 6** screws through the top face into the standoffs.
8. Fit a **stand leg** to each side flange. Lay it on the flange about 5 mm
   below its final position, so the three ribs sit in the leg's slots, then
   **slide it up** until the tongue clicks. No screws.

## The legs

The legs take no fasteners. Each one slides onto three ribs moulded into the
rear face of the case-bottom's side flange: two half-dovetails that capture the
leg, and a bump that latches it.

The leg slides **up** to engage, which is the same direction the case's own
weight pushes it — so sitting on the desk seats the joint harder rather than
working it loose. Two spread-apart dovetails stop the leg being pulled off the
face or pivoting away at either end.

**The taper is the clamp, and it is the whole retention mechanism.** Each rib's
slant leans toward the bottom of the case as it rises, and the leg's lip bears
on it from underneath, so pushing the leg up drives the lip along the slant and
the reaction pulls the leg hard onto the flange. Push harder, grip harder. The
friction that results is what stops it sliding back down — and the case's own
weight pushes in the engaging direction anyway.

A wedge is also the only feature here that shrugs off print tolerance: whatever
slack your printer leaves, the leg just slides a fraction further until it
grips. **The corollary is that nothing else may stop the slide.** The bump and
tongue are therefore a *backstop only*, held slack by 1 mm at both ends so they
can never become the up-stop. They exist to catch the leg if the wedge ever
relaxes, not to hold it.

`slant_fit` in `stand.py` (0.05 mm) is the grip. Smaller grips harder; negative
is a light interference that the lip deflects over, which guarantees a clamp
even on a loose printer. It lives entirely in the leg — the flange ribs do not
change — so you can print legs at two or three values and pick by feel without
reprinting anything else.

**To remove a leg, push it firmly back down** — roughly the same effort it took
to click on. There is no press-to-release tab, deliberately: once a leg is on,
its tongue's back face is against the case, so a tab there would be
unreachable. Sliding it off is the only action you can actually perform.

Note the legs pass right over the four M2.5 case-screw heads, which stand off
that same rear face. The flange is sized so they clear by 0.65 mm — if you
substitute screws with heads wider than 4.7 mm, move `cleat_x` outboard in both
`case_bottom.py` and `stand.py` or the legs will rock.

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
| `fit`, `slant_fit` | `stand.py` | how tight the legs snap on |
| `grille_r`, `grille_pitch` | `case_top.py` | fan grille pattern |

The cleat parameters (`cleat_x`, `cleat_span_y`, `rib_t`, `rib_h`, `rib_flare`,
`detent_y`, `detent_h`) appear in **both** `case_bottom.py` and `stand.py` and
must agree — they are two halves of one joint. `stand.py` re-derives the
detent's flex force and strain from them on every run and refuses to build a
tongue that would be limp, unassemblable, or overstrained.

The scripts carry assertions for the clearances that matter (ribbon, Pi
footprint versus the walls, screw ligaments, fan-screw versus grille), so a
parameter change that would cause a collision fails loudly instead of producing
a bad STL.
