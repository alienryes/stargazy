# LED bezel ring

An optional ring of addressable LEDs around the front bezel of the frame — 20
LEDs (6 top, 6 bottom, 4 each side) firing forward through a **continuous slot
per side**, each filled by a **translucent diffuser window printed into the
frame with the MMU**, so every LED contributes to an even glowing border (not
discrete dots). The LEDs sit **3 mm behind the window** so the light spreads and
there are no hotspots. Driven by the Pi Zero, powered from the 5V supply. The
frame (`case_frame_v2.py` v3.0) is sized around a **10 mm-wide WS2812B strip** —
the outer footprint grew +4 mm/side (117.6×89.5 → 125.6×97.5) so the bezel band
can host the strip channel.

## Strip

- **BTF-LIGHTING WS2812B, 60 LEDs/m** (16.7 mm pitch), 5V, 10 mm-wide flex
  (≈ part `BTF-5V-60L-B`). IP30 (bare) is fine indoors.
- Only ~20 LEDs are used — cut from a 1 m / 60-LED reel with margin to spare.
- Measure the actual reel width; if it isn't 10 mm, change `strip_w` in
  `case_frame_v2.py` and re-export.

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
DOUT → DIN of the next segment). The frame's **corner tunnels run at strip
level**, so each link threads straight through the corner in the strips' plane —
no bending back to the rear. Keep the arrow direction consistent all the way
round.

## Printing the frame (2-material, MMU)

The diffuser windows are printed **into** the frame, so it is a two-material
MMU print:

- `case_frame_v2.stl` — the frame, in the main (opaque) filament.
- `case_frame_v2_windows.stl` — the four diffuser windows (0.8 mm), in **white
  or natural translucent** filament.

In PrusaSlicer: load `case_frame_v2.stl`, then right-click → **Add part** →
`case_frame_v2_windows.stl` (it lands already aligned in the slots). Assign the
windows part to the translucent extruder. Print bezel-face down as usual; a
wipe/purge tower is added for the colour change.

## Fitting the strip

1. Cut and chain the four segments (see Cut plan above).
2. From the **back** of the frame, drop each LED strip segment into its side
   channel. It seats against the front-stop shoulder, **3 mm behind the diffuser
   window**; the snap tabs hold it there.
3. Route the corner links through the corner tunnels.
4. The strip tail (3 wires) exits via the **bottom cable slot**, alongside the
   Pi's power lead.

## Wiring to the Pi

Only the **data** line touches the Pi header — power and ground reach the strip
from a Wago junction off the supply (see Power), so no LED current flows through
the Pi and nothing is soldered to its power pads. Data **must** be GPIO18: the
Inky already uses the SPI pins (MOSI/SCLK/CE0), so the SPI LED method is
unavailable. Solder the one data lead to the GPIO18 pin tail (accessible from
the Pi's back **before** the riser is fitted).

| Strip wire | Connect to |
|---|---|
| DIN (data) | GPIO18 — pin 12 (add a 74AHCT125 level shifter if it glitches) |
| +5V / GND | Wago junction off the 5V supply (not the Pi) — see Power |

### Wire gauge

Current is tiny at the capped blue/purple brightness (<0.3 A for the whole ring;
even theoretical full-white is only ~1.2 A), so choose wire for flexibility and
solderability, not ampacity. Use flexible **silicone**-insulated stranded — it
bends easily, is high strand-count, and won't shrink back when soldered:

| Run | Gauge |
|---|---|
| Corner jumpers (segment→segment; 5V/GND/data) | **26 AWG** — threads the 4 mm tunnels, solders to the small pads |
| Tail 5V + GND (into the Wago) | **24 AWG** — 26 AWG is at/below the Wago 221's 0.14 mm² fine-stranded clamp floor |
| Tail data (GPIO18) | 26 AWG |

Keep the corner links short so they tuck into the tunnels. Voltage drop is
negligible (~60 mV even at 1.2 A over the ~0.4 m perimeter).

### Power (this build)

A **Stontronics 5V / 2A** adapter feeds both the Pi and the strip, split at two
**Wago 221** lever connectors so the LED current never passes through the Pi
(and nothing is soldered to the Pi's power pads). There is room in the frame for
the Wagos.

1. Cut the adapter's micro-USB plug off to expose bare 5V/GND.
2. **Meter the polarity** of the bare wires (don't trust colours) — reversed 5V
   kills the Pi. Insulate any unused conductors (D+/D-, shield).
3. **5V Wago** (3-way): adapter 5V → Pi + strip 5V.
   **GND Wago** (3-way): adapter GND → Pi + strip GND.
4. Feed the Pi from the Wagos via a **micro-USB pigtail** back into its PWR port
   (keeps the Pi's input polyfuse in circuit). Meter the pigtail's polarity too.
5. Ground is common through the shared supply, so the GPIO18 → DIN data line has
   its reference.

Budget: Pi Zero 2W ~0.7 A + the ring. Full white would be ~1.2 A (~1.9 A total,
edge of 2 A), but the ring runs **blue/purple** and **capped in software**, so
real draw is well under 0.3 A. The 221 is rated 32 A — hugely over-spec.

- **Brightness cap ≤ 128 / 255** (`LED_BRIGHTNESS`, see below). Never drive
  sustained full white on all 20 — both for the current budget and because the
  heat would risk softening/warping the PLA case (glass transition ~60 °C).
  Low-brightness blue/purple runs cool.
- GPIO18 data is 3.3V; WS2812B officially wants 5V logic. Short runs often work
  direct — add the level shifter if the first few LEDs flicker.

## Pi software (not yet implemented)

Outline for a follow-up change to `display.py`:

- Install `rpi_ws281x` (`sudo pip install rpi_ws281x`, or apt
  `python3-rpi-ws281x`).
- Drive the strip on the **PWM channel of GPIO18** (needs root / `/dev/mem`).
- 20 pixels; set a **global brightness ceiling** ≤ 128 (see Power). ~40–80
  gives a pleasant ambient glow.
- Keep to the **blue/purple range** to match the Inky palette and stay cool.
- Hook LED updates into the display refresh — e.g. colour by tonight's deep-sky
  verdict, or a slow idle twinkle.

```python
from rpi_ws281x import PixelStrip, Color

LED_COUNT      = 20
LED_PIN        = 18        # GPIO18 (PWM0), pin 12
LED_FREQ_HZ    = 800000
LED_DMA        = 10
LED_BRIGHTNESS = 80        # global scale; hard ceiling 128 for the 2A budget
LED_CHANNEL    = 0

strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA,
                   False, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()
for i in range(LED_COUNT):
    strip.setPixelColor(i, Color(30, 0, 60))   # blue/purple, Color(r, g, b)
strip.show()
```

The pixel index → physical position mapping depends on where you start the data
chain and the segment join order — map it once when wired.
