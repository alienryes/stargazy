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
from PIL import Image, ImageDraw, ImageFilter

from core.palette import STAR_COLOUR
from core.starfield import TWINKLE_SPEED, scintillation
from core.values import _f, _i

# Parallax depth, keyed by the star's size. Bigger stars read as nearer, so they
# drift faster; brightness and depth then reinforce each other instead of
# fighting. Three offsets are computed per frame, not per star.
STAR_DEPTH = {1: 0.25, 2: 0.6, 3: 1.3}

# Drifting cloud sprites. Pre-rendered blurred blobs, count scaled by cloud
# cover; they drift across the sky and dim the stars they pass over.
MAX_CLOUDS = 7
CLOUD_COLOUR = (48, 53, 72)   # muted blue-grey, lighter than the navy sky
# Opacity at the densest point of a sprite. Cloud thick enough to report is
# thick enough to hide stars, so the core is nearly opaque and the softness
# lives at the edges, where thin cloud belongs. Stated as a fraction because
# the previous blind multiplier left the peak at 36-45% - measured - and no
# number of half-transparent sprites reads as overcast.
CLOUD_PEAK_ALPHA = 0.92

# A meteor's streak is the trail seen side-on, so it shortens towards nothing as
# the path points at the observer. Within this distance of the radiant the
# geometry gives no usable direction, and a meteor is nudged out to it rather
# than drawn along a direction that would be invented.
MIN_RADIANT_PX = 40
# Trail geometry: segment length and count, the drawn length being the product.
# Shower meteors scale the segment by their foreshortening.
TRAIL_SEG, TRAIL_SEGMENTS = 11.0, 14
# Radius of the meteor's bright head. It is drawn as a capsule spanning one
# frame's travel rather than a dot - see draw_meteor for why.
HEAD_R = 2

NIGHT_GRADIENT = ((6, 8, 20), (15, 17, 42))
TWILIGHT_GRADIENT = ((22, 32, 62), (44, 60, 100))

# Forced vivid clear-sky mood for --demo (visual testing regardless of weather).
DEMO_PARAMS = {"twilight": False, "gain": 1.0, "drift": 6.0, "meteors": True,
               "met_min": 7.0, "met_max": 15.0, "cloud": 30, "cloud_speed": 14.0}


def sky_params(states):
    """Derive the sky animation's mood from the conditions."""
    cloud   = _i(states.get("sensor.astroweather_backyard_cloud_cover"))
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
        "cloud": cloud,                      # % -> number of drifting cloud sprites
        "cloud_speed": 6.0 + wind * 1.2,     # px/sec
    }


class Sky:
    """The animated background for one canvas size.

    The starfield is seeded, so a given build always draws the same sky and a
    rendered frame can be compared byte for byte against an earlier one.
    """

    def __init__(self, w, h, stars=200, seed=7, twinkle=0.05, twinkle_max=0.20):
        self.w, self.h = w, h
        # Twinkle amplitude, either side of a centre that stays at 0.55 - so
        # neither of these is a brightness control, only the depth of the
        # trough. `twinkle` is the amplitude AT THE ZENITH and `twinkle_max`
        # the ceiling near the horizon; each star's own value is `twinkle`
        # times its scintillation factor, clamped.
        #
        # Amplitude reads most usefully in magnitudes: the swing is a ratio of
        # (0.55 + a) to (0.55 - a), so 0.05 is 0.20 mag, 0.12 is 0.48 and 0.20
        # is 0.83. The field shipped at a flat 0.45, which is 1.33 mag - four
        # to ten times what real scintillation does - and read as the whole sky
        # breathing rather than twinkling.
        #
        # The floor also has to keep stars out of draw_stars' cull at 0.05. The
        # faintest star's base is 0.560 and the lowest gain the display
        # produces is 0.40 in twilight, so the trough is 0.560 x (0.55 - a) x
        # 0.40, which stays above the cull for any amplitude under 0.327. The
        # ceiling here is well inside that.
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
        self._sprites = None
        self._bases = None
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

    def make_base(self, top, bot):
        """Vertical gradient background, built once."""
        top = np.array(top, dtype=np.float32)
        bot = np.array(bot, dtype=np.float32)
        col = (top + (bot - top) * (np.arange(self.h)[:, None] / self.h)).astype(np.uint8)
        arr = np.repeat(col[:, None, :], self.w, axis=1)  # (H,W,3)
        return Image.fromarray(arr, "RGB")

    def base(self, twilight):
        if self._bases is None:
            self._bases = (self.make_base(*NIGHT_GRADIENT),
                           self.make_base(*TWILIGHT_GRADIENT))
        return self._bases[1] if twilight else self._bases[0]

    def draw_stars(self, draw, t, params):
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
            val = base * (0.55 + amp * math.sin(t * speed + phase)) * gain
            if val <= 0.05:
                continue
            c = tuple(int(ch * val) for ch in STAR_COLOUR)
            x = (x0 + drift[size]) % w
            if size == 1:
                draw.point((x, y), fill=c)
            else:
                r = size - 1
                draw.ellipse([x - r, y - r, x + r, y + r], fill=c)
                if size == 3 and val > 0.7:  # faint glint on the brightest stars
                    g = tuple(int(ch * val * 0.5) for ch in STAR_COLOUR)
                    draw.line([(x - 4, y), (x + 4, y)], fill=g, width=1)
                    draw.line([(x, y - 4), (x, y + 4)], fill=g, width=1)

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

    def make_cloud_sprite(self):
        """One soft, translucent cloud: overlapping blobs on an alpha mask, blurred.

        Sized as a FRACTION of the canvas, not in absolute pixels. Fixed sizes
        were tuned on 1280x720 and covered 6-10% of it each, so seven of them
        overlapped into a continuous cloud field. The same sprites on a 1200x1920
        panel cover 3.5-4.7%, stop overlapping, and each one's own rectangular
        footprint becomes visible - clouds that read as blocks rather than as
        weather. The fractions below reproduce the original ranges on the 5"
        canvas, so every panel now gets the same proportion of sky covered.

        The blur radii are already relative to the sprite, so they follow.

        THE BLOBS ARE THEIR OWN SILHOUETTE. An earlier version multiplied the
        mask by a blurred RECTANGLE, to feather the alpha to zero before the
        tile border. That did stop the edge being HARD, which is what its
        comment claimed, but it did not stop it being STRAIGHT: the blobs
        reached past the rectangle, so wherever they did, the visible outline
        was the envelope, and clouds came out flat-sided. Measured on the 10"
        sprites, 12-49% of each one's rows ended within 2 px of its widest
        point, against about 13% for a circle.

        The envelope is gone. The blobs are kept far enough inside that the
        blur falls to zero within the tile on its own, so the outline is the
        union of overlapping ellipses.

        THAT IS NOT ENOUGH ON ITS OWN, and the first attempt at this proved it:
        removing the envelope left the silhouette just as flat, because 5-8
        lobes that large, packed into a band 40% of the tile wide, meet in long
        smooth arcs that read as straight once blurred. A lumpy outline needs
        MORE and SMALLER lobes spread WIDER, each comfortably larger than the
        blur so its bump survives it.
        """
        w = random.randint(int(self.w * 0.28), int(self.w * 0.42))
        h = random.randint(int(self.h * 0.21), int(self.h * 0.33))
        mask = Image.new("L", (w, h), 0)
        md = ImageDraw.Draw(mask)
        # The count changes the number of draws taken from the shared stream, so
        # cloud and meteor spawn positions differ from before. The fallback
        # starfield does not: it is drawn in __init__, before any sprite exists.
        for _ in range(random.randint(9, 14)):
            # Radii bounded so blob span plus blur stays inside the tile: there
            # is no envelope to rescue an overshoot, and a blob reaching the
            # border would put back the hard edge this is avoiding.
            cx = random.uniform(w * 0.30, w * 0.70)
            cy = random.uniform(h * 0.36, h * 0.64)
            rw = random.uniform(w * 0.11, w * 0.16)
            rh = random.uniform(h * 0.13, h * 0.20)
            md.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=random.randint(120, 200))
        # Softer than the lobes are wide, so the bumps survive it. Scaled by the
        # SHORTER side: the 5" tiles are about 2.3:1, so a radius taken from the
        # width alone would be as large as their lobes are tall and would smooth
        # the outline straight back out on that build.
        mask = mask.filter(ImageFilter.GaussianBlur(min(w, h) * 0.05))
        # Scaled to a STATED peak rather than by a blind fraction. Overlapping
        # ellipses overwrite rather than accumulate, and the blur then takes the
        # maximum down further, so what a multiplier leaves at the core is not
        # knowable by reading it - it measured 36-45% where 60% was intended.
        peak = mask.getextrema()[1]
        if peak:
            k = CLOUD_PEAK_ALPHA * 255.0 / peak
            mask = mask.point(lambda p: min(255, int(p * k)))
        sprite = Image.new("RGBA", (w, h), CLOUD_COLOUR + (0,))
        sprite.putalpha(mask)
        return sprite

    def cloud_sprites(self):
        if self._sprites is None:
            self._sprites = [self.make_cloud_sprite() for _ in range(5)]
        return self._sprites

    def spawn_cloud(self):
        sp = random.choice(self.cloud_sprites())
        if random.random() < 0.5:
            sp = sp.transpose(Image.FLIP_LEFT_RIGHT)
        return {"sprite": sp,
                "x": random.uniform(-sp.width, self.w),
                "y": random.randint(-40, int(self.h * 0.72)),
                "depth": random.uniform(0.75, 1.35)}   # parallax: clouds separate

    def initial_clouds(self, params):
        n = round(params.get("cloud", 0) / 100 * MAX_CLOUDS)
        return [self.spawn_cloud() for _ in range(n)]

    def step_clouds(self, clouds, params, frame_dt):
        """Match the count to cover, drift across, recycle off the right edge."""
        tgt = round(params["cloud"] / 100 * MAX_CLOUDS)
        while len(clouds) > tgt:
            clouds.pop()
        while len(clouds) < tgt:
            clouds.append(self.spawn_cloud())
        for c in clouds:
            c["x"] += params["cloud_speed"] * c["depth"] * frame_dt
            if c["x"] > self.w:
                c["x"] = -c["sprite"].width
                c["y"] = random.randint(-40, int(self.h * 0.72))

    def paint(self, params, t, meteors, clouds):
        """A fresh sky frame: gradient, stars, clouds, meteors."""
        frame = self.base(params["twilight"]).copy()
        d = ImageDraw.Draw(frame)
        self.draw_stars(d, t, params)
        for c in clouds:
            frame.paste(c["sprite"], (int(c["x"]), c["y"]), c["sprite"])
        for m in meteors:
            draw_meteor(d, m)
        return frame


def draw_meteor(draw, m):
    frac = m["life"] / m["max"]
    fade = math.sin(math.pi * min(1.0, frac))
    mag = math.hypot(m["vx"], m["vy"])
    ux, uy = m["vx"] / mag, m["vy"] / mag
    seg, nseg = m["seg"], TRAIL_SEGMENTS
    for i in range(nseg):
        b = fade * (1.0 - i / nseg)
        c = (int(255 * b), int(255 * b), int(235 * b))
        x1, y1 = m["x"] - ux * seg * i, m["y"] - uy * seg * i
        x2, y2 = m["x"] - ux * seg * (i + 1), m["y"] - uy * seg * (i + 1)
        draw.line([(x1, y1), (x2, y2)], fill=c, width=2)
    # The head covers the ground crossed since the previous frame rather than
    # marking a point. A meteor steps 4.5-8.5 px between frames against a head
    # 5 px across, so a round head lands clear of where it last was: rendering
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
    hb = int(255 * fade)
    head = (hb, hb, int(235 * fade))
    px, py = m["x"] - m["vx"], m["y"] - m["vy"]
    draw.line([(px, py), (m["x"], m["y"])], fill=head, width=HEAD_R * 2 + 1)
    for cx, cy in ((m["x"], m["y"]), (px, py)):
        draw.ellipse([cx - HEAD_R, cy - HEAD_R, cx + HEAD_R, cy + HEAD_R],
                     fill=head)
