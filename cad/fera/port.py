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
FIT_CLEAR = 0.30           # per side, tune per printer (0.15 too tight; gauge: 0.30 chosen)
ROOF_CLEAR = 0.20          # extra on the socket's top flat: it prints as a bridge and sags
GAUGE_CLEAR = (0.20, 0.30, 0.40)   # the three sockets of the fit gauge
GAUGE_DEPTH = 10.0
GAUGE_WALL = 3.0
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
LATCH_X = -8.0             # pin axis position along the engagement (outboard: clears the battery)
LATCH_DEPTH = 3.5          # how far the pin enters the plug: stops above the 16 mm tube bore
LATCH_FLAT = 2.5           # flat between the top of the ramp and the pocket
LATCH_RAMP_W = 4.6         # slot the pin rides in on the way in

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


def _socket_opening(depth: float, clear: float = None, roof: float = None):
    """The keyed opening, `clear` larger per side than the plug and `roof` more on top."""
    clear = FIT_CLEAR if clear is None else clear
    roof = ROOF_CLEAR if roof is None else roof
    opening = Pos(-depth, 0, 0) * extrude(_section(clear), depth)
    return opening + Pos(0, 0, roof) * opening


def socket_cut():
    """Negative volume to subtract from the hub for one port (port frame)."""
    depth = ENGAGE + SOCKET_OVERTRAVEL
    cut = _socket_opening(depth)
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
    body -= latch_cut()
    return body


def latch_cut():
    """Pocket for the latch pin in the plug's top flat, and the ramp that lifts the pin on
    the way in (so the latch snaps shut by itself at full depth)."""
    r = (LATCH_PIN_D + LATCH_PIN_CLEAR) / 2
    top = PLUG_SQ / 2
    cut = Pos(LATCH_X, 0, top - LATCH_DEPTH) * Cylinder(
        r, LATCH_DEPTH + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    x_ramp = LATCH_X - r - LATCH_FLAT
    wedge = Polygon((-ENGAGE - 1, top - LATCH_DEPTH), (x_ramp, top), (x_ramp, top + 1),
                    (-ENGAGE - 1, top + 1), align=None)
    cut += extrude(Plane.XZ * wedge, LATCH_RAMP_W / 2, both=True)
    return cut


def socket_block():
    """Solid housing for one socket, before the socket is cut (port frame)."""
    return Pos(-SOCKET_BLOCK_L / 2, 0, 0) * Box(
        SOCKET_BLOCK_L, SOCKET_BLOCK_SQ, SOCKET_BLOCK_SQ
    )


def coupon():
    """Stand-alone socket for fit and load testing (port-spec section 7)."""
    return socket_block() - socket_cut()


def gauge_pitch():
    return PLUG_SQ + 2 * max(GAUGE_CLEAR) + GAUGE_WALL


def fit_gauge():
    """Three short sockets side by side, one per GAUGE_CLEAR value, to find FIT_CLEAR for a
    printer in one short print. Tightest on the left with one notch on top, then two, three.
    Printed the same way up as a real socket (roof bridged); walls are thinner to save time."""
    half = PLUG_SQ / 2 + max(GAUGE_CLEAR)
    bottom, top = -(half + 2.0), half + ROOF_CLEAR + GAUGE_WALL
    width = (len(GAUGE_CLEAR) - 1) * gauge_pitch() + 2 * (half + GAUGE_WALL)
    body = Pos(-GAUGE_DEPTH / 2, 0, (top + bottom) / 2) * Box(GAUGE_DEPTH, width, top - bottom)
    for i, clear in enumerate(GAUGE_CLEAR):
        y = (i - (len(GAUGE_CLEAR) - 1) / 2) * gauge_pitch()
        body -= Pos(1, y, 0) * _socket_opening(GAUGE_DEPTH + 2, clear)
        for n in range(i + 1):                     # i + 1 notches across the top face
            body -= Pos(-GAUGE_DEPTH / 2, y + (n - i / 2) * 3.0, top) * Box(
                GAUGE_DEPTH + 2, 1.2, 1.2)
    return body
