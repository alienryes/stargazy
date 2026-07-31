"""Render an exploded assembly diagram from the actual part STLs.

Produces `assembly.png`: an exploded isometric view with the parts separated
along the stack axis, dashed centre-lines showing every fastener path, and
numbered callouts - the same style as RonnyS's assembly sheet for the 7" case.

Because it is built from the exported STLs and the real assembly transforms,
it cannot drift from the parts: re-run it after changing any script.

Assembly frame: Z = 0 at the shell back plate's OUTER face, +Z rearward
(away from the display), X = display long axis, Y = short axis.

    python assembly_diagram.py [pi4|pi5]
"""

import math
import os
import sys

import numpy as np
import pi_models as pm
import pyrender
import trimesh
from PIL import Image, ImageDraw, ImageFont

VERSION = "0.5.0"

PI_MODEL = sys.argv[1] if len(sys.argv) > 1 else "pi4"
assert PI_MODEL in pm.PI_MODELS, f"unknown model {PI_MODEL}"

W, H = 2200, 1560
ELEV, AZIM = 30.0, 128.0             # 128 = -52 + 180 (view from the far side)
COL_L, COL_R = 560, 1545             # x of the callout discs in each column
ZOOM = 1.28                          # >1 pulls the camera back, leaving margin

# ── assembly constants (must match the part scripts) ──────────────────────
DISP_W, DISP_H, DISP_D = 143.4, 91.46, 15.9
PI_W, PI_H, PI_T = 85.0, 56.0, 1.4
PI_X0, PI_Y0, PI_Z0 = -41.2, -28.0, 6.0
FACE_Y0, FACE_Z0 = -51.01, 2.5
STAND_X, LEG_W = 56.0, 14.0           # strap centre in X, and its width
STAND_TILT = 20                      # which stand variant the diagram shows

CASE_SCREWS = [(sx * 51.85, sy * 25.5) for sx in (1, -1) for sy in (1, -1)]
# one chain now runs display standoff -> extender -> Pi -> standoff -> lid
EXTENDERS = [(x, sy * 24.5) for x in (-37.7, 20.3) for sy in (1, -1)]
LID_Z_OUTER = 30.4    # case_top z_outer

# ── explosion offsets along Z (stands also move in X) ─────────────────────
EX_DISPLAY, EX_SHELL, EX_BOTTOM = -95.0, -50.0, 0.0
EX_PI, EX_TOP, EX_STAND_X = 42.0, 100.0, 52.0


def rot(axis, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    m = np.eye(4)
    if axis == "x":
        m[1, 1], m[1, 2], m[2, 1], m[2, 2] = c, -s, s, c
    else:
        m[0, 0], m[0, 2], m[2, 0], m[2, 2] = c, s, -s, c
    return m


def tr(x=0.0, y=0.0, z=0.0):
    m = np.eye(4)
    m[0:3, 3] = (x, y, z)
    return m


def load(name, matrix):
    m = trimesh.load(name)
    m.apply_transform(matrix)
    return m


def box(w, h, d, cx, cy, z0):
    m = trimesh.creation.box(extents=(w, h, d))
    m.apply_translation((cx, cy, z0 + d / 2))
    return m


# ── parts, each already in ASSEMBLY coordinates, then exploded ────────────
# shell: modelled with the pocket opening toward +Z, so it rotates 180 deg
#        about X (it is symmetric in Y, so nothing is mirrored in practice)
# case_top: modelled in print orientation, flips 180 deg about Y then +32
# stand: local (x=along face, y=off face, z=width) -> (X=z, Y=x, Z=y)
_stand_perm = np.array([[0, 0, 1, 0],
                        [1, 0, 0, FACE_Y0],
                        [0, 1, 0, FACE_Z0],
                        [0, 0, 0, 1]], dtype=float)

# A detailed Pi 4B model makes a far clearer diagram than a bare slab, but it
# is third-party and lives in the gitignored reference/ folder, so fall back to
# a plain board for anyone who does not have it.
# Its frame is X = long axis, Y = height, Z = short axis, PCB bottom at Y = 0;
# rotating +90 about X and shifting to the board centre lands it exactly on the
# designed position (x -41.2..43.8, y +-28, PCB bottom z 6.0).
PI_STL = os.path.join("reference", {
    "pi4": "Raspberry Pi 4 Model B.stl",
    "pi5": "RASPBERRY_PI_5_.stl",
}[PI_MODEL])
if os.path.exists(PI_STL):
    pi_part = load(PI_STL, tr(1.3, 0.0, PI_Z0) @ rot("x", 90))
else:
    pi_part = box(PI_W, PI_H, PI_T, PI_X0 + PI_W / 2, PI_Y0 + PI_H / 2, PI_Z0)
    print("note: reference Pi model not found - using a plain board")

PARTS = [
    ("Touch Display 2 (5\")", box(DISP_W, DISP_H, DISP_D, 0, 0, -18.4),
     tr(z=EX_DISPLAY), (0.72, 0.24, 0.24)),
    ("shell", load("shell.stl", rot("x", 180)),
     tr(z=EX_SHELL), (0.93, 0.62, 0.24)),
    ("case_bottom", load(f"case_bottom_{PI_MODEL}.stl", np.eye(4)),
     tr(z=EX_BOTTOM), (0.93, 0.62, 0.24)),
    (pm.label(PI_MODEL), pi_part, tr(z=EX_PI), (0.24, 0.52, 0.30)),
    ("case_top", load(f"case_top_{PI_MODEL}.stl",
                      tr(z=LID_Z_OUTER) @ rot("y", 180)),
     tr(z=EX_TOP), (0.93, 0.62, 0.24)),
    # the stands are handed: each file's own leg-z 0 edge is its INBOARD one,
    # so the -X part is placed from -strap_x1 rather than being mirrored here
    ("stand (x2)", load(f"stand_{STAND_TILT}_usb.stl",
                        tr(x=STAND_X - LEG_W / 2) @ _stand_perm),
     tr(x=EX_STAND_X), (0.93, 0.62, 0.24)),
    ("stand", load(f"stand_{STAND_TILT}_dsi.stl",
                   tr(x=-STAND_X - LEG_W / 2) @ _stand_perm),
     tr(x=-EX_STAND_X), (0.93, 0.62, 0.24)),
]

# ── build the scene ───────────────────────────────────────────────────────
scene = pyrender.Scene(bg_color=[0.97, 0.97, 0.98, 1.0],
                       ambient_light=[0.35, 0.35, 0.35])
placed = []
for label, mesh, expl, colour in PARTS:
    m = mesh.copy()
    m.apply_transform(expl)
    m.fix_normals()
    placed.append((label, m))
    mat = pyrender.MetallicRoughnessMaterial(
        baseColorFactor=[*colour, 1.0], metallicFactor=0.1,
        roughnessFactor=0.6, doubleSided=True)
    scene.add(pyrender.Mesh.from_trimesh(m, material=mat, smooth=False))

for d in ([1, 1, 1], [-1, 0.5, 0.5], [0, -1, 1], [0, 0.5, -1]):
    v = np.array(d, dtype=float)
    v /= np.linalg.norm(v)
    pose = np.eye(4)
    pose[0:3, 2] = -v
    scene.add(pyrender.DirectionalLight(color=[1.0, 1.0, 1.0], intensity=2.5),
              pose=pose)

all_pts = np.vstack([m.vertices for _, m in placed])
centre = (all_pts.min(0) + all_pts.max(0)) / 2
radius = float(np.linalg.norm(all_pts - centre, axis=1).max())

el, az = math.radians(ELEV), math.radians(AZIM)
fwd = np.array([math.cos(el) * math.sin(az), math.cos(el) * math.cos(az),
                math.sin(el)])
# right-handed camera basis: right x up must equal fwd, otherwise the pose is
# a reflection - projection still works but pyrender culls every face.
right = np.cross([0, 0, 1.0], fwd)
right /= np.linalg.norm(right)
up = np.cross(fwd, right)
cam_pose = np.eye(4)
cam_pose[0:3, 0], cam_pose[0:3, 1], cam_pose[0:3, 2] = right, up, fwd
YFOV = math.radians(32)
cam_pose[0:3, 3] = centre + fwd * (radius / math.sin(YFOV / 2) * ZOOM)
scene.add(pyrender.PerspectiveCamera(yfov=YFOV, aspectRatio=W / H),
          pose=cam_pose)

renderer = pyrender.OffscreenRenderer(W, H)
colour_buf, depth_buf = renderer.render(scene)
renderer.delete()
img = Image.fromarray(colour_buf).convert("RGB")
draw = ImageDraw.Draw(img)

# ── 3D -> pixel projection (matches the camera above) ─────────────────────
view = np.linalg.inv(cam_pose)
f = 1.0 / math.tan(YFOV / 2)


def project(p):
    """Project a world point to (pixel_x, pixel_y, depth_from_camera)."""
    v = view @ np.array([p[0], p[1], p[2], 1.0])
    if v[2] >= -1e-6:
        return None
    return ((f / (W / H) * v[0] / -v[2] + 1) / 2 * W,
            (1 - f * v[1] / -v[2]) / 2 * H,
            -v[2])


DEPTH_EPS = 1.0     # mm of bias, so a line lying on a surface still shows


def _visible(q):
    """True if q is in front of whatever the renderer drew at that pixel."""
    ix, iy = int(round(q[0])), int(round(q[1]))
    if not (0 <= ix < W and 0 <= iy < H):
        return False
    z = depth_buf[iy, ix]
    return z <= 0.0 or q[2] < z + DEPTH_EPS


def dashed(p0, p1, dash=13, gap=9, fill=(110, 110, 118), width=2):
    """Dashed 3D line, hidden where it passes behind rendered geometry.

    Sampled along the 3D segment (not the 2D one) so each sample carries its
    own depth, which is tested against the render's depth buffer.
    """
    a, b = np.array(p0, float), np.array(p1, float)
    pa, pb = project(a), project(b)
    if not pa or not pb:
        return
    span = math.dist(pa[:2], pb[:2])
    if span < 1:
        return
    n = max(2, int(span / 3))
    pts = [project(a + (b - a) * (i / n)) for i in range(n + 1)]
    run = 0.0
    for i in range(n):
        A, B = pts[i], pts[i + 1]
        if A is None or B is None:
            continue
        seg = math.dist(A[:2], B[:2])
        if run % (dash + gap) < dash and _visible(A) and _visible(B):
            draw.line([A[0], A[1], B[0], B[1]], fill=fill, width=width)
        run += seg


def font(sz):
    for n in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(n, sz)
        except OSError:
            continue
    return ImageFont.load_default()


F_LBL, F_TTL, F_SML = font(30), font(46), font(26)

# ── fastener centre-lines ─────────────────────────────────────────────────
for x, y in CASE_SCREWS:
    dashed((x, y, EX_DISPLAY - 6), (x, y, EX_BOTTOM + 8))
for x, y in EXTENDERS:
    dashed((x, y, EX_DISPLAY - 6), (x, y, EX_TOP + LID_Z_OUTER + 4))
# the stands share the case screws, so their fastener path runs sideways from
# the exploded stand back onto the same four holes
for x, y in CASE_SCREWS:
    sgn = 1 if x > 0 else -1
    dashed((x, y, 2.5), (x + sgn * EX_STAND_X, y, 2.5))

# ── callouts ──────────────────────────────────────────────────────────────
# (number, text, 3D anchor, column). Label heights are NOT set here - each
# column's slots are handed out in order of the anchors' projected height, so
# leaders within a column can never cross whatever the view angle.
CALLOUTS = [
    ("1", "case_top  -  4x M2.5x6 into the standoffs",
     (30, 24, EX_TOP + LID_Z_OUTER), "r"),
    ("2", "40mm fan (optional)  -  M3 outside",
     (-16, -16, EX_TOP + LID_Z_OUTER), "r"),
    ("3", f"{pm.short_label(PI_MODEL)}  -  held by the standoffs",
     (PI_X0 + PI_W / 2, PI_Y0 + PI_H / 2, PI_Z0 + EX_PI + 2), "r"),
    ("4", "case_bottom  -  lid seats on this wall",
     (-46, -29.5, 9.0), "l"),
    ("6", "M2.5 case screws  ->  display bosses",
     (51.85, -25.5, EX_SHELL + 2), "r"),
    ("7", "M2.5 6+6 extenders + 20mm standoffs",
     (-37.7, 24.5, EX_SHELL + 2), "r"),
    # on the STRUT, which at this height spans case Y -41.9..-32.3; the strap
    # itself is only 3mm thick, so a leader there would be hard to see
    ("5", "stand x2  -  uses the case screws",
     (-STAND_X - EX_STAND_X, -37.0, 27.5), "l"),
    ("8", "shell  -  display drops in front",
     (-64, 20, EX_SHELL - 8), "l"),
    ("9", "Touch Display 2, 5 inch",
     (-64, 20, EX_DISPLAY - 6), "l"),
]

SLOTS = {"r": [210, 292, 610, 1035, 1117], "l": [400, 620, 1080, 1290]}

ordered = []
for col, slots in SLOTS.items():
    items = [c for c in CALLOUTS if c[3] == col]
    items.sort(key=lambda c: (project(c[2]) or (0, 1e9))[1])
    ordered += [(c[0], c[1], c[2], col, y) for c, y in zip(items, sorted(slots))]

R = 23
for num, text, anchor, col, ly in ordered:
    p = project(anchor)
    if not p:
        continue
    bb = draw.textbbox((0, 0), text, font=F_LBL)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    if col == "r":
        cx = COL_R
        text_x = cx + R + 16
    else:
        cx = COL_L
        text_x = cx - R - 16 - tw
    # leader: anchor -> a short horizontal run into the disc
    elbow_x = cx + (-(R + 60) if col == "r" else (R + 60))
    draw.line([p[0], p[1], elbow_x, ly], fill=(70, 70, 78), width=2)
    draw.line([elbow_x, ly, cx + (-R if col == "r" else R), ly],
              fill=(70, 70, 78), width=2)
    draw.ellipse([cx - R, ly - R, cx + R, ly + R], fill=(34, 34, 40))
    nb = draw.textbbox((0, 0), num, font=F_SML)
    draw.text((cx - (nb[2] - nb[0]) / 2 - nb[0],
               ly - (nb[3] - nb[1]) / 2 - nb[1]), num,
              font=F_SML, fill=(255, 255, 255))
    draw.text((text_x, ly - th / 2 - bb[1]), text, font=F_LBL,
              fill=(26, 26, 32))

draw.text((46, 38), "Touch Display 2 (5\") case  -  assembly", font=F_TTL,
          fill=(20, 20, 26))
draw.text((48, 96),
          "Exploded view generated from the part STLs.  "
          "Dashed lines are fastener paths.",
          font=F_SML, fill=(96, 96, 104))
draw.text((48, H - 88),
          "Remix of RonnyS 'Raspberry Pi Touch Display 2 Case' "
          "(printables.com/model/1377047), CC BY.",
          font=F_SML, fill=(96, 96, 104))
draw.text((48, H - 52),
          "Raspberry Pi board models by Pyro_Industries "
          "(printables.com/model/727545 and /727155), CC0.",
          font=F_SML, fill=(96, 96, 104))

out = f"assembly_{PI_MODEL}.png"
img.save(out)
print(f"assembly_diagram v{VERSION} [{PI_MODEL}]: wrote {out} ({W}x{H})")
