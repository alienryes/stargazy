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

Differences from the original, beyond scale:

- The fan is **hung off the lid** instead of a separate Pi-mounted bracket.
  On the 5-inch stack the gap between the Pi's GPIO header and the lid is
  13.6 mm; a bracket plus fan needs 12.5 mm, leaving ~0.5 mm a side — too tight
  to print reliably. Lid-mounting gives 3.6 mm of clearance.
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
| `case_bottom.stl` | 1 | 126 × 76 × 23 | 23 g | plate **flat**, wall up |
| `case_top.stl` | 1 | 106 × 81 × 24 | 46 g | outer face **down** |
| `stand.stl` | **2** | 93 × 56.4 × 8 | 16 g ea | **flat** on the profile |

Settings: 0.2 mm layer, 3 walls, 20 % infill, **no supports** — every part is
oriented so nothing overhangs beyond 45°.

The tolerances assume PETG. For PLA, drop `fit_clear` in `shell.py` from 0.5 to
0.4 mm.

## Hardware

| Item | Qty | Notes |
|---|---|---|
| M2.5 × 6+6 male-female standoff | 4 | extenders; relay the Pi mount plane past the case |
| M2.5 × 6 screw | 4 | Pi onto the extenders |
| M2.5 × 16 screw | 4 | case screws: case-bottom → shell → display |
| M2.5 × 10 screw | 4 | stand legs onto the case-bottom flanges |
| M3 × 12 screw | 4 | lid onto the case-bottom towers |
| M3 heat-set insert | 4 | case-bottom towers (e.g. Ruthex RX-M3×5.7) |
| 40 × 40 × 10 mm 5 V fan | 1 | **optional** |
| M3 self-tapping screw | 4 | fan, from outside through the lid — optional |

Screw lengths are calculated from the stack-up; confirm the M2.5 × 16 against
your panel, since the thread depth of the display's own screw bosses is not
published.

The Pi is **not** carried by the case. The display's four built-in 15.9 mm
standoffs carry it, via the extenders.

## Assembly

1. Press the four **M3 inserts** into the case-bottom's corner towers.
2. Drop the display into the **shell** from the front. It is retained by the
   sandwich, not screwed to the shell.
3. Screw the four **M2.5 6+6 extenders** through the shell's back plate into the
   display's built-in standoffs (58 × 49 pattern).
4. Fit the **case-bottom** over the extenders and secure the four **case screws**
   (103.7 × 51 pattern) down into the display's screw bosses.
   **Do this before fitting the Pi** — the Pi's USB corner sits over the
   right-hand pair with only 3.5 mm of clearance, and a driver will not reach.
5. Plug the **DSI ribbon** into the display, then seat the Pi on the extenders
   and secure it. The display's socket sits under the board, so bring the
   ribbon up through the bay, **wrap it around the board's DSI edge** and fold
   it onto the socket on the Pi's top face. Lay the slack **flat over the top
   of the Pi** — there is 22 mm of headroom there. Do not bunch it underneath.
6. Optional: screw the **fan** to the lid from the outside (32 × 32 pattern).
7. Fit the **lid** and secure with the four M3 screws.
8. Bolt a **stand leg** to each side flange with two M2.5 screws.

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
| `tilt` | `stand.py` | stand lean angle (default 20°) |
| `fit_clear` | `shell.py` | display pocket clearance (PETG 0.5, PLA 0.4) |
| `foot_len` | `stand.py` | stand depth — how far back the foot reaches |
| `grille_r`, `grille_pitch` | `case_top.py` | fan grille pattern |

The scripts carry assertions for the clearances that matter (ribbon, Pi
footprint versus the walls, screw ligaments, fan-screw versus grille), so a
parameter change that would cause a collision fails loudly instead of producing
a bad STL.
