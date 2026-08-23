# 🌌 Stargazy

A stargazing conditions display for the [Raspberry Pi Touch Display 2](https://www.raspberrypi.com/documentation/accessories/touch-display-2.html). It fetches live [AstroWeather](https://github.com/mawinkler/astroweather) forecast data (on the Pi itself, or from Home Assistant if available) and renders an overnight forecast over a live, data-reactive animated night sky, with no interaction required.

Rendered with Pillow and written straight to the Linux framebuffer (`/dev/fb0`) — no X and no display server.

**There are two builds**, sharing one engine. Pick the one that matches the hardware:

| | [`build5/`](build5/) | [`build10/`](build10/) |
|---|---|---|
| Panel | Touch Display 2, **5 inch** | Touch Display 2, **10.1 inch** |
| Board | Pi 4 | **Pi 5 or CM** — four-lane DSI, a Pi 4 cannot drive it |
| Canvas | 1280×720 landscape, rotated to the panel | 1200×1920 portrait, no rotation |
| Pages | Conditions, targets | Conditions, targets, plus conditional pages for **meteor showers**, **aurora**, **satellite passes** and **the Sun** |
| Status | **Proven in service** | **In service** |

Everything that is not layout (both weather sources, the target reports, the imagery, the animated sky, night mode, touch, the framebuffer) lives in [`core/`](core/) and is shared. The rest of this README describes the 5 inch build unless it says otherwise; substitute `build10/` for `build5/` in the commands to install the other one.

**Highlights**

- Tonight's deep-sky verdict (EXCELLENT → NONE) spelled out in bold display type
- Condition bars: cloudless %, seeing, transparency, calm. A reading below its warning mark is drawn hollow instead of filled. **Cloudless is the inverse of obscuration, not of raw cloud cover**: a sky fully covered by thin cirrus is largely observable and is reported that way
- **A real image of the Moon** for the current hour (true phase, libration and terminator) with constellation and next new/full moon dates
- Footer grouped by type — astronomical (moon dates, dusk/dawn) on the right under the moon; meteorological (lifted index, weather) on the left
- Handles the no-astronomical-darkness case for midsummer at high latitudes
- **Live animated night sky** behind the dashboard: **the actual stars overhead**, plotted from a catalogue at their real positions for the configured location and the moment, plus drifting clouds and meteors from tonight's active showers — all **reactive to the actual conditions**
- **Touch controls** hidden until the screen is tapped: night mode, page rotation, paging through the full deep-sky list, brightness and a true blank that drops the display to 0% CPU

---

## 📸 Display layout

### The 5 inch build

Two pages rotate over the same continuous animated sky. Both shots are real frames from the panel's own Pi 4, rendered from live data:

**Page 1 — tonight's conditions**

![The conditions page: a large GOOD verdict in pale blue-white, four labelled condition bars with percentages, and a photographic waning crescent Moon captioned Waning Crescent in Cancer. Each bar is filled to its value inside a hollow outline, so Seeing at just over half sits visibly short of the other three, which are nearly full. A footer gives tomorrow's forecast, lifted index, temperature, dew point, humidity and wind. A meteor is crossing the sky behind the dashboard.](screenshots/conditions.png)

> **Dusk / Dawn** is used in that footer, not sunrise/sunset: AstroWeather's sun rise/set entities report **civil twilight** bounds (sun 6° below the horizon), ~40 min off the geometric sun crossing. True darkness is tracked separately (`astronomical_night_duration`) and drives the "NO DARK SKY" state.

**Page 2 — tonight's targets**

![The 5 inch targets page: a dusk-to-dawn timeline with the astronomical dark window highlighted; an altitude-versus-bearing plot of the planets, with a line beneath it naming the bodies still below the horizon and the times they rise; and four deep-sky cards headed with the range on show out of a much longer list, each card carrying a real sky photograph, object type, constellation, peak altitude and a bar for the share of the dark hours the object stays up.](screenshots/targets.png)

The page-2 timeline only appears once UpTonight has run, and the page leaves the rotation entirely if it has produced nothing, so an empty page is never shown.

A page that has nothing to show leaves quietly, since that is the ordinary case and a warning would sit on the panel on a perfectly good night. A page whose data source actually **failed** is named instead: the conditions page lists it as unavailable for that refresh, so a silent gap and a broken feed do not look alike. This matters most on the 10.1 inch build, where five conditional pages draw on separate feeds.

**Night mode — the same page after dark**

![The conditions page in red night mode: the identical layout rendered entirely in shades of red on black, including the photograph of the Moon. The verdict, the condition bars, the percentages and the footer are all still legible, and the bars that fall below their warning marks still read as hollow outlines against the filled ones; only hue has gone.](screenshots/night-red.png)

Between real dusk and dawn (not on a clock schedule) the finished frame is put through a red filter, because long wavelengths don't disrupt dark-adapted vision. The whole frame is filtered rather than the palette swapped, which keeps the lunar photograph and the deep-sky cutouts from glowing white.

Because none of the states on the display are encoded by hue, no information is lost. The main verdict is a word, every bar has a number and a length, and a reading below its threshold is hollow rather than a different colour. `night_mode = "dim"` keeps full colour at reduced brightness instead.

### Colour marks real objects; state is neutral

If something on the display is coloured it is a thing that is actually up there — the Moon, a planet, a comet, a photograph of a nebula. If it is a judgement about tonight it is the same neutral blue-white as everything else.

### The 10.1 inch build

Orientation is portrait, 2.5× the pixels at slightly lower density, so the space is used for extra content rather than for scaling. These are real frames captured from the panel's own framebuffer, in service:

**Page 1 — conditions.** The Moon takes the middle band at 600px across; the source frame is 730px, so this is close to native rather than an enlargement. Under it are the numbers that come with the frame and are not used for the 5 inch display — age, distance, apparent diameter, and libration as the direction the near side is tipped.

![The 10.1 inch conditions page in portrait: a large GOOD verdict, a 600-pixel photograph of a waning crescent Moon captioned Waning Crescent in Cancer with its age, distance, diameter and libration, four condition bars, and a footer of forecast, dusk and dawn times and weather.](screenshots/10in-conditions.png)

**Page 2 — targets.** One altitude-versus-bearing plot carries the planets *and* the deep-sky objects on a full 0–90° axis. The 5 inch build keeps the two apart because it has far less vertical room: UpTonight selects deep-sky targets for high altitude, while the planets stay near the ecliptic and so occupy a lower band, and a short axis holding both compresses whichever band is lower. How far apart those bands sit depends on latitude — from the reference location at 51°N the objects peak around 70–85° and the planets stay below about 35°, but nearer the equator, the ecliptic rides much higher and the two overlap. Every position on the plot is for the single instant named above it.

![The 10.1 inch targets page: a dusk-to-dawn timeline; an altitude-versus-bearing plot carrying the planets alongside the same deep-sky objects as the cards below, each labelled with its bearing; a line naming the bodies still below the horizon with the times they rise; and six deep-sky cards headed with the range on show out of a much longer list, each with a real sky photograph, object type, constellation, peak altitude and where it stands at the plotted instant.](screenshots/10in-targets.png)

**Page 3 — meteors.** Which showers are actually running, from a table of orbital constants indexed by solar longitude, with the rate an observer would count once radiant altitude, cloud and moonlight are accounted for.

A shower is named until its zenithal hourly rate falls to a quarter of the sporadic background's; that background is shown at the foot of the page. Past that threshold it drops off, even though its activity window has not closed; a named row implies something to watch for and when a shower is at a fraction of the background rate it doesn't qualify any more. The windows vary twentyfold in how long they run past maximum, so the cut is made against the rate rather than a number of days. The comparison is made in ZHR rather than in the rates printed on the page, so it does not move with the site's latitude, the radiant's altitude tonight, or the weather. When nothing clears the floor the page leaves the rotation entirely.

The printed rates carry a decimal place below 1/hr. Most nights sit in low single digits and cloud divides them again, so whole numbers at that end of the range have two values and one of them is zero — which would have a named shower reporting that nothing was falling, directly above a sporadic background it is a third of.

![The 10.1 inch meteor page: a header giving the instant the rates are computed for and the current solar longitude, then a row per running shower with its days before or past peak, the radiant's altitude and bearing, a bar and a figure for the rate an observer would count, and its zenithal hourly rate at maximum. Below them a Coming Up list of forthcoming shower peaks with the days to each, and a footer giving the sporadic background rate. Meteors are falling in the sky behind the text, drawn as tapering streaks brightest at the leading end.](screenshots/10in-meteors.png)

---

## ✨ The animated sky

The sky is a live layer composited behind the dashboard each frame (12 fps on a Pi 4 - see the note under Running); the dashboard itself is an RGBA overlay (transparent where the sky should show, opaque content on top). The animation **reflects the conditions** rather than just decorating:

| Condition | Effect |
|---|---|
| Seeing / transparency / calm | Star brightness and twinkle (crisper when clear) |
| Cloud **obscuration** | Fraction of the sky the cloud field obscures, and the stars behind it go out. Derived from the forecast's high/medium/low split rather than its raw cloud fraction. 100% thin cirrus stops far less starlight than 100% stratus, and the raw figure counts them the same. Layers combine as independent transmittances, weighted by `cloudcover_*_weakening`. Falls back to raw cover where the per-layer figures are unavailable |
| Wind speed | How fast the cloud drifts, derived from the wind and a nominal 1500 m cloud base and then time-compressed (`CLOUD_COMPRESSION`, default 8). The honest rate is far too slow to read as motion. Stated as degrees of sky per second, so both panels show the same weather at the same apparent speed despite their different angular scales |
| No astronomical darkness | Sky washes to twilight blue; meteors suppressed |

The moon card shows **a real image of the Moon** (set `display.moon_ring = true` to outline the full disc), fetched hourly from NASA SVS's Dial-a-Moon and cached on disk. It uses actual phase, libration and terminator rather than a drawn approximation. If the API can't be reached the display falls back to drawing the phase geometrically, so it degrades rather than breaks. It deliberately does not reuse an older cached frame: the phase moves about 12° a day, so yesterday's picture would be incorrect, and the correct drawing is better than an attractive but wrong photograph.

Star and cloud brightness always keep a visible floor, so the sky stays alive even on poor nights.

**The clouds pass behind the moon card, and that is deliberate.** The disc on the dashboard is a *card*, not a view through a window; it is drawn about fifty times the Moon's true angular size (the sky layer runs roughly 21 pixels per degree on the 10.1 inch panel, where the real Moon would be about 11 pixels across) and it sits at a fixed place in the layout rather than where the Moon actually is. Letting cloud drift across it would suggest that the Moon really is there, that large, in that direction. The dashboard describes the sky; only the layer behind it depicts the sky. The Moon's true position is on the targets page, on the alt-az plot with the other potential targets for the night.

### The starfield is the real sky

The stars behind the dashboard are not decoration. They are plotted from the Yale Bright Star Catalogue at their true altitude and azimuth for the configured location and the current moment, recomputed every minute, and they drift in line with the Earth's spin.

**Constellations are recognisable**. This was checked on the panel; on 11 August 2026 at 09:30 the 10.1 inch build had all seven of Orion's main stars in frame, Betelgeuse within two degrees of the view centre, and the belt read at a glance. This was during daylight: Orion is a morning object in August, so the panel was showing a dark sky that could not have been seen out of the window at the time.

**Only displayed down to a `limiting_magnitude`, default 5.0 — not the catalogue's 6.5.** The catalogue's faint end references stars nobody at the reference location would see: measured over the 5 inch field of view it put 1,204 stars on screen, of which 983 were fainter than magnitude 5 and those carried 56% of the drawn area. They buried the sixteen stars that actually made a pattern, and a real sky came out looking random. Raise it for a genuinely dark site. The catalogue ships in the repository, so this needs no network connectivity.

**The panel does not know which way it is facing, so the direction in which it looks is configuration rather than something inferred:**

```toml
[sky]
real_stars = true
camera_azimuth = 180    # degrees: 0 = north, 90 = east, 180 = south
camera_altitude = 45    # degrees above the horizon at the centre of the view
field_of_view = 70      # degrees, vertical (build10 defaults to 90)
```

The default view faces **due south at 45° up**, which is where objects transit and therefore the most useful direction at northern latitudes. Point it wherever the window actually faces, or wherever the view is best. The horizontal field is derived from the panel's aspect ratio so the scale stays even in both directions — which means the landscape 5 inch build sees considerably more sky than the portrait 10.1 inch one at the same vertical setting.

Brightness and star size are mapped for legibility at a distance rather than photometrically: the ordering is faithful, so Sirius still dominates, but the range is compressed; a sky spanning eight magnitudes is drawn across about 1.5, with size carrying the rest. Each panel has its own size table, because the 10.1 inch shows a narrower window of sky magnified over 2.5× the pixels. Set `real_stars = false` for a pseudo-random starfield.

### The meteors follow tonight's real showers

**They are representations, not observations.** A meteor on the panel does not correspond to a meteor in the sky, and nothing on the panel is a live feed. What is real is everything governing their behaviour — when they fall, how often, and which direction they go.

**The cadence** comes from the same computation that fills the 10.1 inch meteor page: which showers are running, how high each radiant sits, and how much of the rate is reduced by cloud and moonlight. So a quiet night in March shows almost nothing and a clear Perseid peak is busy, and if nothing is falling, nothing falls on the display either. The rate is deliberately time-compressed (`meteor_compression`, default 20), because a real three-an-hour would make the animated sky look broken; it does scale what is there but doesn't invent anything.

**The direction** is the true radiant. A meteor is drawn from one of tonight's active showers in proportion to that shower's rate, and travels away from where that shower's radiant actually is in the projected sky, so it converges on a point that agrees with the stars around it. Trails shorten towards the radiant, since a path pointing at the observer would be seen end-on. The radiant can quite often be off the edge of the panel, as the view faces one direction and the shower is in another, so its meteors sweep in near-parallel from that side. Meteors belonging to no shower (the sporadic background, which is most of them on an ordinary night) use an arbitrary direction, because they genuinely have none. Setting `sky.real_stars = false` sets the meteors to arbitrary directions along with the pseudo-random starfield.

Sources for the animated sky: the Yale Bright Star Catalogue (Hoffleit & Warren, 5th revised edition) via VizieR at CDS Strasbourg for the starfield; NASA SVS's Dial-a-Moon, by Ernie Wright, for the lunar frame; the IMO Working List of Visual Meteor Showers for radiants, peaks and zenithal hourly rates, with the activity falloff from Jenniskens (1994). The catalogue and the shower table ship in the repository; only the lunar frame is fetched.

---

### Aurora, when there is any (10.1 inch build)

This page exists **only when aurora is above the configured location's horizon and it is dark enough to see it**. At temperate latitudes that means it may be absent for years at a time; in Iceland or northern Norway it will be a regular fixture. Both are correct, and the frequency difference is real rather than a setting.

![The aurora page during a real storm: 69 percent probability at bearing 342 degrees on the horizon, a second cell 25 degrees up to the north-north-west, a drawn field along the northern horizon shading from yellow-green low down to magenta above, and the three-day Kp forecast.](screenshots/10in-aurora.png)

> **A real storm, 8 August 2026, Kp 6.** The strongest cell was 69% at 1,754 km on the horizon to the north-north-west; the best-placed one 10% at 25° elevation and 477 km. Captured with `--no-night` so the emission-height colours are visible. Between dusk and dawn the panel renders this page in red, which is when it exists. This replaces the injected-storm screenshot the page shipped with, retained as `screenshots/10in-aurora-simulated.png`.

**The query is not "the probability at my latitude".** Aurora emits 100–250 km up, so it is visible far beyond the ground it sits over; from 51°N the horizon reaches past 67°N. Reading only the model cell that contains the configured location can return zero even though a good display is genuinely visible to the north or south. Instead, every model cell within the horizon is searched.

**The direction is not assumed.** The auroral oval passes overhead at high latitudes and lies to the *south* in the southern hemisphere, so the bearing and elevation are computed rather than presumed. The same code answers "north and low" from southern England, "overhead" from Reykjavik and "south" from Tasmania, none of them special-cased.

Two model cells are reported, because they answer different questions and are routinely different: the **strongest**, and the **best placed** — the highest above the horizon. The strongest is often the one grazing the horizon, where the whole thickness of the atmosphere and any terrain at all stand in the way. So reporting that cell alone may send the observer to look at nothing.

**The storm itself is drawn**, not just its extremes: every lit model cell is classified by bearing and elevation and shaded by its probability, so the shape on the plot is the model's own from the observer's position. Opacity *is* the probability (a 60% cell is drawn 60% solid), and the blur only smooths the grid's steps. No structure is added; curtains and rays are not something the model can resolve.

**Colour follows emission height.** The green line is emitted around 100–150 km and the red from 200 km upward, and the Earth hides the lower part first. So the colour is computed from the lowest altitude still above the horizon at each cell's distance. A distant aurora renders red because the red tops are genuinely all that clears the horizon, and one overhead renders green. That is why southern England reports a red glow while Tromsø gets green, and the same code produces both. It is an inference from geometry rather than something OVATION reports, and between dusk and dawn the panel's night mode collapses everything to red luma anyway, so the colour is naturalism and doesn't carry meaning on its own.

The page also carries SWPC's three-day Kp outlook, and says whether the local sky is clear enough to act on any of it. Everything shown is a **probability from a model, roughly 76 minutes ahead of its observation time** — not an observation.

Source: NOAA SWPC's OVATION model. No key, no registration.

---

### Satellite passes (10.1 inch build)

A page that appears **when a bright satellite crosses this sky within the coming day**. Unlike the other conditional pages it is not gated on the sky being dark now, because a pass is an appointment rather than a condition.

![The 10.1 inch satellite page in portrait: a headline naming the next bright pass with its time and how long until it, trailed by a solid line sample keying it to the plot, then a line giving where it rises, how high it climbs and in which direction, and where it sets, and a line giving minutes in view and range at its highest. Below that an altitude-versus-bearing plot on a 0 to 90 degree axis over the compass points, carrying one solid beaded arc for that pass with a round marker part way down its descending limb, and three dashed arcs behind it for the other passes of the same night. Beneath the plot two listings: tonight's passes, each row giving date, time, object, its dash pattern, peak altitude and the bearings it travels between; and the best for the next seven days, whose rows carry no dash sample because they are not plotted. A three-line footer explains the beads, the marker and the faint track, and credits CelesTrak for the elements along with their age. Cloud drifts behind the whole page.](screenshots/10in-satellites.png)

> **A real capture, 18 August 2026**, taken off the panel with the rotation paused on this page. The next pass was still eleven hours away, which is why the page was up in daylight: it is gated on a pass falling within the day, not on the sky being dark now.

**This is the one man-made thing the display will draw into the sky layer.** Everything in that layer claims to be in front of the observer at that bearing and that altitude, and a pass can honour the claim: the object really is there, at that minute. The aurora field and the Moon card are dashboard content precisely because they cannot.

**Visibility is not darkness alone.** The satellite has to be in sunlight while the observer is not, which is why passes belong to twilight rather than the middle of the night, when the object is in the Earth's shadow and there is nothing to see. The gate is civil twilight rather than the astronomical darkness the aurora page waits for, since waiting for full darkness would discard the twilight passes, which are most of the good ones. A pass also has to reach 10° at its highest to be worth announcing, or it spends its whole duration in haze and behind whatever is on the horizon.

**Nothing here predicts a brightness.** Apparent magnitude depends on which face is turned towards the observer, and no keyless source reports the attitude. Range and altitude are given instead, both computed rather than estimated. Which objects are bright enough to qualify at all is CelesTrak's judgement: the page tracks its `visual` group rather than a list kept in this repository, which would decay silently as objects re-enter and new ones launch. Rocket bodies, debris and numbered military payloads are filtered out by name, leaving the named payloads — the two stations, the BlueBirds, and the reliable sun-synchronous set.

**Ranking on height alone was measured to be worse than no ranking.** Across the group a week holds dozens of near-zenith passes, so height saturates and the winner is effectively arbitrary: the page once led with a 1970 ion-engine testbed at three in the morning while an ISS pass the same evening went unmentioned. Objects are sorted into two tiers instead, with height ordering them within a tier.

**The path is why this is a page rather than a line of text.** The headline pass is plotted on the same bearing-by-altitude panorama the other pages use, so the track needs no axes of its own. Beads along it mark minutes, a faint stretch is time spent in the Earth's shadow, and the moving marker shows direction rather than speed. The other passes of the same night are drawn behind it, dimmed, each keyed by its dash pattern to its row in the listing beneath, so an arc and the row describing it cannot disagree. Below the plot are two blocks: tonight's passes, and the best of the next seven days.

The listing reaches a week while the page itself is gated on the coming day, because whether the page exists is a question about acting tonight and the list is a schedule. It stops at a week deliberately: pass times come from orbital elements that age, and quoting a minute a fortnight out would state a precision the elements do not carry. Elements are refreshed twice a day and the display refuses to predict from a set more than three days old, because a stale element set does not produce an obviously wrong answer, it produces a plausible one at the wrong minute. `[satellites] enabled = false` removes the page.

Source: CelesTrak's GP element sets, one grouped request rather than one per object. No key, no registration.

---

### The Sun, while it is up (10.1 inch build)

Every other conditional page here exists only after dark, because aurora and meteors are conditions of the night sky. This page inverts that: it appears **whenever the Sun is above the horizon**, and fills the hours when the rest of the panel has less to say.

![The solar page on a quiet day: the word QUIET over the day's strongest flare, rows for sunspots, coronal mass ejections, flare odds and radio flux, and below them a photograph of the Sun's disc in white light with individual sunspots visible as small dark marks.](screenshots/10in-solar.png)

> **An ordinary quiet day, 13 August 2026** — captured off the panel. Seven spot regions, nothing above a B-class flare, and no CME modelled to arrive.

It is also the only page here that is **always present rather than gated on something happening**. That is a deliberate departure from the rule the other pages follow, because the Sun is always there: a quiet Sun is still a fact about today, not just an empty page.

**The disc is a photograph.** SDO's HMI continuum frame; the white-light view, which is the one with the sunspots actually in it. It is composited the same way the Moon card composites its Dial-a-Moon frame, on the same black field with the same circular mask. The mask is doing real work here: it removes the caption strip SDO prints along the bottom of every frame. What the frame resolves is **individual spots** rather than the groups they belong to: labelling the dark blobs gives 11–21 of them against SWPC's 22 spots in 7 regions on the same day, so the credit names spots and the sunspot row carries both counts. The colour is SDO's own, a table applied to continuum intensity: from space the Sun is white, and the page states that the colour is applied rather than observed. All of that sits in the footnotes as `Imagery: …`, with the other attributions, rather than as a caption under the disc.

The imagery replaced a drawn disc and fixed the issues it brought with it. The drawing plotted each group from SWPC's regional report and overlaying those computed positions on an SDO frame showed **every mark sitting east of its real spot by about the same amount** — because the report is a *daily* snapshot while solar rotation carries a group roughly 13.2° a day, up to 110 px at this scale by the time the next one is issued. The projection was correct; its input was stale, and only a photograph could have shown that. A frame has no such lag: it shows the spots where they were at its own timestamp, which is what the page displays.

The drawn disc survives as the fallback for when SDO cannot be reached — orthographic, tilted by the season (the Sun's axis leans up to 7.25° either way through the year, so the equator bows off centre and the disc reads as a sphere), far-side groups dropped rather than folded onto the wrong limb, and solar west to the right as in every published solar image. In that state the marks are enlarged to be visible and the caption says the positions are as last reported rather than as they are in the present.

**An eclipse gets top billing** when one is due within a day, with a countdown. It is stated as a single line at the foot however far off it is otherwise; the rarest thing this panel shows is worth knowing about in advance. From southern England expect roughly one visible partial a year and none at all in some years; the next is 2 August 2027.

**Magnitude and obscuration are given separately and named separately.** Magnitude is the fraction of the Sun's *diameter* covered, obscuration the fraction of its *area*. They're not the same number: at a deep partial they differ by ten points. The page never prints one under the other's label.

**The eclipse needs no network at all.** It is computed locally from the Sun's and Moon's apparent discs, seen from the configured location so that lunar parallax is included. That makes it the one thing this display can still announce with the internet down.

**Nothing on the page is phrased as an instruction or invitation to look at the Sun without protection**, and the filter warning follows what it qualifies: it sits beside the coverage figures while an eclipse holds the top of the page, and in the footnotes the rest of the time, alongside the next eclipse line.

Sources: NOAA SWPC for spots, flares and radio flux; NASA's DONKI model runs served by CCMC for a coronal mass ejection's predicted arrival and Kp; NASA SDO/HMI for the disc. All keyless, none requiring registration.

## 👆 Touch controls

Since the panel is a touchscreen, there are touch controls. The display reads them directly from `/dev/input/eventN`, so neither X nor Wayland is required.

No controls are drawn until the screen is touched. **The first tap only reveals a control strip** along the bottom, which will disappear after six seconds; a second tap presses a button. That way the ambient display stays uncluttered and brushing past the panel in the dark can't affect anything.

| Button | What it does |
|---|---|
| **Night** / **Day** | Turns the red night filter on or off, immediately, whatever the hour |
| **Pause** / **Resume** | Holds the current page instead of rotating |
| **Next** | Jumps to the next page straight away |
| **Dimmer** / **Brighter** | Backlight, via `/sys/class/backlight`. Never goes below the lowest visible step |
| **Blank** | Backlight off and compositing stopped. The display drops to **0% CPU** until it is touched again. |
| **More** | *Targets page only.* Steps to the next screenful of deep-sky objects, and wraps at the end |

**More** exists because the deep-sky list is far longer than one screenful. UpTonight commonly passes forty objects on a dark night, against six cards on the 10.1 inch panel and four on the 5 inch, and the heading has always said so — `DEEP SKY (1–6 of 40)`. Pressing **More** reaches the rest, six or four at a time; on the 10.1 inch build the altitude-versus-bearing plot follows, so the plot and the cards always describe the same objects.

Every screenful is drawn in advance on the data thread, along with the sky photograph for each object, because stepping between them happens on the render loop where a fetch is too expensive. The page rotation also holds while the control strip is showing, so a page cannot turn mid-press.

A night mode picked by hand lapses the next time the sky crosses dusk or dawn: it is a change of state for that night, not a second schedule competing with the automatic one. Nothing else in the touch controls is persisted. `config.toml` is restored on restart, so the display always comes back to a known state.

This functionality requires `display.mode = "animated"`, and an account in the `input` and `video` groups (`setup.sh` arranges both). Set `touch.enabled = false` to turn the touch controls off.

---

## 🛠️ Requirements

**Hardware** — the whole build, and roughly what it costs:

| Item | Qty | Notes |
|---|---|---|
| Raspberry Pi 4 Model B (2GB is plenty) | 1 | What this is built and proven on. See the Pi 5 note below |
| Raspberry Pi Touch Display 2, **5 inch** | 1 | 720×1280 DSI. Ships with a Pi 4 DSI cable |
| Official Raspberry Pi USB-C PSU (5.1V/3A) | 1 | The printed stand is sized so this one's stiff cable clears the desk |
| microSD card, 16GB+ | 1 | Raspberry Pi OS Lite 64-bit |
| 3D-printed case and stands | 1 set | Optional — see [`case/`](case/README.md). ~150g of PETG |
| M2.5 screws and standoffs | 1 set | Only for the case; full list in [`case/README.md`](case/README.md) |

No soldering, no HAT, no GPIO wiring. The display is DSI and the case is all screws and standoffs. If a 5v GPIO pin is required then the 0 v pin of the display connector can be shifted to the middle pin and the connector moved right by one pin. This frees up Pin 2. Normally the connector connects via Pin 2 and Pin 6, which blocks pin 4.

> **Using a Pi 5 for the 5 inch build gives no advantage.** It needs a Display Adapter Cable for Pi 5 (22-way → 15-way, the one marked `DISPLAY`), and there is no performance reason to move: the render loop is single-threaded and uses about one core of four. The case *does* have a printable Pi 5 variant.
>
> The framebuffer format differs between the two panels and is **detected at runtime**, so neither build needs configuring for it: the 5 inch reports 16bpp RGB565, the 10.1 inch on a Pi 5 reports 32bpp XRGB8888. To see what a board presents:
> ```bash
> cat /sys/class/graphics/fb0/bits_per_pixel /sys/class/graphics/fb0/virtual_size
> ```
> A padded framebuffer (one whose `stride` exceeds width × bytes-per-pixel) is not supported, and is refused at startup rather than rendered as a diagonal smear. Neither panel pads.

**For the 10.1 inch build**, the table changes: a **Raspberry Pi 5** (its DSI is four-lane, which the panel requires), the **10.1 inch** Touch Display 2, a 27W USB-C PSU, and the official **Pi 5 Active Cooler**, which is required rather than optional on a continuous render loop.

**The 10.1 inch build deliberately has no case, and doesn't need one.** The Pi bolts to the standard 58 × 49 mm hole pattern in the middle of the panel's back, which mounts it properly on its own — unlike the 5 inch, where the case and the Pi share one screw chain. Leaving the board open also suits the active cooler, which needs free air rather than a grille. The panel is 247 mm tall in its native portrait with the Pi centred, so there is roughly 80–95 mm below the board for the display ribbon and the power cable to turn and drop; the 5 inch needs a stand partly because rotating it to landscape leaves only about 18 mm there. A stand is still wanted for the 10.1 inch, but that is a question of how it sits on a desk, not of enclosing anything.

**Software**
- Raspberry Pi OS Lite 64-bit (Trixie / Bookworm), headless (`multi-user.target`)
- Python 3.11+
- **No Home Assistant required.** Weather comes from [pyastroweatherio](https://github.com/mawinkler/pyastroweatherio), the library the Home Assistant [AstroWeather](https://github.com/mawinkler/astroweather) integration itself wraps, talking straight to MET Norway and Open-Meteo. If Home Assistant is available with that integration, then set `weather.source = "homeassistant"` and the display reads its sensors instead.
- **An internet connection**, but nothing else on the local network. The 5 inch build uses three public services: the weather above, NASA SVS for the lunar image, and CDS Strasbourg for the deep-sky cutouts. The 10.1 inch build adds four more for its conditional pages: NOAA SWPC for aurora and space weather, NASA's DONKI runs served by CCMC for CME arrival, NASA SDO for the solar disc, and CelesTrak for the satellite elements. All are keyless and none require registration. No broker, no container, no local servers. Each one degrades on its own if it's unreachable. The moon falls back to a drawn phase, the cutouts to drawn glyphs, and cached weather keeps the dashboard up.

---

## 🚀 Setup

### 1. Pi one-time setup

The 5 inch Touch Display 2 is auto-detected over DSI and needs no device-tree overlay. **The 10.1 inch is not**: `display_auto_detect=1` is firmware-side probing, so firmware older than the panel does not recognise it, and the symptom is no output *and* no DSI connector at all in `/sys/class/drm`. For that panel, add the overlay to `/boot/firmware/config.txt` and reboot before running setup:

```
dtoverlay=vc4-kms-dsi-ili79600-10-1inch
```

Append `,dsi0` only if the ribbon is in CAM/DISP 0. The overlay defaults to DSI1, which is CAM/DISP 1. Then run the setup script:

```bash
# Copy the build's setup.sh to the Pi, then:
sudo bash setup.sh          # or: sudo bash setup.sh <username>
sudo reboot                 # required: setup.sh adds fbcon=map:2 to the kernel cmdline
```

With no argument it sets everything up for the account that invoked `sudo`, which is almost always what is required. Pass a username only if installing on behalf of a different account.

`setup.sh`:
- installs `fonts-ibm-plex` (the display's typeface), `fonts-dejavu-core` (fallback), `python3-pil`, `python3-numpy`, `python3-requests`, `python3-pip`, `python3-venv`
- builds the display's virtualenv, reusing apt's Pillow and NumPy rather than rebuilding them
- adds the user to the `video` group (framebuffer + backlight) and `input` group (touchscreen)
- adds `fbcon=map:2` to `/boot/firmware/cmdline.txt` so the text console never draws over the display
- installs a deliberately narrow sudoers rule for the deploy script — see the security note below

### 2. Create config

```bash
cp build5/config.example.toml build5/config.toml
```

Set the desired observing location in `[location]`; that is the only thing that MUST be edited (unless the location is Greenwich, London, UK, which is the default). The default `weather.source = "direct"` fetches the forecast on the Pi itself and needs no credentials at all:

```toml
[weather]
source = "direct"

[location]
latitude = 51.4779
longitude = -0.0015
elevation = 47
timezone = "Europe/London"

[display]
# mode = "animated"     # or "static" (redraw only when the data changes)
# fps = 12
# data_refresh_min = 15
```

**Every setting with a code default ships commented out, holding that default.** Uncommenting one pins it: the value then survives upgrades, and a later change to the default stops reaching that machine. The file is therefore a list of what can be changed rather than a set of choices already made, and a working install can consist of `[location]` alone.

That distinction is not cosmetic. The Open-Meteo model was pinned in code to a coarse global grid until 2026-08-11, when it reported 60% high cloud over a photographed clear sky; had the panels also pinned `forecast_model` in their own config, correcting the default would have deployed and silently done nothing.

**Night mode** (`night_mode = "off" | "dim" | "red"`) applies between real dusk and dawn rather than on a clock schedule, because the point is to stop the panel ruining dark adaptation and that starts when the dark sky does. `"dim"` keeps the colours at `night_dim`% brightness; `"red"` goes monochrome red because long wavelengths leave low-light vision alone. Nothing is lost by going red. No reading is carried by colour alone, so the verdict word, the numbers and the bar lengths all still say what they said. It applies to the finished frame, so it covers the animated sky and the sky photographs too.

**Backlight** (`brightness`, a percentage of the panel's maximum, default 100) is applied at startup. It is set rather than left alone because the backlight is the one setting the hardware keeps across a restart: left alone, the panel comes back at whatever the Dimmer and Brighter buttons were last pressed to, and after a reboot at the driver's own value — 4 of 31 on both panels, which is dim enough to read as a fault. Everything else already returns to this file on restart; this makes the backlight do the same.

To read from Home Assistant instead, set `source = "homeassistant"` and add an `[ha]` section with the HA URL and a long-lived access token (HA → Profile → Security → Long-Lived Access Tokens).

Both sources are the same underlying model, so they agree. `display.py --compare` fetches from each back to back and prints a per-value diff if local confirmation is required.

### 3. Deploy

From Windows:

```powershell
.\build5\deploy.ps1 -User <pi-username> -PiHost <hostname-or-ip>
```

Both default to the reference build's values (username `operations` and hostname `stargazy5.local`; the 10.1 inch build's script defaults to `stargazy10.local`), so `.\build5\deploy.ps1` alone works once the local ones match. Otherwise pass them. Unlike `setup.sh`, this runs on a PC and talks to the Pi over SSH, so it cannot infer the remote account name. The host is resolved by mDNS, which works on either the wired or the wireless interface; use an explicit address if mDNS is unavailable.

This copies the files, installs the Python dependencies, stages the systemd units, and restarts the always-on animated display. **The very first deploy (and any later one that changes a unit file) will print one extra command to run**. Installing a systemd unit is done under interactive sudo on the Pi, not automatically.

### A note on security

- **The NOPASSWD sudoers rules cover exactly two commands**: restarting the display service and kicking a first UpTonight run. In particular the deploy account **cannot** install unit files unattended. A unit executes as root, so `build5/systemd/install-units.sh` asks for a password instead. If these rules are widened for convenience, understand that root is being handed to anything that ever compromised the deploy account.
- **Check for `/etc/sudoers.d/90-cloud-init-users`.** A Pi provisioned with Raspberry Pi Imager gets its first user `NOPASSWD:ALL` from cloud-init, which silently defeats the scoped rules above. `sudo -l` will show it. If the account has a usable password (`passwd -S <user>` says `P` — confirm this first, or lose easy root), remove that file and sudo goes back to asking.
- **`deploy.ps1` uses `StrictHostKeyChecking=accept-new`**: first contact trusts the key it sees, after which a changed host key aborts the deploy. If the Pi is reflashed, clear the stale key with `ssh-keygen -R stargazy5.local`.
- `config.toml` is deployed with mode 600, since it can carry a Home Assistant token.
- Python dependencies install **unpinned** (current Pi OS ships Python versions the upstream pins predate). That is a supply-chain trade-off: current wheels are used, not vetted ones. Pin them if that suits the threat model. The riskiest parsers (Pillow, requests, urllib3, NumPy) deliberately come from **apt**, not pip, so Debian's security team patches them; keep that working by running `apt upgrade` occasionally or installing `unattended-upgrades`.
- **Both services run sandboxed** (`NoNewPrivileges`, `ProtectSystem=full` and friends): they parse data fetched from the internet, so the units assume compromise and bound it. Code inside the service cannot invoke sudo at all, whatever the sudoers file says. The unit comments record which protections are deliberately absent and why.
- **`sudo bash harden-pi.sh` does the last two**, and neither is completed by `setup.sh`. They change the machine logon mode, which an application installer should not affect. It switches SSH to key-only (once passwordless sudo is off, the account password is the box's root gate and shouldn't be guessable over the network) and installs `unattended-upgrades`. It refuses to run unless the key is already installed, validates the config, rolls back on failure, and reloads rather than restarts sshd so it cannot strand the access mid-session. **Afterwards root needs the key *and* the password. On a Pi with no keyboard, losing both means pulling the SD card.**

---

## 🖥️ Running & preview

The always-on `stargazy.service` runs `display.py` as a daemon. For manual runs and development:

```bash
python3 display.py            # daemon (mode from config; default animated)
python3 display.py --once     # render one frame to the panel and exit
python3 display.py --save preview.png   # save a single composited frame (no panel needed)
python3 display.py --demo     # force a vivid clear-sky animation, ignoring the weather
python3 display.py --compare  # fetch from both weather sources and diff them
```

`--demo` is handy for checking the vivid end of the range without waiting for a clear night.

`--save` renders the draw path again, so it shows what the code *would* produce. To capture what the panel is **actually showing** (the page the rotation is on, the control strip, the live night filter) read the framebuffer instead:

It reads `/dev/fb0`, so it runs **on the Pi**, where `deploy.ps1` puts it beside `display.py`:

```bash
cd ~/stargazy
.venv/bin/python grab_panel.py --rotate 270 --out panel.png   # 5 inch
.venv/bin/python grab_panel.py --rotate 180 --out panel.png   # 10.1 inch
```

The rotation differs because the framebuffer holds the image in the panel's orientation rather than a readable one, and neither value can be detected from the framebuffer itself. Geometry and colour depth are read from the device. Reading `/dev/fb0` needs membership of the `video` group, which `setup.sh` arranges.

---

## 🧰 Case

A free 3D-printable case for the 5 inch Touch Display 2 + Pi 4 lives in [`case/`](case/README.md) — four parametric CadQuery parts (shell, Pi clamshell, twin bolt-on stands at a 20° lean, optional 40 mm fan). A Pi 5 variant of the two clamshell parts is also generated, built and fitted, though its display ribbon routes differently and needs an adapter cable. It's a **CC BY remix of [RonnyS's Touch Display 2 case](https://www.printables.com/model/1377047-raspberry-pi-touch-display-2-case)**, which targets the 7" panel; this one is re-drawn for the 5 inch. See [`case/README.md`](case/README.md) for print settings, hardware and assembly.

**This is for the 5 inch build only.** The 10.1 inch panel mounts and cools its Pi perfectly well with the board left open — see the note under Requirements.

For the 10.1 inch panel there is a **stand** instead, in [`stand10/`](stand10/README.md): one printed part and two M2.5 screws, holding the panel at a 10° lean with the Pi left open on its back, with two moulded-in collars carrying the power lead down to the desk. It is **GPL-3.0, not CC BY** — nothing in it derives from RonnyS's case, since the 10.1 inch panel decouples its enclosure brackets from the Pi's own mounting pattern and none of the 5 inch design carries over. Printed and in use. Note that the panel mounts 180° from the way it arrives, which is the only orientation the stand fits — see [`stand10/README.md`](stand10/README.md).

The project originally ran on a **Pimoroni Inky Impression 4"** with a bespoke stand (CadQuery frame + riser + WS2812B LED bezel ring). After moving to the self-lit Touch Display 2 that design was retired and archived, with its full history, to a separate private repository.

---

## 🔧 Troubleshooting

| Symptom | Fix |
|---|---|
| Blank panel, or console/login text over the dashboard | The text console is still bound to `/dev/fb0`. Ensure `fbcon=map:2` is in `/boot/firmware/cmdline.txt` and reboot; `fbcon-detach.service` also unbinds it at start |
| Dark panel while the service is healthy and logging normally | The display was never woken: `fbcon=map:2` means no console performs a modeset, and a Pi 5 with `disable_fw_kms_setup=1` has no firmware-set mode either, so the CRTC stays off while frames render into a buffer nobody scans out. The daemon now issues an unblank when it opens the framebuffer, so this should not recur. Confirm with `cat /sys/class/drm/card*-DSI-*/enabled` (want `enabled`) and `cat /sys/class/backlight/*/bl_power` (want `0`, not `4`) |
| `PermissionError` writing `/dev/fb0` | The user isn't in the `video` group — rerun `setup.sh`, or `sudo adduser <user> video` and re-login |
| Sky looks static / no visible animation | Heavy cloud legitimately calms the sky. Confirm with `python3 display.py --demo`; check the computed mood with `python3 -c "import tomllib,display; c=tomllib.load(open('config.toml','rb')); print(display.sky_params(display.make_fetcher(c)()))"` |
| Dashboard upside down / mirrored | Flip `ROTATE` in `display.py` between `Image.ROTATE_90` and `Image.ROTATE_270` |
| `ModuleNotFoundError: numpy` | `sudo apt install python3-numpy` (or rerun `setup.sh`) |
| Tapping the panel does nothing | The log will say `No touchscreen found` if the account isn't in the `input` group — rerun `setup.sh`, or `sudo adduser <user> input` and reboot. Also check `touch.enabled` is true and `display.mode` is `animated`; touch is not wired into static mode |
| Taps land a quarter-turn away from a finger | The touch mapping follows `ROTATE`, so if that is flipped, flip it here too. Check it directly with `python3 touch.py`, which prints raw and mapped coordinates for each tap |
| A button fires when the tap was only meant to wake the strip | The first tap only reveals it. If the strip was already up (it stays for `touch.strip_seconds`), the tap counts as a press; raise or lower that value to suit |
| Drawn moon instead of a photograph | The Dial-a-Moon fetch failed. The log says why. It will not substitute an older cached frame, because the phase moves ~12°/day and yesterday's picture would be wrong |
| `KeyError: 'ha'` in config | Only applies with `weather.source = "homeassistant"`: `config.toml` is missing the `[ha]` section header |
| 401 Unauthorized from HA | Likewise — the token in `config.toml` is wrong or expired |
| The Pi's hostname reverts, days or weeks after being changed | cloud-init owns it on an Imager-provisioned Pi and reapplies it at boot. `sudo bash rename-host.sh <newname>` sets it and disarms that; only a reboot proves it held |
| After a rename, `/etc/hosts` keeps the old name as an alias | cloud-init caches its datasource per instance-id, so correcting `/boot/firmware/user-data` alone has no effect. `sudo bash disable-cloud-init.sh`, then reboot; afterwards `stat -c %y /etc/hosts` must predate `uptime -s` |

**Check logs / CPU:**

```bash
journalctl -u stargazy -f
systemctl status stargazy
```

**The frame rate is a maximum and is not guaranteed**, and the default of 12fps is what the panel holds in both night modes with room to spare. Measured end to end: **51 ms a frame with the night filter off and 43 ms in red**, roughly 60% of it the RGB565 pack either way. Raising `fps` buys about 19 fps by day and 23 after dark. Lowering it reduces CPU.

Daylight is the binding case, which reverses how this build spent most of its life. Red used to be the expensive mode (118 ms a frame at one point, and still 57 ms after the framebuffer fast paths landed) because the night transform was the one step with no C implementation behind it. It now computes its luma through PIL's matrix convert rather than in numpy, which is worth about 14 ms a frame on the 5 inch and 20 ms on the 10.1 inch.

### Optional: a 32-bit framebuffer on the Pi 4

On a Pi 4 the DSI panel comes up at **16bpp** (RGB565), because that is what the vc4 KMS framebuffer emulation provides. On a Pi 5 the DSI panel is driven by a different driver and already presents 32bpp. Nothing needs configuring for either. The depth is read from the device at startup and the pixel packing follows it.

16bpp can be overridden. Adding this to `/boot/firmware/cmdline.txt` (on the single existing line, space-separated) and rebooting gives 32bpp:

```
video=DSI-1:720x1280-32@60
```

**The connector name differs by board.** It is `DSI-1` on a Pi 4 and `DSI-2` on a Pi 5; `ls /sys/class/drm` gives the right one. The resolution and refresh are required, as the bit-depth suffix alone is ignored. Confirm the result with `cat /sys/class/graphics/fb0/bits_per_pixel`.

**What it buys.** Red night mode packs luma into the five red bits at 16bpp — **32 levels for the whole image**. At 32bpp it is 256. The twilight gradient and the cloud field's soft edges are both smooth ramps drawn almost entirely in one channel after dark, so that is where banding shows if it shows anywhere.

**What it costs.** Measured on a Pi 4, packing one frame:

| night mode | 16bpp | 32bpp |
|---|---|---|
| off | 29.3 ms | **12.2 ms** |
| red | **36.6 ms** | 44.4 ms |

Faster in daylight and slower after dark, which is the wrong way round for a display that runs red from dusk to dawn. The frame still fits inside the 12 fps budget either way, with less margin. Framebuffer memory and write bandwidth double.

Worth it for colour on a panel that is looked at closely; not worth it for speed.

---

## 📁 File structure

There are two builds, differing in panel and board. They share one engine in
`core/`; each build folder holds only what is specific to its hardware — layout,
config, systemd units and deploy script. A build folder plus `core/` is
everything that gets installed on a Pi.

```
core/                   Shared engine: weather sources, target reports, imagery,
                        animated sky, night filter, framebuffer, touch controls
build5/                 5 inch Touch Display 2 on a Pi 4 (720x1280) - the reference build
  display.py              Entry point and 1280x720 layout
  touch.py                Touchscreen reader (evdev; run alone to check mapping)
  config.toml             Local config (gitignored)
  config.example.toml     Template ([weather] + [location] + [display] + [touch])
  deploy.ps1              Windows → Pi deploy script
  setup.sh                One-time Pi setup (run with sudo)
  systemd/
    stargazy.service            Always-on animated display daemon
    fbcon-detach.service        Frees /dev/fb0 from the text console
    install-units.sh            Installs the units - interactive sudo, by design
build10/                10.1 inch Touch Display 2 on a Pi 5 (1200x1920) - portrait,
                        adds a meteor shower PAGE, an aurora page, a satellite
                        pass page and a solar page. Both builds fly real
                        meteors in the sky itself
screenshots/            README images, regenerated with display.py --save
tools/                  Development checks and utilities
  grab_panel.py           Capture what the panel is actually showing, off /dev/fb0
  check_fb_paths.py       Prove the framebuffer fast paths emit the shipped bytes
  check_ranking.py        Deep-sky ordering, incl. UpTonight's 0.0 magnitude
  check_paging.py         Deep-sky card paging arithmetic, both card counts
harden-pi.sh            Optional: key-only SSH + automatic security updates
rename-host.sh          Optional: rename the Pi so the change survives a reboot
disable-cloud-init.sh   Optional: stop cloud-init reapplying its provisioning
case/
  README.md               Print settings, hardware, assembly
  shell.py                Display shell (front frame + back plate)
  pi_models.py            Measured Pi 4 / Pi 5 connector tables
  case_bottom.py          Pi clamshell base (bay, walls, port sill, lid spigots)
  case_top.py             Ventilated lid (ports, fan grille + mounting)
  stand.py                Bolt-on desk stand - print 2
stand10/                Desk stand for the 10.1 inch panel - one part, no case needed
  README.md               Print settings, panel orientation, assembly
  stand10.py              The stand, incl. the power-lead collars
  check_stand10.py        Fit, clearance and overhang checks on the exported STL
```

---

## 💬 Feedback and contributions

Bug reports, questions and build photos are all welcome via [Issues](https://github.com/alienryes/stargazy/issues).

One area where reports are especially useful, because it cannot be verified here:

- **Other latitudes.** The reference build sits at 51°N. The targets page derives its altitude axis from the configured latitude (the highest an ecliptic body can reach, plus the Moon's inclination and a little headroom) so it should not need adjusting anywhere, and reports that it does are useful. The axis also opens beyond that figure for a comet placed higher, comets not being tied to the ecliptic.

---

## 🙏 Acknowledgements

This project is a thin dashboard over other people's hard work.

- **[AstroWeather](https://github.com/mawinkler/astroweather) and [pyastroweatherio](https://github.com/mawinkler/pyastroweatherio)** by Markus Winkler (MIT). The seeing, transparency, calm and deep-sky figures are its model, not a reimplementation of it. The display calls the same library the Home Assistant integration wraps.
- **[UpTonight](https://github.com/mawinkler/uptonight)**, also by Markus Winkler, computes the target lists on the Pi.
- **Weather data** from [MET Norway](https://www.met.no/) and [Open-Meteo](https://open-meteo.com/), via the above.
- **The star catalogue** behind the real sky in both builds is the **Yale Bright Star Catalogue** (Hoffleit & Warren, 5th revised edition), obtained from **VizieR at CDS, Strasbourg Observatory, France** (catalogue V/50) and trimmed to magnitude 6.5 — of which the display draws down to `limiting_magnitude`. It ships in the repository as `core/data/stars.tsv`, so the display needs no network to draw the sky.
- **Sky imagery** from the [`hips2fits` service](https://alasky.cds.unistra.fr/hips-image-services/hips2fits) at **CDS, Strasbourg Observatory, France**, rendering the **DSS2 colour** HiPS survey. The Digitized Sky Survey was produced at the Space Telescope Science Institute under U.S. Government grant NAG W-2166, from photographic data of the Oschin Schmidt Telescope on Palomar Mountain and the UK Schmidt Telescope.
- **Lunar imagery** from **[Dial-a-Moon](https://svs.gsfc.nasa.gov/4442)**, by **Ernie Wright** at **NASA's Scientific Visualization Studio**, rendered from Lunar Reconnaissance Orbiter data. SVS content is public domain. Each frame shows the Moon's real phase, libration and terminator for that hour. The display is compositing an actual render, not drawing an approximation.
- **Aurora forecasts** from the **[NOAA Space Weather Prediction Center](https://www.swpc.noaa.gov/)**: the **OVATION** auroral precipitation model, which gives the probability of aurora above each point of a global grid, and the **planetary K-index** — both the one-minute series and the three-day outlook. SWPC products are U.S. Government works and in the public domain, so this credit is courtesy rather than obligation. The meteorological aurora model is theirs; what this display adds is the horizon geometry that turns it into an answer for one location. The `[aurora]` page needs no key and no registration.
- **Satellite orbital elements** from **[CelesTrak](https://celestrak.org/)**, as GP element sets, keyless and needing no registration. The satellite page tracks CelesTrak's **`visual`** group, which is the set of objects bright enough to be seen without a telescope, so which objects qualify is CelesTrak's judgement rather than a list kept here. Elements age, so the cache expires rather than falling back indefinitely, and the page credits the set's age beside the passes. Brightness itself is not predicted.
- **The case** is a remix of **"Raspberry Pi Touch Display 2 Case" by RonnyS** ([Printables 1377047](https://www.printables.com/model/1377047-raspberry-pi-touch-display-2-case)), used under CC BY.

## 📄 Licence

**GPL-3.0** — see [LICENSE](LICENSE). Chosen to match [pilomar](https://github.com/Short-bus/pilomar), the Pi miniature-observatory project by Short-bus that this display was inspired by.

**Except `case/`**, which is **CC BY** rather than GPL, because it is a remix of RonnyS's CC-BY model and that licence carries forward. Credit RonnyS and alienryes (`@alienryes_42883` on Printables) if remixed further.

`stand10/` is **GPL-3.0** like the rest of the repository. It is the 10.1 inch panel's stand and is original work, not a remix, so the CC BY attribution requirement does not reach it.
