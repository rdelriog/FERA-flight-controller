"""FERA Port geometry — single source of truth (see docs/port-spec.md).

Port frame: the mating plane is X = 0 (the hub's outer face). The plug engages
toward -X; the module (tube) extends toward +X. Z is up, the key corner is at
+Y/+Z, the latch pin drops in from +Z.
"""
from build123d import Box, Cylinder, Plane, Polygon, Pos, Rot, extrude, Align

# --- Structural tube -------------------------------------------------------
TUBE_OD = 16.0
TUBE_ID = 14.0
TUBE_BORE_CLEAR = 0.2      # diametral clearance of printed bores on the tube

# --- Plug / socket section -------------------------------------------------
PLUG_SQ = 24.0             # across flats of the square section
CORNER_CHAMFER = 3.0
KEY_CHAMFER = 6.0          # the +Y/+Z corner: makes insertion one-way
ENGAGE = 30.0              # engagement length
FIT_CLEAR = 0.15           # per side, tune per printer
SOCKET_OVERTRAVEL = 0.5    # extra socket depth so the flange always seats

# --- Plug external features ------------------------------------------------
FLANGE_SQ = 30.0
FLANGE_T = 4.0
COLLAR_OD = 24.0
COLLAR_L = 12.0
TUBE_PIN_D = 3.2           # M3 cross pin through collar + tube
END_WALL = 3.0             # plug wall behind the tube end (carries the ID PCB)
WIRE_HOLE_D = 10.0

# --- Latch -----------------------------------------------------------------
LATCH_PIN_D = 4.0
LATCH_PIN_CLEAR = 0.2
LATCH_X = -ENGAGE / 2      # pin axis position along the engagement
LATCH_DEPTH = 6.0          # how far the pin enters the plug from its top flat

# --- Connector window in the socket back wall ------------------------------
CONN_WINDOW_W = 20.0
CONN_WINDOW_H = 12.0

# --- Socket housing (the block of hub material around a socket) ------------
SOCKET_WALL = 4.0
SOCKET_BLOCK_SQ = PLUG_SQ + 2 * SOCKET_WALL          # 32
SOCKET_BLOCK_L = ENGAGE + SOCKET_OVERTRAVEL + 5.5    # 36


def _section(offset: float = 0.0):
    """Keyed square section in the port's YZ plane, grown by `offset` per side."""
    h = PLUG_SQ / 2 + offset
    c, k = CORNER_CHAMFER, KEY_CHAMFER
    pts = [
        (h - k, h), (-h + c, h), (-h, h - c), (-h, -h + c),
        (-h + c, -h), (h - c, -h), (h, -h + c), (h, h - k),
    ]
    return Plane.YZ * Polygon(*pts, align=None)


def _along_x(radius: float, length: float, x0: float = 0.0):
    """Cylinder along +X starting at x0."""
    cyl = Cylinder(radius, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return Pos(x0, 0, 0) * Rot(0, 90, 0) * cyl


def socket_cut():
    """Negative volume to subtract from the hub for one port (port frame)."""
    depth = ENGAGE + SOCKET_OVERTRAVEL
    cut = Pos(-depth, 0, 0) * extrude(_section(FIT_CLEAR), depth)
    # latch pin bore, from the plug centreline up through the housing
    r = (LATCH_PIN_D + LATCH_PIN_CLEAR) / 2
    cut += Pos(LATCH_X, 0, 0) * Cylinder(
        r, 60, align=(Align.CENTER, Align.CENTER, Align.MIN)
    ).move(Pos(0, 0, PLUG_SQ / 2 - LATCH_DEPTH))
    # connector / wiring window through the back wall
    cut += Pos(-depth - 10, 0, 0) * Box(
        20, CONN_WINDOW_W, CONN_WINDOW_H,
        align=(Align.CENTER, Align.CENTER, Align.CENTER),
    )
    return cut


def plug(with_tube_bore: bool = True):
    """Module-side plug. Bond and cross-pin it to the 16 mm tube."""
    body = Pos(-ENGAGE, 0, 0) * extrude(_section(0), ENGAGE)
    body += Pos(FLANGE_T / 2, 0, 0) * Box(FLANGE_T, FLANGE_SQ, FLANGE_SQ)
    if with_tube_bore:
        body += _along_x(COLLAR_OD / 2, COLLAR_L, FLANGE_T)
        bore_r = (TUBE_OD + TUBE_BORE_CLEAR) / 2
        x_start = -ENGAGE + END_WALL
        body -= _along_x(bore_r, FLANGE_T + COLLAR_L - x_start + 1, x_start)
        body -= _along_x(WIRE_HOLE_D / 2, END_WALL + 2, -ENGAGE - 1)
        # cross pin through collar and tube (axis along Y)
        pin = Cylinder(TUBE_PIN_D / 2, COLLAR_OD + 2)
        body -= Pos(FLANGE_T + COLLAR_L / 2, 0, 0) * Rot(90, 0, 0) * pin
    # latch pin pocket from the top flat
    r = (LATCH_PIN_D + LATCH_PIN_CLEAR) / 2
    pocket = Cylinder(r, LATCH_DEPTH + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body -= Pos(LATCH_X, 0, PLUG_SQ / 2 - LATCH_DEPTH) * pocket
    return body


def socket_block():
    """Solid housing for one socket, before the socket is cut (port frame)."""
    return Pos(-SOCKET_BLOCK_L / 2, 0, 0) * Box(
        SOCKET_BLOCK_L, SOCKET_BLOCK_SQ, SOCKET_BLOCK_SQ
    )


def coupon():
    """Stand-alone socket for fit and load testing (port-spec section 7)."""
    return socket_block() - socket_cut()
