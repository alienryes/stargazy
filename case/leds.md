# LED bezel ring

An optional ring of addressable LEDs around the front bezel of the frame — 20
LEDs (6 top, 6 bottom, 4 each side) firing forward through a **continuous slot
per side** behind a single **translucent diffuser window ring printed into the
frame with the MMU** — a filleted band round the whole bezel (the straight sides
glow; the corners are a decorative inlay). Every LED contributes to an even
glowing border (not discrete dots). The LEDs sit **3 mm behind the window** so the light spreads and
there are no hotspots. Driven by the Pi (a **Pi 4** in this build; a Zero 2 W
works identically — see Wiring to the Pi), powered from the 5V supply. The
frame (`case_frame_v3.py` v3.1) is sized around a **10 mm-wide WS2812B strip** —
the outer footprint grew +4 mm/side (117.6×89.5 → 125.6×97.5) so the bezel band
can host the strip channel.

## Strip

- **BTF-LIGHTING WS2812B, 60 LEDs/m** (16.7 mm pitch), 5V, 10 mm-wide flex
  (≈ part `BTF-5V-60L-B`). IP30 (bare) is fine indoors.
- Only ~20 LEDs are used — cut from a 1 m / 60-LED reel with margin to spare.
- Measure the actual reel width; if it isn't 10 mm, change `strip_w` in
  `case_frame_v3.py` and re-export.

## Cut plan (4 segments)

WS2812B is cuttable at every LED (copper pads between each). Cut into four
straight segments, minding the data-flow arrow (DIN → DOUT):

| Segment | LEDs |
|---|---|
| Top | 6 |
| Right | 4 |
| Bottom | 6 |
| Left | 4 |

Chain them into **one continuous data path** around the ring. Join segments at
the corners with short flexible wire links carrying 3 conductors (5V, GND, and
DOUT → DIN of the next segment).

**Corner link length: cut ≈ 45 mm** (finishing ~40 mm installed), the same for
all four corners. The link doesn't run straight — it follows the L-trench from
the last LED pad, round the **outboard side of the corner screw**, into the next
channel (~33–35 mm routed), plus a few mm each end for strip/tin and a little
slack to seat without tension. Cut all three conductors the same, but **stagger
the solder joints** (don't line them up) so the bundle stays under ~3 mm and
tucks into the trench. Best confirmed on the printed frame: lay a segment in
each channel and measure pad-to-pad round the corner before cutting all four.

Solder the **whole ring — four segments plus
corner links — as one loop first**, then fit it (see Fitting the strip): the
frame's **corner trenches are open to the back** (they route round the outboard
side of each corner screw), so the pre-soldered assembly lays straight in and
lifts back out. Keep the arrow direction consistent all the way round.

## Printing the frame (2-material, MMU)

The diffuser windows are printed **into** the frame, so it is a two-material
MMU print:

- `case_frame_v3.stl` — the frame, in the main (opaque) filament.
- `case_frame_v3_window.stl` — the diffuser window ring (0.8 mm), in **white
  or natural translucent** filament.

In PrusaSlicer: load `case_frame_v3.stl`, then right-click → **Add part** →
`case_frame_v3_window.stl` (it lands already aligned in the frame). Assign the
windows part to the translucent extruder. Print bezel-face down as usual; a
wipe/purge tower is added for the colour change.

## Fitting the strip

1. Cut the four segments and solder them into one loop with the corner links
   (see Cut plan above) — do this **before** fitting, not in place.
2. From the **back** of the frame, lay the loop in: each segment drops into its
   side channel, seating against the front-stop shoulder **3 mm behind the
   diffuser window** (the snap tabs hold it), and each corner link lays into the
   open corner trench round the outboard side of the screw.
3. The strip tail (3 wires) exits via the **bottom cable slot**, alongside the
   Pi's power lead.

## Wiring to the Pi

The **data** line plus the strip's **5V and GND** all come from the GPIO
splitter (see Power) — the ring is powered from the Pi's 5V rail via the
splitter, and nothing is soldered to the Pi's pads. LED current does share the
Pi's supply, so isolation is a *software* guarantee: the `LED_BRIGHTNESS` cap
keeps the whole ring under ~0.3 A (see Power).

**Why GPIO19 (pin 35, PWM1).** `rpi_ws281x` can drive the strip from PWM, PCM or
SPI, but its SPI channel is **SPI0 MOSI (GPIO10) only** — and the Inky already
owns SPI0 (MOSI/SCLK/CE0). So the SPI method is out **on every board, Pi 4
included**; the spare SPI3–SPI6 buses on a Pi 4 exist but this library cannot
use them. That leaves PWM: GPIO19 is unused by the Inky *and* both its
neighbours (pins 33/37) are free, so it is forgiving to land on.

| Strip wire | Connect to |
|---|---|
| DIN (data) | GPIO19 — pin 35, PWM1 (add a 74AHCT125 level shifter if it glitches) |
| +5V / GND | 5V and GND pins on the splitter's horizontal branch — see Power |

### Getting at the header (GPIO splitter)

The Inky covers the whole 40-pin header, so the data lead needs somewhere to go.
Use a **1-to-2 40-pin GPIO edge adapter** (GeeekPi, ~£8) — a passive fanout that
sits on the Pi's header and re-presents the same 40 pins twice: once as a
vertical stacking header, once as a horizontal edge header. The Inky goes on the
vertical branch, the LED data lead plugs into the horizontal one.

This replaces tack-soldering to the ~2 mm of Pi pin left exposed above the
Inky's low-profile socket. It also keeps the LED loop **removable**, which is
the whole point of the frame's open-to-back corner trenches (see Fitting the
strip) — the ring lifts out without desoldering anything.

Before plugging anything in:

1. **Meter the pin order on the horizontal branch.** These adapters sometimes
   mirror or reverse numbering relative to the vertical header. Check known pins
   (3V3 on pin 1, 5V on pins 2/4, GND on pin 6) against the vertical branch
   first — **reversed 5V/GND kills the Pi.** This is the hard gate before
   connecting the strip's power; do it with a working meter.
2. **The strip's 5V/GND come off this branch (topology A).** LED current *does*
   pass through the splitter, so keep the ring capped: at blue/purple, capped
   brightness the whole ring is <0.3 A, which the adapter's traces carry easily.
   Never drive sustained full white (~1.2 A) — that cap is the software
   isolation guarantee doing the job the Wago used to (see Power).

### Pi 4 (this build)

The Pi 4 is 85 × 56 mm with tall connectors and does **not** fit the frame's
PCB pocket, so it mounts externally behind the riser. The Inky therefore can't
sit on the vertical branch directly — the chain is:

```
Pi 4 → GPIO splitter → 40-pin ribbon → Inky
                     └→ LED data (GPIO19) + GND
```

Keep the ribbon as short as practical: it adds unterminated stub to SPI0, which
the Inky shares. The Inky clocks slowly so this should be fine — if refreshes
come out corrupted, shorten the ribbon before suspecting anything else.

### Zero 2 W (alternative)

Everything above applies unchanged except the mounting: the Zero 2 W hides
behind the Inky on the header, inside the frame pocket, so no ribbon is needed
and the splitter's added ~10–12 mm of stack has to fit the 16 mm pocket — check
it before committing. Without the splitter, the original approach still works:
tin the wire and tack it to the ~2 mm of GPIO19 pin exposed above the Inky's
socket, then pot it in hot glue for strain relief.

### PWM and onboard audio

`rpi_ws281x` on a PWM channel conflicts with the Pi's onboard analog audio,
which uses the same PWM hardware. Add `dtparam=audio=off` to
`/boot/firmware/config.txt` if the LEDs misbehave. This applies to the Pi 4 and
the Zero 2 W equally — neither board is advantaged here. Driving PWM also needs
root / `/dev/mem` (see Pi software).

### Wire gauge

Current is tiny at the capped blue/purple brightness (<0.3 A for the whole ring;
even theoretical full-white is only ~1.2 A), so choose wire for flexibility and
solderability, not ampacity. Use flexible **silicone**-insulated stranded — it
bends easily, is high strand-count, and won't shrink back when soldered:

| Run | Gauge |
|---|---|
| Corner jumpers (segment→segment; 5V/GND/data) | **26 AWG** — lays into the 3 mm corner trenches, solders to the small pads |
| Tail 5V + GND (to the splitter header) | **26 AWG** — fine at this current; crimp/solder to a DuPont header. (Use **24 AWG** for Option B: 26 AWG is at/below the Wago 221's 0.14 mm² fine-stranded clamp floor) |
| Tail data (GPIO19) | 26 AWG |

Keep the corner links short so they sit in the trenches. Voltage drop is
negligible (~60 mV even at 1.2 A over the ~0.4 m perimeter).

### Power topology — DECIDED: option A (5V off the splitter)

**Decided 2026-07-20: option A.** The Wago architecture (Option B, below) was
designed for a Zero 2 W on a 2 A supply, where the ring's worst case genuinely
threatened the budget. On the Pi 4 with a 3 A supply that is over-engineering —
worst case is Pi ~1.2 A + full-white ring ~1.2 A = ~2.4 A, which fits. The
splitter has arrived and the Inky seats on its vertical branch as expected.

- Supply plugs into the **Pi's USB-C port normally** — nothing cut, no breakout,
  no pigtail, no Wagos.
- The strip takes **5V, GND and data all from the splitter's horizontal branch**
  (5V pin 2/4, a GND pin, GPIO19 data on pin 35).
- Isolation is a **software** guarantee: the `LED_BRIGHTNESS` cap (≤ 128, running
  ~80) keeps the ring under ~0.3 A, so LED current through the Pi's 5V rail and
  the splitter stays trivial. **Never sustained full white.**
- **Gate:** meter the splitter's horizontal-branch pin order first (see Getting
  at the header) — reversed 5V/GND kills the Pi.

Option B (Wago isolation) is kept below as the rejected alternative — reach for
it only if you ever want LED current physically off the Pi (e.g. running the
ring bright).

### Power wiring (option A, this build)

The 5V supply plugs straight into the Pi; the strip draws 5V/GND/data from the
splitter. That is the whole of it — no cutting, breakout, pigtail or Wagos.

1. Plug the **5V supply into the Pi's USB-C port** as normal. (This build's
   supply is a 5.1V/5 A USB-PD brick — it delivers the 5V default profile with
   no negotiation, which is all the Pi 4 needs; see the budget note below.)
2. **Meter the splitter's horizontal-branch pin order** (see Getting at the
   header) before connecting anything — reversed 5V/GND kills the Pi.
3. Strip **5V** → a 5V pin on the horizontal branch (pin 2 or 4).
   Strip **GND** → a GND pin (6/9/14/20/25/30/34/39).
   Strip **DIN** → **GPIO19, pin 35**.
4. Ground is common through the shared header, so the GPIO19 → DIN data line has
   its reference.

Budget, and **the supply must match the board**:

| Board | Pi draw | + ring (capped) | Supply needed |
|---|---|---|---|
| Zero 2 W | ~0.7 A | <0.3 A | 5V / 2 A — the Stontronics is fine |
| **Pi 4** | up to ~1.2 A typical, 3 A rated | <0.3 A | **5V / 3 A minimum — the Stontronics 2 A is NOT enough** |

The Pi 4 is specified at 5V/3 A, so a 2 A adapter would risk brownouts under load
(SD corruption, undervoltage throttling). This build uses a **5.1V/5 A USB-PD**
supply (label lists 5.1/9/12/15 V profiles — multiple fixed profiles means true
PD). Its 5 A mode needs PD negotiation, but the Pi only ever draws the 5V default
profile, so **budget 5V/3 A**. That clears the ~1.5 A typical (Pi + capped ring)
comfortably, and even the ~2.4 A theoretical worst case fits.

- **Brightness cap ≤ 128 / 255** (`LED_BRIGHTNESS`, see below). Under topology A
  this cap is the *only* thing keeping LED current off the Pi's rail modest, so
  it matters more than ever: never drive sustained full white on all 20 — both
  for the current budget and because the heat would risk softening/warping the
  PLA case (glass transition ~60 °C). Low-brightness blue/purple runs cool and
  draws <0.3 A.
- GPIO19 data is 3.3V; WS2812B officially wants 5V logic. Short runs often work
  direct — add the 74AHCT125 level shifter if the first few LEDs flicker.

### Option B — Wago isolation (alternative, not used)

Kept for reference. Physically isolates LED current from the Pi, at the cost of a
USB-C breakout, a male pigtail and two Wago 221s. Reach for it only if you ever
want to run the ring bright enough that its current shouldn't share the Pi's
rail. A single 5V adapter feeds both, split at two **Wago 221** lever connectors:

1. Get bare 5V/GND from the adapter:
   - **USB-C supply: do NOT cut the cable.** A USB-C source will not enable VBUS
     until it sees 5.1 kΩ Rd pulldowns on the CC pins — cutting the plug off
     removes that termination and you get nothing (and a ruined supply). Use a
     **USB-C breakout board with the CC resistors fitted** (Pi Hut, £2.60) and
     take 5V/GND from its screw terminals.
   - **Micro-USB supply (Zero 2 W):** cut the plug off to expose bare 5V/GND.
2. **Meter the polarity** before connecting anything (don't trust colours) —
   reversed 5V kills the Pi. Insulate any unused conductors (D+/D-, shield).
3. **5V Wago** (3-way): adapter 5V → Pi + strip 5V.
   **GND Wago** (3-way): adapter GND → Pi + strip GND.
4. Feed the Pi from the Wagos via a **male pigtail** back into its power port
   (the breakout and the Pi's port are both receptacles) — USB-C for the Pi 4,
   micro-USB for the Zero 2 W (keeps the Pi's input polyfuse in circuit). The
   pigtail needs no CC resistors — VBUS is injected directly, nothing
   negotiates. Meter its polarity too. The 221 is rated 32 A, hugely over-spec.

## Pi software (not yet implemented)

Outline for a follow-up change to `display.py`:

- Install `rpi_ws281x` (`sudo pip install rpi_ws281x`, or apt
  `python3-rpi-ws281x`).
- Drive the strip on **PWM1 / GPIO19** (needs root / `/dev/mem`).
- 20 pixels; set a **global brightness ceiling** ≤ 128 (see Power). ~40–80
  gives a pleasant ambient glow.
- Keep to the **blue/purple range** to match the Inky palette and stay cool.
- Hook LED updates into the display refresh — e.g. colour by tonight's deep-sky
  verdict, or a slow idle twinkle.

```python
from rpi_ws281x import PixelStrip, Color

LED_COUNT      = 20
LED_PIN        = 19        # GPIO19 (PWM1), pin 35
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_BRIGHTNESS = 80        # global scale; hard ceiling 128 (see Power budget)
LED_CHANNEL    = 1        # PWM1 (GPIO13/19); PWM0 pins would use 0

strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA,
                   False, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()
for i in range(LED_COUNT):
    strip.setPixelColor(i, Color(30, 0, 60))   # blue/purple, Color(r, g, b)
strip.show()
```

The pixel index → physical position mapping depends on where you start the data
chain and the segment join order — map it once when wired.
