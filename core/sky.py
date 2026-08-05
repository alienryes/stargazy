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
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from core.palette import STAR_COLOUR
from core.values import _f, _i

# Parallax depth, keyed by the star's size. Bigger stars read as nearer, so they
# drift faster; brightness and depth then reinforce each other instead of
# fighting. Three offsets are computed per frame, not per star.
STAR_DEPTH = {1: 0.25, 2: 0.6, 3: 1.3}

# Drifting cloud sprites. Pre-rendered blurred blobs, count scaled by cloud
# cover; they drift across the sky and dim the stars they pass over.
MAX_CLOUDS = 7
CLOUD_COLOUR = (48, 53, 72)   # muted blue-grey, lighter than the navy sky

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

    def __init__(self, w, h, stars=200, seed=7):
        self.w, self.h = w, h
        random.seed(seed)
        # x, y, base brightness, twinkle phase, twinkle speed, size.
        self.stars = [
            (
                random.randint(0, w - 1),
                random.randint(0, h - 1),
                random.uniform(0.35, 1.0),
                random.uniform(0.0, 2 * math.pi),
                random.uniform(0.4, 2.6),
                1 if random.random() > 0.28 else (2 if random.random() > 0.25 else 3),
            )
            for _ in range(stars)
        ]
        self._sprites = None
        self._bases = None
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
        for x0, y, base, phase, speed, size in self.stars:
            val = base * (0.55 + 0.45 * math.sin(t * speed + phase)) * gain
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

    def spawn_meteor(self):
        return {
            "x": random.uniform(self.w * 0.25, self.w - 10),
            "y": random.uniform(10, self.h * 0.45),
            "vx": -random.uniform(4.0, 7.5),
            "vy": random.uniform(2.0, 4.0),
            "life": 0,
            "max": random.randint(40, 58),
        }

    def step_meteors(self, meteors):
        """Advance and retire meteors in place."""
        for m in meteors[:]:
            m["x"] += m["vx"]
            m["y"] += m["vy"]
            m["life"] += 1
            if m["life"] >= m["max"] or m["y"] > self.h + 20 or m["x"] < -20:
                meteors.remove(m)

    def make_cloud_sprite(self):
        """One soft, translucent cloud: overlapping blobs on an alpha mask, blurred."""
        w = random.randint(360, 540)
        h = random.randint(150, 240)
        mask = Image.new("L", (w, h), 0)
        md = ImageDraw.Draw(mask)
        for _ in range(random.randint(5, 8)):
            cx = random.uniform(w * 0.30, w * 0.70)   # keep blobs off the tile edges
            cy = random.uniform(h * 0.38, h * 0.62)
            rw = random.uniform(w * 0.10, w * 0.22)
            rh = random.uniform(h * 0.14, h * 0.28)
            md.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=random.randint(120, 200))
        mask = mask.filter(ImageFilter.GaussianBlur(w * 0.06))
        # Feather the alpha to zero at the tile border so the sprite never shows a
        # hard rectangular edge where it overlaps the sky.
        env = Image.new("L", (w, h), 0)
        ImageDraw.Draw(env).rectangle([w * 0.14, h * 0.16, w * 0.86, h * 0.84], fill=255)
        env = env.filter(ImageFilter.GaussianBlur(min(w, h) * 0.13))
        mask = ImageChops.multiply(mask, env)
        mask = mask.point(lambda p: int(p * 0.6))   # stars faintly show through
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
    seg, nseg = 11.0, 14
    for i in range(nseg):
        b = fade * (1.0 - i / nseg)
        c = (int(255 * b), int(255 * b), int(235 * b))
        x1, y1 = m["x"] - ux * seg * i, m["y"] - uy * seg * i
        x2, y2 = m["x"] - ux * seg * (i + 1), m["y"] - uy * seg * (i + 1)
        draw.line([(x1, y1), (x2, y2)], fill=c, width=2)
    hb = int(255 * fade)
    draw.ellipse([m["x"] - 2, m["y"] - 2, m["x"] + 2, m["y"] + 2],
                 fill=(hb, hb, int(235 * fade)))
