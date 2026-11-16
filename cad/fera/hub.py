"""FERA hub v0 — octagonal central unit with four identical ports.

Hub frame: X forward (FRONT port), Z up, origin at the centre of the floor's
underside. Port order matches docs/port-spec.md: FRONT, RIGHT, BACK, LEFT.
"""
import math

from build123d import Align, Box, Cylinder, Polygon, Pos, Rot, extrude

from . import port

ACROSS_FLATS = 130.0
HEIGHT = 34.0
WALL = 3.0
FLOOR = 2.4
LID_T = 3.0

PORT_Z = port.SOCKET_BLOCK_SQ / 2          # plug centreline height
# CAD is Z-up, PX4 is Z-down, so PX4 RIGHT (+Y) is CAD -Y.
PORT_ANGLES = {"FRONT": 0, "RIGHT": -90, "BACK": 180, "LEFT": 90}

# FERA Core board (hardware/fera-core). Board frame is KiCad's: x right, y down,
# FRONT port at -y. Hub frame: X forward, Y left. So hub (X, Y) = (-by, -bx).
BOARD_T = 1.6
BOARD_Z = 11.4                              # underside of the PCB above the hub datum
FC_POST_D = 6.5
FC_HOLE_D = 2.6                             # M3 self-tap / insert pilot
USB_SLOT = (11.0, 5.0)                      # opening for the USB-C plug (width, height)
USB_Z = BOARD_Z + BOARD_T + 1.6             # connector centreline


def board_to_hub(bx, by):
    return (-by, -bx)


def _design():
    """The PCB's design data (outline, mounting holes, USB position)."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[2] / "hardware" / "fera-core" / "gen" / "design.py"
    spec = importlib.util.spec_from_file_location("fera_core_design", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def board_posts():
    return [board_to_hub(x, y) for x, y in _design().MOUNT_HOLES]


def board_solid():
    """The bare PCB as a solid, in the hub frame (for fit checks)."""
    pts = [board_to_hub(x, y) for x, y in _design().OUTLINE]
    return Pos(0, 0, BOARD_Z) * extrude(Polygon(*pts, align=None), BOARD_T, dir=(0, 0, 1))

BOSS_D = 8.0
BOSS_R = ACROSS_FLATS / 2 - WALL - BOSS_D / 2 + 0.5
INSERT_D = 4.0                              # M3 heat-set insert pilot
INSERT_DEPTH = 8.0
LID_SCREW_D = 3.4
LATCH_ACCESS_D = 6.0


# --- Battery ---------------------------------------------------------------
# The pack rides on top of the lid, held by two hook-and-loop straps. It lies along the
# 45 degree diagonal: there it covers none of the four latch access holes and none of the
# lid screws, whatever its length up to BATTERY_MAX.
BATTERY_SIZES = {                              # length, width, height in mm (typical 4S packs)
    "4S 1500 mAh": (78.0, 38.0, 37.0),
    "4S 2200 mAh": (106.0, 35.0, 34.0),
}
BATTERY_MAX = (110.0, 40.0, 40.0)              # the envelope the lid is laid out for
BATTERY_ANGLE = 45.0
STRAP_W = 20.0
STRAP_X = 20.0                                 # strap positions along the pack, either side of centre
LOOP_CLEAR = 4.0                               # opening under a strap loop
LOOP_BAR = (STRAP_W + 4.0, 4.0, 2.5)           # bar length, width, thickness
LOOP_Y = BATTERY_MAX[1] / 2 + 3.0 + LOOP_BAR[1] / 2
LEAD_EXIT = (16.0, 9.0)                        # slot for the two battery leads (12-14 AWG)


def battery_pads():
    """Hub XY of the board's BAT+ and BAT- solder pads."""
    refs = {p["ref"]: p for p in _design().PARTS}
    return [board_to_hub(refs[r]["x"], refs[r]["y"]) for r in ("J9", "J10")]


def lead_exit_xy():
    """The lead slot sits above the two battery pads, moved sideways just enough to clear
    the socket block next to them (build.py checks that nothing is underneath)."""
    (x1, y1), (x2, y2) = battery_pads()
    clear_of_block = -(port.SOCKET_BLOCK_SQ / 2 + LEAD_EXIT[0] / 2 + 1.5)
    return (min((x1 + x2) / 2, clear_of_block), (y1 + y2) / 2)


def battery(size=BATTERY_MAX):
    """Reference solid of a pack sitting on the lid (not printed)."""
    return Pos(0, 0, HEIGHT + LID_T) * Rot(0, 0, BATTERY_ANGLE) * Box(
        *size, align=(Align.CENTER, Align.CENTER, Align.MIN))


def _octagon(across_flats: float):
    r = across_flats / 2 / math.cos(math.pi / 8)
    pts = [
        (r * math.cos(math.radians(22.5 + 45 * i)),
         r * math.sin(math.radians(22.5 + 45 * i)))
        for i in range(8)
    ]
    return Polygon(*pts, align=None)


def port_location(name: str):
    """Transform from the port frame to the hub frame."""
    return Rot(0, 0, PORT_ANGLES[name]) * Pos(ACROSS_FLATS / 2, 0, PORT_Z)


def _diagonals():
    for a in (45, 135, 225, 315):
        yield (BOSS_R * math.cos(math.radians(a)), BOSS_R * math.sin(math.radians(a)))


def base():
    shell = extrude(_octagon(ACROSS_FLATS), HEIGHT)
    shell -= Pos(0, 0, FLOOR) * extrude(_octagon(ACROSS_FLATS - 2 * WALL), HEIGHT)
    body = shell
    for name in PORT_ANGLES:
        body += port_location(name) * port.socket_block()
    # standoffs for the FERA Core board
    for x, y in board_posts():
        body += Pos(x, y, 0) * Cylinder(FC_POST_D / 2, BOARD_Z,
                                        align=(Align.CENTER, Align.CENTER, Align.MIN))
    # lid bosses on the diagonal walls
    for x, y in _diagonals():
        body += Pos(x, y, 0) * Cylinder(
            BOSS_D / 2, HEIGHT, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # trim anything that pokes outside the octagon
    body &= extrude(_octagon(ACROSS_FLATS), HEIGHT)

    for name in PORT_ANGLES:
        body -= port_location(name) * port.socket_cut()
    for x, y in board_posts():
        body -= Pos(x, y, FLOOR) * Cylinder(FC_HOLE_D / 2, BOARD_Z,
                                            align=(Align.CENTER, Align.CENTER, Align.MIN))
    # USB-C opening through the wall in line with the board's USB tongue
    d = _design()
    ux, uy = board_to_hub(d.TONGUE_X, -(d.TONGUE_Y + d.LOBE_IN) / 2 + 0.5)
    body -= Pos(ux, uy - 5, USB_Z) * Box(USB_SLOT[0], 12, USB_SLOT[1])
    for x, y in _diagonals():
        body -= Pos(x, y, HEIGHT - INSERT_DEPTH) * Cylinder(
            INSERT_D / 2, INSERT_DEPTH + 1,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
    return body


def lid():
    plate = extrude(_octagon(ACROSS_FLATS), LID_T)
    for x, y in _diagonals():
        plate -= Pos(x, y, 0) * Cylinder(LID_SCREW_D / 2, 3 * LID_T)
    # latch pin access above each port
    for name, ang in PORT_ANGLES.items():
        plate -= Rot(0, 0, ang) * Pos(ACROSS_FLATS / 2 + port.LATCH_X, 0, 0) * Cylinder(
            LATCH_ACCESS_D / 2, 3 * LID_T)
    # Battery: four strap loops beside the pack (two straps). Each loop is a bar on two
    # posts, so the strap never enters the hub and the bar prints as a bridge.
    length, width, thick = LOOP_BAR
    post = (length - STRAP_W - 1.0) / 2 + 0.5
    for sx in (-1, 1):
        for sy in (-1, 1):
            loop = Pos(0, 0, LID_T + LOOP_CLEAR + thick / 2) * Box(length, width, thick)
            for end in (-1, 1):
                loop += Pos(end * (length - post) / 2, 0, LID_T + LOOP_CLEAR / 2) * Box(
                    post, width, LOOP_CLEAR + 0.2)
            plate += Rot(0, 0, BATTERY_ANGLE) * Pos(sx * STRAP_X, sy * LOOP_Y, 0) * loop
    # slot where the battery leads come up from the board's solder pads
    x, y = lead_exit_xy()
    w, h = LEAD_EXIT
    plate -= Pos(x, y, 0) * (Box(w - h, h, 3 * LID_T)
                             + Pos((w - h) / 2, 0, 0) * Cylinder(h / 2, 3 * LID_T)
                             + Pos(-(w - h) / 2, 0, 0) * Cylinder(h / 2, 3 * LID_T))
    return Pos(0, 0, HEIGHT) * plate
