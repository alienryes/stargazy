# LED bezel ring

An optional ring of addressable LEDs around the front bezel of the frame — 20
LEDs (6 top, 6 bottom, 4 each side) firing forward through a **continuous slot
per side** with a **white diffuser insert**, so every LED contributes to an
even glowing border (not discrete dots). Driven by the Pi Zero, powered from the
5V supply. The frame (`case_frame_v2.py` v3.0) is sized around a **10 mm-wide
WS2812B strip** — the outer footprint grew +4 mm/side (117.6×89.5 → 125.6×97.5)
so the bezel band can host the strip channel.

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
DOUT → DIN of the next segment). The frame's corner notches route these links
across the solid corners. Keep the arrow direction consistent all the way
round.

## Mounting

1. Print the diffusers (`case_diffusers_v1.py` → `.stl`) in **white or natural
   translucent** filament, ~1.5 mm thin so they glow. Four strips.
2. From the **back** of the frame, drop a diffuser strip into each side channel
   first — it seats against the front-wall shoulders, covering the slot.
3. Drop the matching LED strip segment in behind it, LEDs facing forward against
   the diffuser. The snap tabs hold the strip, pressing the diffuser against the
   wall.
4. The strip tail (3 wires) exits via the **bottom cable slot**, alongside the
   Pi's power lead.

## Wiring to the Pi

The Inky occupies the full 40-pin header. Solder short flying leads to the pin
tails — accessible from the Pi's back **before** the riser is fitted. Data
**must** be GPIO18: the Inky already uses the SPI pins (MOSI/SCLK/CE0), so the
SPI LED method is unavailable.

| Strip wire | Connect to |
|---|---|
| DIN (data) | GPIO18 — pin 12 (add a 74AHCT125 level shifter if it glitches) |
| GND | any GND — pin 6, common with the Pi |
| +5V | Pi 5V rail — the PP1 pad or a 5V header pin, ≥22 AWG (shared with the Pi; safe because brightness is capped — see Power) |

### Power (this build)

Powered from a **Stontronics 5V / 2A** adapter on the Pi's micro-USB — the same
supply feeds both the Pi and the strip.

Budget: Pi Zero 2W ~0.7 A + the ring. Full white would be ~1.2 A (~1.9 A total,
right at the edge of 2 A and the micro-USB connector), but this ring is meant
to run in the **blue/purple range** to match the Inky palette and be **capped in
software**, so real draw is well under 0.3 A.

- **Brightness cap ≤ 128 / 255** (`LED_BRIGHTNESS`, see below). Never drive
  sustained full white on all 20 — both for the current budget and because the
  heat would risk softening/warping the PLA case (glass transition ~60 °C).
  Low-brightness blue/purple runs cool.
- With the cap, the **simple connection is sufficient**: solder the strip's
  5V/GND to the Pi's PP1/PP6 pads (or a 5V + GND header pin, ≥22 AWG). No
  separate supply, junction, or splitter needed. (Only worth splitting the feed
  before the Pi if you ever wanted sustained bright white — which 2 A isn't
  sized for anyway.)
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
