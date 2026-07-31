"""Measured connector tables for the Raspberry Pi 4B and Pi 5.

Shared by case_bottom.py and case_top.py so that the port gap in the wall and
the aperture in the lid - which together form ONE opening - are derived from a
single set of numbers. Getting those two halves out of step is what buried the
USB-C socket on the first print.

All values are ASSEMBLY coordinates (the frame case_bottom.py works in): the
board sits at x -41.2..43.8, y +-28, PCB 6.0..7.4, and +Z is rearward.

MEASURED, not derived. Taken from the CC0 reference meshes by Pyro_Industries
in the gitignored reference/ folder (Pi 4 = printables.com/model/727545,
Pi 5 = printables.com/model/727155) by clustering mesh vertices that pass the
board edge. Cross-checked against the official Pi 4 drawing: the micro-HDMI
centres come out at -15.18 and -1.47 against nominal -15.2 and -1.7, and the
USB-C at -30.00 against nominal -30.0.

Clustering by distance alone gets this wrong twice, in opposite directions, so
both corrections are baked into the numbers below:
  - One housing can be modelled as two shells further apart than two adjacent
    housings are (Pi 4: 3.18mm inside the USB2 shell against 3.30mm between the
    USB2 and USB3 housings). The +X bodies were separated by matching height
    and protrusion instead.
  - A connector with a flat middle carries vertices only at its rounded ends,
    so the USB-C splits into two blobs 7mm apart and reads as two ports. A
    stray vertex row at z ~ 8.0 spanning the whole board then bridges the real
    gaps. The -Y ports were taken above z 8.4 and re-merged by inspection.
"""

# --- shared board geometry (identical on both models) ---
BOARD_X0 = -41.2
BOARD_W = 85.0
BOARD_HY = 28.0
PCB_Z0, PCB_Z1 = 6.0, 7.4

# Each +X entry: (name, y0, y1, z0, z1, reach_x, underside_z_at_wall)
#   underside_z_at_wall is the lowest point of the body within the wall band
#   (x 44.0..46.5) - it, not z0, is what limits how high a port sill may rise.
# Each -Y entry: (name, x0, x1, z0, z1, reach_y)
PI_MODELS = {
    "pi4": {
        "label": "Raspberry Pi 4 Model B",
        "short": "Raspberry Pi 4",
        "max_z": 24.20,          # tallest point anywhere on the board
        "fan_zone_z": 16.30,     # tallest point under the lid fan (x,y +-20):
                                 # the GPIO header on both boards
        "cooler_fan_zone_z": None,
        "side": [
            ("usb2", -26.45, -11.55, 7.85, 23.72, 47.79, 7.85),
            ("usb3", -8.25, 6.25, 8.58, 24.20, 47.40, 9.28),
            ("eth", 9.80, 25.70, 8.00, 21.50, 47.05, 8.00),
        ],
        "bottom": [
            ("usb_c", -34.47, -25.53, 7.35, 11.16, -29.50),
            ("hdmi0", -18.45, -11.95, 8.00, 10.90, -29.80),
            ("hdmi1", -4.95, 1.55, 8.00, 10.90, -29.80),
            ("csi", 3.80, 6.80, 8.00, 13.48, -28.00),
            ("audio", 9.30, 16.30, 8.00, 14.00, -30.40),
        ],
    },
    "pi5": {
        "label": "Raspberry Pi 5",
        "short": "Raspberry Pi 5",
        "max_z": 25.14,          # the active cooler adds nothing: it sits below
                                 # the USB cans, which still set the maximum
        "fan_zone_z": 16.30,
        # ...but it is 20.90 tall where the lid's optional 40mm fan hangs
        # (underside 17.40), so the cooler and that fan cannot both be fitted.
        "cooler_fan_zone_z": 20.90,
        "side": [
            ("eth", -25.75, -9.85, 8.00, 21.50, 46.90, 8.00),
            ("usb3", -5.70, 7.90, 9.18, 25.14, 47.48, 9.18),
            ("usb2", 11.55, 26.45, 8.00, 23.82, 47.69, 8.00),
        ],
        "bottom": [
            ("usb_c", -34.47, -25.53, 8.00, 11.16, -29.19),
            ("hdmi0", -18.65, -12.15, 8.00, 10.90, -29.00),
            ("hdmi1", -5.25, 1.25, 8.00, 10.90, -29.00),
            # The Pi 5's two 22-pin MIPI CAM/DISP connectors are on THIS edge,
            # not on the -X short edge where the Pi 4 keeps its DSI socket.
            # The display ribbon route differs completely between the models.
            ("mipi0", 6.70, 9.00, 8.85, 11.90, -27.54),
            ("mipi1", 12.90, 15.20, 8.85, 11.90, -27.54),
        ],
    },
}


def side_ports(model):
    return PI_MODELS[model]["side"]


def bottom_ports(model):
    return PI_MODELS[model]["bottom"]


def side_span(model):
    """(y0, y1) covering every +X connector."""
    p = side_ports(model)
    return min(e[1] for e in p), max(e[2] for e in p)


def bottom_external(model):
    """The -Y ports that actually need an opening.

    A port needs one only if it passes the board edge, which is what a plug has
    to reach through. The Pi 4's CSI connector and the Pi 5's two MIPI
    connectors sit flush with the edge and face upward, so wall in front of them
    blocks nothing.
    """
    return [e for e in bottom_ports(model) if e[5] < -BOARD_HY - 0.05]


def bottom_span(model):
    """(x0, x1) covering every -Y port that needs an opening."""
    p = bottom_external(model)
    return min(e[1] for e in p), max(e[2] for e in p)


def bottom_sill_z(model):
    """Highest a sill may rise under the -Y ports.

    Unlike the +X edge, these connectors stop at or just inside the wall's inner
    face, so a PLUG passes through the opening rather than the socket poking out
    of it. That is why this edge gets a sill but no dividers: the overmoulds set
    the spacing, and two micro-HDMI plugs are already tight on a bare Pi 4 with
    their sockets 13.5mm apart. The sill itself is safe - it sits below every
    socket, and the reference's equivalent wall stops higher still (z 8.5 over a
    3.0 plate) with real cables in use.
    """
    return min(e[3] for e in bottom_external(model))


def side_gaps(model):
    """(y0, y1) of each clear space BETWEEN neighbouring +X connectors."""
    p = sorted(side_ports(model), key=lambda e: e[1])
    return [(p[i][2], p[i + 1][1]) for i in range(len(p) - 1)]


def side_sill_z(model):
    """Highest a port sill may rise under the +X connectors."""
    return min(e[6] for e in side_ports(model))


def max_z(model):
    return PI_MODELS[model]["max_z"]


def fan_zone_z(model):
    """Tallest point under the lid's optional 40mm fan (x, y within +-20)."""
    return PI_MODELS[model]["fan_zone_z"]


def cooler_fan_zone_z(model):
    """Same, with the official active cooler fitted; None if there isn't one."""
    return PI_MODELS[model]["cooler_fan_zone_z"]


def label(model):
    return PI_MODELS[model]["label"]


def short_label(model):
    """For places where the full name does not fit, such as diagram callouts."""
    return PI_MODELS[model]["short"]
