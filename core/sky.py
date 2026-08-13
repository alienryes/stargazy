"""The live sky the dashboard sits on: gradient, starfield, meteors, clouds.

Everything here is sized by the canvas it was built for, which is why it is a
class rather than a module of functions over globals - two builds with different
panels each hold their own.

The animation is data-reactive but keeps a visible floor in every direction. An
effect that vanishes in the conditions it reports is not reporting them: an
early version drove star gain to 0.15 and switched meteors off under cloud, and
read as a fault rather than as weather.
"""
import math
import random

import numpy as np
from PIL import Image, ImageDraw

from core import cloudfield
from core.palette import STAR_COLOUR
from core.starfield import TWINKLE_SPEED, px_per_degree, scintillation
from core.values import _f, _i

# Parallax depth, keyed by the star's size. Bigger stars read as nearer, so they
# drift faster; brightness and depth then reinforce each other instead of
# fighting. Three offsets are computed per frame, not per star.
# Sizes must cover every band any build's SIZE_BANDS can produce: draw_stars
# indexes this by size, so a band table introducing a size absent here fails on
# the panel rather than in a test.
STAR_DEPTH = {1: 0.25, 2: 0.6, 3: 1.3, 4: 1.8, 5: 2.2, 6: 2.6}

# A meteor's streak is the trail seen side-on, so it shortens towards nothing as
# the path points at the observer. Within this distance of the radiant the
# geometry gives no usable direction, and a meteor is nudged out to it rather
# than drawn along a direction that would be invented.
MIN_RADIANT_PX = 40
# Trail geometry: segment length and count, the drawn length being the product.
# Shower meteors scale the segment by their foreshortening.
TRAIL_SEG, TRAIL_SEGMENTS = 11.0, 14
# Stroke width at the leading end of the trail and at its far end.
#
# The trail was drawn at a flat 2 px with only its brightness fading, behind a
# head 5 px across. A constant-width thread trailing a wider rounded head is a
# tadpole, not a meteor, and the panel duly read as one. A real trail is the
# ablation trail thinning and cooling behind the object, so the width has to go
# with the brightness rather than stay put while it fades.
TRAIL_W_HEAD, TRAIL_W_TAIL = 3, 1
# Exponent on the trail's brightness ramp. Linear left the far end of a 154 px
# trail plainly visible, which is most of what made the streak read as long and
# uniform. Above 1 the light concentrates into the leading third and the rest
# dies away, shortening the APPARENT trail without touching the geometry the
# foreshortening in spawn_meteor is calculated against.
TRAIL_FALLOFF = 1.8
# The head's glare pass: a wider, dimmer stroke laid under the core so the
# bright end reads as over-exposure rather than as a body with an edge to it.
# This is what replaced a pair of filled discs - see draw_meteor.
HEAD_GLARE_W, HEAD_GLARE = 5, 0.30

# How sharply a star's glare falls off from its core, as an exponent on the
# radius. 1.0 is linear; higher concentrates the light into the centre and
# leaves a fainter halo.
#
# NOT A CONFIG KEY, BY DESIGN - as for CORE_BOOST below. Both were tuned by eye
# against the panel over several reversals, and neither stands alone: they act
# with SIZE_BANDS and the SPARSE_* ratios in core/starfield.py, none of which is
# exposed either. Moving one of an interacting set is enough to break the tuning
# and not enough to restore it. Hardware variation is already answered the right
# way - a second calibrated band table per panel, plus the min_size floor.
HALO_FALLOFF = 1.8

# The core is drawn this much brighter than the star's own value, and clipped.
#
# KEEP IT SMALL. At 1.9 everything brighter than magnitude 2.19 clipped to the
# same white, which is most of what makes a constellation - the pattern stars
# run about 1.8 to 3.3 - so the sky lost its shape and read as random again.
# 1.25 clips only magnitude 0.2 and brighter: Vega, Arcturus, Sirius. Those are
# genuinely brilliant and losing the distinction between them is correct.
# A real bright star does not present the eye with a grey dot - it saturates,
# which is why photographs of them blow out at the centre. Without this the
# brightest object on the panel topped out around RGB (203, 205, 217), a light
# grey, and read as flat however large it was drawn. The clip means magnitude
# stops being carried by the core past a point and is carried by the halo
# instead, which is what glare does.
#
# The 1.9 case above is also why this is not exposed in config: a wrong value
# does not read as a setting turned too far, it reads as a defect in the
# starfield. See HALO_FALLOFF.
CORE_BOOST = 1.25

# Cloud drift, stated as an ANGLE and converted to pixels by each build.
#
# It used to be `6.0 + wind * 1.2` pixels a second, two invented numbers with no
# units. Two things were wrong with that. It ran fast: at 6 mph it came to
# 1.97 deg/s on the 5" build against a real 0.077 deg/s for cloud at 2000 m,
# and the offset alone put dead calm at 0.67 deg/s. And because it was in
# PIXELS, the same weather was drawn nearly twice as fast on the 5" panel as on
# the 10", which have different angular scales - a number that reads as a
# property of cloud but is really a property of the canvas.
#
# Cloud at height h moving at v subtends v/h radians a second at the zenith, so
# the base height is the whole calibration and is an assumption, stated here
# rather than buried. Away from the zenith the true rate is lower, so this is
# the fast end of the real range.
CLOUD_BASE_M = 1500.0
# Time compression, declared for the same reason METEOR_COMPRESSION is: the
# honest rate is far too slow to read as motion on an ambient display. This
# scales what the wind is actually doing rather than inventing a speed.
CLOUD_COMPRESSION = 8.0
# Below this the drift is imperceptible over any time anyone looks at the panel.
# Real calm does mean stationary cloud, but a sky that never moves reads as a
# frozen display rather than as still air.
MIN_WIND_KMH = 2.0
MPS_PER_KMH = 1000.0 / 3600.0

NIGHT_GRADIENT = ((6, 8, 20), (15, 17, 42))
TWILIGHT_GRADIENT = ((22, 32, 62), (44, 60, 100))

# Forced vivid clear-sky mood for --demo (visual testing regardless of weather).
DEMO_PARAMS = {"twilight": False, "gain": 1.0, "drift": 6.0, "meteors": True,
               "met_min": 7.0, "met_max": 15.0, "cloud": 30, "cloud_deg_s": 1.7}


def cloud_deg_s(wind_kmh):
    """Apparent drift of cloud across the sky, in degrees a second."""
    v = max(MIN_WIND_KMH, wind_kmh) * MPS_PER_KMH
    return math.degrees(v / CLOUD_BASE_M) * CLOUD_COMPRESSION


def sky_params(states):
    """Derive the sky animation's mood from the conditions."""
    # Obscuration, not raw cover: what the cloud actually stops, which is what
    # the sky layer depicts. See core.weather.cloud_obscuration.
    #
    # Read inline rather than through core.weather.obscuration_of. That module
    # imports requests, and this one is on the render path - pulling requests
    # and urllib3 in behind the starfield is a dependency the sky layer has no
    # use for.
    cloud   = _i(states.get("sensor.astroweather_backyard_cloud_obscuration",
                            states.get("sensor.astroweather_backyard_cloud_cover")))
    seeing  = _i(states.get("sensor.astroweather_backyard_seeing_percentage"))
    transp  = _i(states.get("sensor.astroweather_backyard_transparency"))
    calm    = _i(states.get("sensor.astroweather_backyard_calm_percentage"))
    wind    = _f(states.get("sensor.astroweather_backyard_10m_wind_speed"))
    no_dark = _f(states.get("sensor.astroweather_backyard_astronomical_night_duration")) < 3600

    clarity = max(0.0, min(1.0, (seeing + transp + calm) / 300.0))
    # Keep the sky clearly alive in all conditions; modulate within a visible range.
    gain = (0.60 + 0.40 * clarity) * (1.0 - 0.35 * cloud / 100.0)
    gain = max(0.45, min(1.0, gain))
    if no_dark:
        gain = 0.40                          # twilight: dimmer, few stars
    # Meteors whenever it's dark; rarer (longer gaps) when cloudy/poor.
    met_min = 8.0 + 0.22 * cloud
    return {
        "twilight": no_dark,
        "gain": gain,
        "drift": 2.5 + wind * 0.7,           # px/sec
        "meteors": not no_dark,
        "met_min": met_min,
        "met_max": met_min + 8.0,
        "cloud": cloud,                      # % of sky the cloud field obscures
        "cloud_deg_s": cloud_deg_s(wind),    # degrees of sky per second
    }


class Sky:
    """The animated background for one canvas size.

    The starfield is seeded, so a given build always draws the same sky and a
    rendered frame can be compared byte for byte against an earlier one.
    """

    def __init__(self, w, h, stars=200, seed=7, twinkle=0.018, twinkle_max=0.12, *, fov):
        self.w, self.h = w, h
        # Keyword-only and required, with no default. The cloud drift arrives as
        # an angle and has to be converted here, and the two builds have
        # different angular scales - so any default would be silently wrong on
        # one panel, which is the failure this conversion exists to fix.
        self.px_per_degree = px_per_degree(h, fov)
        # Twinkle amplitude, either side of a centre that stays at 0.55 - so
        # neither of these is a brightness control, only the depth of the
        # trough. `twinkle` is the amplitude AT THE ZENITH and `twinkle_max`
        # the ceiling near the horizon; each star's own value is `twinkle`
        # times its scintillation factor, clamped.
        #
        # Amplitude reads most usefully in magnitudes. The factor runs from
        # 1 - 2a up to 1, so the depth is 2.5 log10(1 / (1 - 2a)): 0.018 is
        # 0.04 mag and 0.12 is 0.30. The field shipped at a flat 0.45 about a
        # centre of 0.55, which is 1.33 mag - four to ten times what real
        # scintillation does - and read as the whole sky breathing.
        #
        # NEARLY NOTHING OVERHEAD, A LITTLE NEAR THE HORIZON. A star at the
        # zenith is genuinely steady, and the cycle here runs 5 to 31 seconds
        # against real scintillation's tens of hertz, which 12 fps cannot draw
        # and never will. At 0.20 mag on every star that slow swing read as
        # breathing rather than twinkling - and it got worse, not better, when
        # the field was cut from 1200 dim stars to 200 bright ones, because the
        # pulse became legible on individual objects instead of lost in a
        # crowd. The zenith figure is now imperceptible and the horizon cap is
        # 0.30 mag, the top of what real scintillation does at mid altitude,
        # reached below about 18 degrees.
        #
        # The floor also has to keep stars out of draw_stars' cull at 0.05. The
        # faintest star drawn has a base of 0.25 under the sparse profile and
        # the lowest gain the display produces is 0.40 in twilight, so the
        # trough is 0.25 x (1 - 2a) x 0.40, which stays above the cull for any
        # amplitude under 0.25. The ceiling here is well inside that.
        self.twinkle = twinkle
        self.twinkle_max = twinkle_max
        random.seed(seed)
        # x, y, base brightness, twinkle phase, twinkle speed, size, and the
        # scintillation factor. This field is the fallback used when a build
        # has not supplied real positions, so it has no true altitudes; height
        # up the canvas stands in for one, which is the same thing the eye
        # assumes when it looks at it.
        # An explicit loop rather than a comprehension, so x is drawn before y
        # exactly as before. The order matters beyond this field: the global
        # random stream is shared with the cloud sprites and the meteors, and
        # swapping two draws here would shift everything after them.
        self.stars = []
        for _ in range(stars):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - 1)
            self.stars.append((
                x, y,
                random.uniform(0.35, 1.0),
                random.uniform(0.0, 2 * math.pi),
                random.uniform(*TWINKLE_SPEED),
                1 if random.random() > 0.28 else (2 if random.random() > 0.25 else 3),
                scintillation(90.0 * (1.0 - y / h)),
            ))
        # The cloud field, built once; and the strip built from it for the
        # current (twilight, cover), which is rebuilt when either moves.
        self._field = None
        self._cloud_rgb = None
        self._cloud = ()
        # Meteor radiants for right now, as (x, y, weight) with x and y None for
        # the sporadic floor. Empty means no build supplied any, and meteors
        # then spawn from nowhere in particular as they always did.
        self._radiants = []
        self._px_per_degree = None
        # Seeded points drift to suggest motion. Real stars do not need to be
        # suggested - they move because the positions are recomputed - so a
        # build supplying them turns this off via set_stars().
        self.star_drift = True

    def set_stars(self, stars, drift=False):
        """Replace the starfield, e.g. with real positions for this moment."""
        self.stars = stars
        self.star_drift = drift

    def gradient_column(self, twilight):
        """The sky gradient as one column, (H, 1, 3), to be broadcast over the field.

        A column rather than a full canvas because the gradient is constant
        along x: materialising it at field width cost a 27 MB allocation per
        cover change on the 10" build and bought nothing that broadcasting does
        not do for free.
        """
        top, bot = TWILIGHT_GRADIENT if twilight else NIGHT_GRADIENT
        top = np.array(top, dtype=np.float32)
        bot = np.array(bot, dtype=np.float32)
        col = top + (bot - top) * (np.arange(self.h, dtype=np.float32)[:, None] / self.h)
        return col[:, None, :]

    @property
    def field_w(self):
        """Width of the cloud field, and the distance drift travels before it repeats."""
        return self.w * cloudfield.FIELD_WIDTHS

    def clouded_base(self, twilight, cover):
        """Gradient with the cloud field composited on, plus a wrap margin, cached.

        WIDER THAN THE CANVAS SO THAT DRIFT IS A CROP. Sliding a window along a
        prepared strip is a memcpy; compositing a full-canvas cloud layer every
        frame instead would cost more than the whole animation has spare on a
        build already at 12 fps.

        The strip is the field once plus its first canvas-width repeated at the
        end, so a window running off the end wraps onto the start without a
        seam - the field being periodic over its own width is what makes the
        join invisible.

        Cover only moves on a data refresh, so one strip serves thousands of
        frames.

        TWO ARE KEPT, NOT ONE, and one entry was measured to defeat the whole
        arrangement. The refresher builds the new strip ahead of the render
        loop so the loop never pays for it; with a single slot, building the new
        one evicts the old, and the loop - still drawing the previous cover
        until the new parameters are published - misses and rebuilds it. The two
        threads then take turns evicting each other. Holding the previous key as
        well makes the handover free from either direction, and removes any need
        to order the publish against the build.

        Entries are newest-last and the tuple is REBOUND rather than mutated, so
        a reader takes a consistent snapshot without a lock.
        """
        key = (bool(twilight), int(cover))
        cached = next((e for e in self._cloud if e[0] == key), None)
        if cached is None:
            if self._field is None:
                # Feature size comes from the CANVAS, not from this array - see
                # make_field. The cloud's own colour follows the field and not
                # the cover, so it is built once alongside it.
                self._field = cloudfield.make_field(
                    self.field_w, self.h, min(self.w, self.h))
                self._cloud_rgb = cloudfield.make_tone_rgb(self._field)
            alpha = cloudfield.alpha_for(self._field, cover / 100.0)
            # Blended here rather than through Image.alpha_composite, which
            # wants both sides as full RGBA canvases - two more allocations the
            # width of the field, for a blend numpy does in one pass.
            a = alpha[..., None].astype(np.float32) / 255.0
            arr = (self.gradient_column(twilight) * (1.0 - a)
                   + self._cloud_rgb * a).astype(np.uint8)
            one = Image.fromarray(arr, "RGB")
            strip = Image.new("RGB", (self.field_w + self.w, self.h))
            strip.paste(one, (0, 0))
            strip.paste(one.crop((0, 0, self.w, self.h)), (self.field_w, 0))
            # Kept as flat BYTES, not as the numpy array it was built from.
            # Stars and meteors read it one point at a time, and indexing a
            # numpy array per point builds a numpy scalar object each time:
            # measured at 13.2 ms a frame for 841 stars on the Pi 4, over half
            # the whole sky layer. Indexing bytes yields a plain int and costs
            # a fraction of that. Nothing here ever needs it as an array.
            cached = (key, strip, alpha.tobytes(), alpha.shape[1])
            self._cloud = (self._cloud[-1:] + (cached,))[-2:]
        return cached[1], cached[2], cached[3]

    def draw_stars(self, draw, t, params, alpha=None, alpha_w=0, off=0,
                   frame=None):
        w, gain = self.w, params["gain"]
        if self.star_drift:
            drift = {s: (t * params["drift"] * d) % w for s, d in STAR_DEPTH.items()}
        else:
            drift = dict.fromkeys(STAR_DEPTH, 0.0)
        for x0, y, base, phase, speed, size, scint in self.stars:
            # Amplitude is per star, from the airmass its light crosses: nearly
            # steady overhead, shimmering low down. A single figure for the
            # whole field overstates the zenith and understates the horizon.
            amp = min(self.twinkle_max, self.twinkle * scint)
            # The twinkle PEAKS at 1.0 rather than oscillating about 0.55.
            # That 0.55 was written as the centre of the swing, but it was also
            # a permanent 45% cut on every star: the brightest object in the sky
            # rendered at RGB (114, 115, 122) - mid grey - which is why stars
            # read as flat and dim rather than as points of light. Dropping the
            # amplitude made it worse by removing the top of the swing as well.
            # Now a star reaches its full magnitude-derived brightness at the
            # top of the cycle and dips below it, which is also what a real one
            # does: scintillation takes light away, it does not add any.
            val = base * (1.0 - amp + amp * math.sin(t * speed + phase)) * gain
            x = (x0 + drift[size]) % w
            if alpha is not None:
                # Occluded by the cloud actually in front of THIS star, rather
                # than by a single factor applied to the whole field. A global
                # dimming cannot tell a covered star from an uncovered one, so
                # it washes out the clear half of a broken sky as well.
                #
                # Wrapped on the FIELD's width, not the canvas's: the field is
                # several canvases wide, and taking the modulo of the narrower
                # one would sample the wrong column for most of the drift.
                val *= 1.0 - alpha[y * alpha_w + int(x + off) % alpha_w] / 255.0
            if val <= 0.05:
                continue
            light = tuple(int(ch * val) for ch in STAR_COLOUR)
            # A CORE WITH A HALO, NOT A DISC. Every star used to be one filled
            # ellipse in a single colour - a size-6 star was 97 pixels at
            # exactly the same value, which reads as a smudge rather than a
            # light. Magnitude is carried by how far the glare reaches, which is
            # what glare actually does, while the centre stays a sharp point.
            #
            # The background is sampled ONCE, at the centre, and every ring is
            # computed from it. Sampling per ring would read back the ring just
            # drawn and compound the addition.
            bg = frame.getpixel((int(x), y)) if frame is not None else (0, 0, 0)
            for rr in range(size - 1, 0, -1):
                k = (1.0 - rr / size) ** HALO_FALLOFF
                ring = (min(255, bg[0] + int(light[0] * k)),
                        min(255, bg[1] + int(light[1] * k)),
                        min(255, bg[2] + int(light[2] * k)))
                draw.ellipse([x - rr, y - rr, x + rr, y + rr], fill=ring)
            c = (min(255, bg[0] + int(light[0] * CORE_BOOST)),
                 min(255, bg[1] + int(light[1] * CORE_BOOST)),
                 min(255, bg[2] + int(light[2] * CORE_BOOST)))
            draw.point((x, y), fill=c)
            # NO GLINT CROSS. A nine-pixel cross drawn through a seven-pixel
            # star is a plus sign, not a star, and it was the strongest thing
            # on the panel once the discs were tightened. A saturated core says
            # "this one is brilliant" without drawing a diffraction spike the
            # naked eye does not see.


    def set_radiants(self, radiants, px_per_degree):
        """Where tonight's showers radiate from, in canvas coordinates.

        `radiants` is [(x, y, weight)], one row per active shower plus one for
        the sporadic floor carried as x and y of None. The weights need not be
        normalised and are the relative rates: cloud and moonlight cancel out of
        the ratio between showers, because they cut every shower and the
        sporadics by the same factor, so only the shower rate and the radiant's
        altitude decide which stream a given meteor belongs to.

        `px_per_degree` converts a distance on the canvas into an angle, which
        is what sets how foreshortened a meteor's trail is.
        """
        self._radiants = radiants
        self._px_per_degree = px_per_degree

    def _pick_radiant(self):
        """One radiant drawn in proportion to its rate, or None for a sporadic."""
        total = sum(w for _, _, w in self._radiants)
        if total <= 0:
            return None
        r = random.uniform(0.0, total)
        for x, y, weight in self._radiants:
            r -= weight
            if r <= 0.0:
                return None if x is None else (x, y)
        return None

    def spawn_meteor(self):
        """One meteor, radiating from a real shower where there is one.

        A sporadic belongs to no stream and genuinely has no preferred
        direction, so it keeps the arbitrary one this display always used. Only
        a shower meteor gets its direction from the sky.
        """
        if not self._radiants:
            return self._spawn_undirected()
        radiant = self._pick_radiant()
        if radiant is None:
            return self._spawn_undirected()

        rx, ry = radiant
        # The meteor appears somewhere on the panel and travels away from the
        # radiant. Taking the appearance point first, rather than an angle from
        # the radiant, means it is on the canvas by construction - which matters
        # because the radiant itself is often off it.
        x = random.uniform(0.0, self.w)
        y = random.uniform(0.0, self.h * 0.85)
        dx, dy = x - rx, y - ry
        dist = math.hypot(dx, dy)
        if dist < MIN_RADIANT_PX:
            # Too close to have a direction: push it out to where it does.
            if dist < 1e-6:
                dx, dy, dist = 1.0, 0.0, 1.0
            x, y = rx + dx / dist * MIN_RADIANT_PX, ry + dy / dist * MIN_RADIANT_PX
            dx, dy, dist = x - rx, y - ry, MIN_RADIANT_PX

        # Trails shorten towards the radiant because the path is then pointing
        # at the observer. The angular distance is what governs it, so the pixel
        # distance is converted before the sine rather than after.
        theta = min(90.0, dist / self._px_per_degree)
        speed = random.uniform(4.5, 8.5)
        return {
            "x": x, "y": y,
            "vx": dx / dist * speed,
            "vy": dy / dist * speed,
            "seg": TRAIL_SEG * max(0.25, math.sin(math.radians(theta))),
            "life": 0,
            "max": random.randint(40, 58),
        }

    def _spawn_undirected(self):
        """The original arbitrary meteor: down and to the left, from the top right."""
        return {
            "x": random.uniform(self.w * 0.25, self.w - 10),
            "y": random.uniform(10, self.h * 0.45),
            "vx": -random.uniform(4.0, 7.5),
            "vy": random.uniform(2.0, 4.0),
            "seg": TRAIL_SEG,
            "life": 0,
            "max": random.randint(40, 58),
        }

    def step_meteors(self, meteors):
        """Advance and retire meteors in place.

        Radiants put meteors on any heading, so all four edges retire them; the
        original only ever needed the two it travelled towards.
        """
        for m in meteors[:]:
            m["x"] += m["vx"]
            m["y"] += m["vy"]
            m["life"] += 1
            off = (m["x"] < -20 or m["x"] > self.w + 20
                   or m["y"] < -20 or m["y"] > self.h + 20)
            if m["life"] >= m["max"] or off:
                meteors.remove(m)

    def paint(self, params, t, meteors, scroll):
        """A fresh sky frame: cloud over gradient, then stars, then meteors.

        `scroll` is how far the cloud has drifted, in DEGREES of sky - the unit
        the weather is in. Converting here rather than at the source is what
        makes the two builds depict the same wind at the same apparent rate
        despite their different angular scales. Cloud moves left to right, so
        the window travels the other way along the strip.
        """
        cover = params.get("cloud", 0)
        strip, alpha, alpha_w = self.clouded_base(params["twilight"], cover)
        off = int(-scroll * self.px_per_degree) % self.field_w
        frame = strip.crop((off, 0, off + self.w, self.h))
        d = ImageDraw.Draw(frame)
        self.draw_stars(d, t, params, alpha, alpha_w, off, frame)
        for m in meteors:
            draw_meteor(d, m, alpha, alpha_w, off, frame)
        return frame


def _lit(frame, x, y, light):
    """`light` added to whatever is already at (x, y), clamped.

    STARS AND METEORS ADD LIGHT; THEY DO NOT REPLACE THE SKY. Drawing them as a
    flat colour meant anything dimmer than its background was painted ON as a
    DARK speck - the sky showing through a hole where a star should be. It was
    not a corner case: measured over this field, a poor night under 90% cloud
    drew 222 stars darker than the sky against 5 brighter, and twilight drew
    1977 against none. The cloud rewrite made it worse by putting a much
    lighter background behind the stars far more of the time.
    """
    if frame is None:
        return light
    w, h = frame.size
    xi, yi = int(x), int(y)
    if not (0 <= xi < w and 0 <= yi < h):
        return light
    bg = frame.getpixel((xi, yi))
    return (min(255, bg[0] + light[0]),
            min(255, bg[1] + light[1]),
            min(255, bg[2] + light[2]))


def _clear_at(alpha, w, off, x, y):
    """How much light gets through the cloud at one canvas point, 0 to 1.

    A meteor burns up around 100 km and cloud sits at two or three, so cloud is
    always the nearer of the two and a trail crossing it is hidden. Sampled
    along the trail rather than applied to the meteor as a whole, because a
    streak is long enough to be under cloud at one end and in the clear at the
    other.

    Meteors are retired a little way off the canvas, so a sampled point can be
    outside it; those count as clear, which is what the sky beyond the panel is
    for anything the display cannot see.
    """
    if alpha is None:
        return 1.0
    yi = int(y)
    if yi < 0 or yi * w >= len(alpha):
        return 1.0
    return 1.0 - alpha[yi * w + int(x + off) % w] / 255.0


def draw_meteor(draw, m, alpha=None, alpha_w=0, off=0, frame=None):
    frac = m["life"] / m["max"]
    fade = math.sin(math.pi * min(1.0, frac))
    mag = math.hypot(m["vx"], m["vy"])
    ux, uy = m["vx"] / mag, m["vy"] / mag
    seg, nseg = m["seg"], TRAIL_SEGMENTS
    for i in range(nseg):
        x1, y1 = m["x"] - ux * seg * i, m["y"] - uy * seg * i
        x2, y2 = m["x"] - ux * seg * (i + 1), m["y"] - uy * seg * (i + 1)
        along = i / nseg
        b = fade * (1.0 - along) ** TRAIL_FALLOFF
        b *= _clear_at(alpha, alpha_w, off, (x1 + x2) / 2.0, (y1 + y2) / 2.0)
        # Skipped rather than drawn dark. A fully occluded segment still has a
        # colour, and drawing it would paint the trail on in black instead of
        # leaving the cloud where it is.
        if b <= 0.02:
            continue
        c = _lit(frame, (x1 + x2) / 2.0, (y1 + y2) / 2.0,
                 (int(255 * b), int(255 * b), int(235 * b)))
        w = max(TRAIL_W_TAIL,
                int(round(TRAIL_W_HEAD - (TRAIL_W_HEAD - TRAIL_W_TAIL) * along)))
        draw.line([(x1, y1), (x2, y2)], fill=c, width=w)
    # The head covers the ground crossed since the previous frame rather than
    # marking a point. A meteor steps 4.5-8.5 px between frames against a head
    # a few px across, so a round head lands clear of where it last was: rendering
    # three consecutive frames into separate channels shows three separated
    # blobs riding a continuous trail. The path is not gapped - the leading
    # trail segment is full brightness and 11 px long - so what beads is the
    # WIDTH, a bright dot hopping along a thin thread.
    #
    # That is why this reads as judder at any frame rate the panel can hold.
    # Measured on the 10.1" build, frame times run a median of 66 ms with a p99
    # of 74, so 14 fps overruns its budget on 15% of frames where 12 overruns
    # on 0.3% - raising the rate would deliver frames less evenly, not more.
    # A capsule spanning the step tiles continuously at any speed and any rate,
    # by construction, and is also what a camera would record.
    #
    # WHAT THE CAPSULE IS NOT ALLOWED TO BE IS A BULB. It was drawn 5 px wide
    # with a filled disc capping each end, against a 2 px trail: a hard-edged
    # round head stuck on a thread, which is a spermatozoon and was read as one.
    # The head now carries the same width as the trail's leading segment, so it
    # is a brighter continuation of the streak rather than a separate object,
    # and the discs are gone along with the step change that needed them.
    #
    # Brightness past that point is carried by glare instead of by size, the same
    # trade CORE_BOOST makes for stars: a dim wide pass laid down first, then the
    # core over it. _lit samples the frame, so the core adds to the glare already
    # there and saturates towards white at the centre, which is how an
    # over-exposed streak actually resolves.
    px, py = m["x"] - m["vx"], m["y"] - m["vy"]
    hf = fade * _clear_at(alpha, alpha_w, off, (px + m["x"]) / 2.0, (py + m["y"]) / 2.0)
    if hf <= 0.02:
        return
    for width, level in ((HEAD_GLARE_W, HEAD_GLARE), (TRAIL_W_HEAD, 1.0)):
        hb = hf * level
        head = _lit(frame, (px + m["x"]) / 2.0, (py + m["y"]) / 2.0,
                    (int(255 * hb), int(255 * hb), int(235 * hb)))
        draw.line([(px, py), (m["x"], m["y"])], fill=head, width=width)
