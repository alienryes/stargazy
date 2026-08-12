# Bill of materials — Touch Display 2 (5") case

Everything needed to build the case, in one list. Design reasoning, assembly
order and the parameters behind these figures are in [`README.md`](README.md).

## Two choices to make first

Both affect which files are printed, and neither can be changed by editing the
list below.

**Board variant — Pi 4 or Pi 5.** The shell and the stands are shared; only
`case_bottom` and `case_top` are cut per board, and they must be a matching
pair. The Pi 5 additionally needs a display adapter cable.

**Lean angle — 15°, 20° or 30°.** Two stand files per angle, one per side. 20°
is the default. The 30° pair is the marginal one for rear tipping margin; see
the README before choosing it.

## Printed parts

PETG, 0.2 mm layer, 3 walls, 20 % infill, **no supports** — every part is
oriented so nothing overhangs beyond 45°.

| File | Qty | Size (mm) | Orientation | ~Mass |
|---|---|---|---|---|
| `shell.stl` | 1 | 149.4 × 97.5 × 18.9 | back plate **down** | 58 g |
| `case_bottom_pi4.stl` *or* `case_bottom_pi5.stl` | 1 | 126 × 76 × 13.5 | plate **flat**, wall up | 23 g |
| `case_top_pi4.stl` *or* `case_top_pi5.stl` | 1 | 95 × 71 × 19.9 | outer face **down** (as exported) | **27.6 g** |
| `stand_<angle>_usb.stl` | 1 | 105.4 × 42.3 × 14.0 at 20° | **flat** on the profile | 11 g |
| `stand_<angle>_dsi.stl` | 1 | 105.4 × 42.3 × 14.0 at 20° | **flat** on the profile | 11 g |

Only `case_top` has been sliced and weighed — **27.6 g in PETG, 1 h 23 min** at
the settings above. The other three masses are estimates from model volume and
run high: the same estimate for the lid was 36 g, about 30 % over. They are not
corrected by that ratio, because the proportion of sparse infill depends on the
part's size, so a figure taken from one part does not transfer to another.

Total filament is therefore around **130 g**, and likely less.

The stands are handed: `_usb` goes on the USB/Ethernet side, `_dsi` on the
ribbon side. They are mirror images and cannot substitute for one another.

For PLA, drop `fit_clear` in `shell.py` from 0.5 to 0.4 mm before slicing. PETG
is preferred — an enclosed Pi 4 can creep toward PLA's glass transition.

## Fasteners

| Item | Qty | Purpose |
|---|---|---|
| M2.5 × 6+6 male-female standoff | 4 | extenders; relay the Pi mount plane past the case |
| M2.5 × 20 male-female standoff | 4 | clamp the Pi and take the lid screws |
| M2.5 × 6 screw | 4 | lid into the 20 mm standoffs |
| M2.5 × 16 screw | 4 | case screws: stand → case-bottom → shell → display |

**No heat-set inserts and no soldering** — everything threads into a standoff.

The M2.5 × 16 length is calculated from the stack-up rather than measured, since
the thread depth of the display's own screw bosses is not published. Confirm it
against the panel in hand; if the screws feel short, go to × 18.

## Electronics and cables

| Item | Qty | Notes |
|---|---|---|
| Raspberry Pi Touch Display 2, 5-inch | 1 | 91.46 × 143.4 mm panel |
| Raspberry Pi 4 or Pi 5 | 1 | must match the printed `case_bottom` / `case_top` pair |
| USB-C power supply | 1 | the official Raspberry Pi PSU fits — the stands lift the case 22 mm specifically so it does |
| Display Adapter Cable for Pi 5, 22-way → 15-way | 1 | **Pi 5 only.** Replaces the panel's own cable |

The Pi 5 adapter cable is a single part, not a cable plus an adapter, and is
sold in 200 / 300 / 500 mm lengths — measure the routing before choosing, as the
run climbs through the bay and then crosses the board. It must be the one
printed `DISPLAY`; camera adapter cables fit the same connectors and look nearly
identical.

## Optional — 40 mm fan

| Item | Qty | Notes |
|---|---|---|
| 40 × 40 × 10 mm 5 V fan | 1 | hangs off the lid, 32 × 32 screw pattern |
| M3 self-tapping screw | 4 | through the lid from outside |

The fan clears a Pi 4's GPIO header by only 1.10 mm; check it against the real
board before relying on it. It does **not** clear a Pi 5 active cooler — the
two are mutually exclusive, and the cooler is the one to keep. The lid's grille
holes still vent without a fan fitted.

## Tools

- Driver for M2.5 screws
- A thin blade or small screwdriver, to release an Ethernet cable after
  assembly — the RJ45 clip is on the underside of the jack and the stand's strap
  passes 1.15 mm beneath it, leaving no room for a fingertip
