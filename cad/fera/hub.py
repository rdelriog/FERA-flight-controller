"""FERA hub v0 — octagonal central unit with four identical ports.

Hub frame: X forward (FRONT port), Z up, origin at the centre of the floor's
underside. Port order matches docs/port-spec.md: FRONT, RIGHT, BACK, LEFT.
"""
import math

from build123d import Align, Box, Cylinder, Polygon, Pos, Rot, extrude

from . import latch, port

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
LATCH_Z_LID = HEIGHT - PORT_Z               # lid underside in the port frame


# --- Battery ---------------------------------------------------------------
# The pack rides on top of the lid, held by two hook-and-loop straps. It lies along the
# 45 degree diagonal: there it covers none of the four latch towers and none of the
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
        body += port_location(name) * latch.base_boss(LATCH_Z_LID)     # collar stop
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
    plate = Pos(0, 0, HEIGHT) * plate
    # latch towers: spring, collar and hall sensor for each port's pin
    for name in PORT_ANGLES:
        plate += port_location(name) * latch.tower(LATCH_Z_LID, LATCH_Z_LID + LID_T)
    for name in PORT_ANGLES:
        plate -= port_location(name) * latch.tower_cut(LATCH_Z_LID, LATCH_Z_LID + LID_T)
    return plate


# --- Battery cover -----------------------------------------------------------
# Optional shell over the pack. It bolts down with the two lid screws that lie across the
# pack (longer screws: M3 x 12), stays on the vehicle, and is open at the front: the pack
# slides in and one strap across the opening holds it. Nothing on the lid or the base changes.
COVER_WALL = 2.0
COVER_ROOF = 1.6
COVER_INNER_H = BATTERY_MAX[2] + 2.0           # room for a strip of foam under the roof
COVER_INNER_W = 2 * (LOOP_Y + LOOP_BAR[1] / 2 + 1.0)       # walls stand outside the strap loops
COVER_REAR = -(BATTERY_MAX[0] / 2)             # inner face of the closed end
COVER_FRONT = 59.0                             # walls end here, short of the lid edge
COVER_PACK_L = 108.0                           # longest pack that still leaves room for the strap
COVER_TAB_T = 3.0
COVER_SLOTS = (48.0, 55.0)                     # strap slots near the open end (along the pack)


def _cover_local():
    """The cover in the pack frame: X along the pack (open end at +X), Y across, Z = 0 on the lid."""
    half_w = COVER_INNER_W / 2
    outer_w = COVER_INNER_W + 2 * COVER_WALL
    x0, x1 = COVER_REAR - COVER_WALL, COVER_FRONT
    height = COVER_INNER_H + COVER_ROOF
    body = Pos((x0 + x1) / 2, 0, height / 2) * Box(x1 - x0, outer_w, height)
    body -= Pos((COVER_REAR + x1 + 1) / 2, 0, COVER_INNER_H / 2 - 0.5) * Box(
        x1 + 1 - COVER_REAR, COVER_INNER_W, COVER_INNER_H + 1)
    # ribs that centre the pack; they start above the strap loops on the lid
    rib_z0 = LID_LOOP_TOP + 2.5
    rib_reach = half_w - (BATTERY_MAX[1] / 2 + 0.75)
    for x in (-45.0, -5.0, 30.0):
        for s in (-1, 1):
            body += Pos(x, s * (half_w - rib_reach / 2), (rib_z0 + COVER_INNER_H) / 2) * Box(
                2.4, rib_reach, COVER_INNER_H - rib_z0)
    # mounting tabs out to the two lid screws across the pack, with 45 degree gussets so the
    # part prints upside down without support
    screw_r = BOSS_R
    for s in (-1, 1):
        root, tip = half_w + COVER_WALL - 0.5, screw_r + 4.0
        outline = [(-16, s * root), (-6, s * root), (6, s * (screw_r - 3.5)), (6, s * tip),
                   (-6, s * tip), (-6, s * (screw_r - 3.5))]
        tab = extrude(Polygon(*outline, align=None), height - 8, dir=(0, 0, 1))
        tab -= Pos(0, s * (tip + 70.71), COVER_TAB_T + 70.71) * Rot(-45 * s, 0, 0) * Box(200, 200, 200)
        tab -= Pos(0, s * screw_r, COVER_TAB_T) * Cylinder(
            3.3, height, align=(Align.CENTER, Align.CENTER, Align.MIN))                 # screw head
        tab -= Pos(0, s * screw_r, 0) * Cylinder(LID_SCREW_D / 2, 3 * COVER_TAB_T)
        body += tab
    # strap slots in both walls near the open end
    for x in COVER_SLOTS:
        body -= Pos(x, 0, 21) * Box(3.5, outer_w + 2, STRAP_W + 2)
    # the closed end clears the lid screw underneath it
    body -= Pos(x0, 0, 2.2) * Box(2 * COVER_WALL + 2, 9, 4.6)
    return body


LID_LOOP_TOP = LOOP_CLEAR + LOOP_BAR[2]        # height of the strap loops above the lid


def battery_cover():
    """Battery cover in the hub frame, sitting on the lid."""
    place = Pos(0, 0, HEIGHT + LID_T) * Rot(0, 0, BATTERY_ANGLE)
    cover = place * _cover_local()
    x, y = lead_exit_xy()                       # keep the lead slot open
    w, h = LEAD_EXIT
    return cover - Pos(x, y, HEIGHT + LID_T + 30) * Box(w + 3, h + 3, 80)


def battery_in_cover(length=COVER_PACK_L):
    """Reference solid of the longest pack the cover takes, pushed against the closed end."""
    return Pos(0, 0, HEIGHT + LID_T) * Rot(0, 0, BATTERY_ANGLE) * Pos(COVER_REAR + length / 2, 0, 0) * Box(
        length, BATTERY_MAX[1], BATTERY_MAX[2], align=(Align.CENTER, Align.CENTER, Align.MIN))
