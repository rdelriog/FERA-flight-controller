"""Starter parts for the plane, rover, crawler and boat modes.

Every part clamps onto the same 16 mm carbon tube that the port plug holds, so a module is
always: port plug + tube + the parts below. First-pass geometry: it passes the checks in
build.py but none of it has been printed or loaded yet.

Local frame of a tube-end part (same as modules.motor_mount): tube axis along X, tube end
at X = 0, the part's sleeve covers X = -SLEEVE_L .. 0, Z is up.

Bought parts the geometry assumes (change the constants to suit what you have):
  plane   2207-class brushless motor (16 x 16 mm M3), 9 g servos, 6 mm rod, 3 mm sheet
  rover   25 mm gear motor (25GA-370 style: 7 mm boss, 2 x M3 on 17 mm, 4 mm D shaft)
  crawler the same gear motor, M4 bolts for the idlers, 1.75 mm filament as hinge pins
  boat    65 mm foam floats (pool noodle), the quad's 2207 motors and 5-inch props in air
"""
import math

from build123d import Align, Box, Cylinder, Plane, Polygon, Pos, Rot, extrude

from . import port
from .modules import MOTOR_PATTERN, MOTOR_SCREW_D, MOTOR_SHAFT_D, SLEEVE_L, SLEEVE_SQ

BORE_R = (port.TUBE_OD + port.TUBE_BORE_CLEAR) / 2
END_WALL = 2.0


def _y_cyl(radius, length):
    """Cylinder along Y, centred on the origin."""
    return Rot(90, 0, 0) * Cylinder(radius, length)


def _sleeve():
    """Square sleeve over the tube end, closed by a thin wall the tube stops against."""
    return (Pos(-SLEEVE_L / 2, 0, 0) * Box(SLEEVE_L, SLEEVE_SQ, SLEEVE_SQ)
            + Pos(END_WALL / 2, 0, 0) * Box(END_WALL, SLEEVE_SQ, SLEEVE_SQ))


def _sleeve_cuts():
    """Tube bore and the M3 cross pin."""
    return (port._along_x(BORE_R, SLEEVE_L + 1, -SLEEVE_L - 1)
            + Pos(-SLEEVE_L / 2, 0, 0) * _y_cyl(port.TUBE_PIN_D / 2, SLEEVE_SQ + 2))


def _motor_pattern(depth):
    """Brushless motor screw holes and shaft clearance, along Z, centred on the origin."""
    cut = Cylinder(MOTOR_SHAFT_D / 2, depth)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cut += Pos(sx * MOTOR_PATTERN / 2, sy * MOTOR_PATTERN / 2, 0) * Cylinder(
                MOTOR_SCREW_D / 2, depth)
    return cut


# =========================================================================== plane
NOSE_STANDOFF = 14.0        # open space behind the firewall for the motor screws
NOSE_PLATE_D = 34.0
NOSE_PLATE_T = 5.0


def nose_motor_mount():
    """Firewall on the tube end, motor axis along the tube (tractor nose on the FRONT port)."""
    x0 = END_WALL
    body = _sleeve()
    for turn in (0, 90):                                   # cross-shaped web: screws go between
        body += Pos(x0 + NOSE_STANDOFF / 2, 0, 0) * Rot(turn, 0, 0) * Box(
            NOSE_STANDOFF, NOSE_PLATE_D - 2, 4)
    body += port._along_x(6, NOSE_STANDOFF, x0)
    body += port._along_x(NOSE_PLATE_D / 2, NOSE_PLATE_T, x0 + NOSE_STANDOFF)
    body -= _sleeve_cuts()
    body -= Pos(x0 + NOSE_STANDOFF + NOSE_PLATE_T / 2, 0, 0) * Rot(0, 90, 0) * _motor_pattern(
        NOSE_PLATE_T + 2)
    return body


NOSE_FACE_X = END_WALL + NOSE_STANDOFF + NOSE_PLATE_T       # motor mounting face

WING_CHORD = 200.0
WING_SPAR_AT = 0.30         # spar (the tube) position, fraction of chord
WING_ROD_AT = 0.72          # 6 mm anti-rotation rod
WING_ROD_D = 6.0
WING_TE_CUT = 0.96          # blunt trailing edge
RIB_T = 5.0
RIB_COLLAR_L = 14.0
RIB_COLLAR_WALL = 3.0
SERVO_W, SERVO_H = 23.5, 12.6          # 9 g servo body opening
SERVO_SCREW_SPAN = 27.8


def _naca4412(x):
    """Camber line and half thickness of a NACA 4412 at chord fraction x."""
    m, p, t = 0.04, 0.4, 0.12
    yt = 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x ** 2 + 0.2843 * x ** 3
                  - 0.1015 * x ** 4)
    if x < p:
        yc, dy = m / p ** 2 * (2 * p * x - x * x), 2 * m / p ** 2 * (p - x)
    else:
        yc, dy = m / (1 - p) ** 2 * (1 - 2 * p + 2 * p * x - x * x), 2 * m / (1 - p) ** 2 * (p - x)
    return yc, yt, math.atan(dy)


def _rib_point(x, z_frac):
    """Chord fraction and height fraction -> local (Y, Z); the spar axis is the origin."""
    return ((WING_SPAR_AT - x) * WING_CHORD, (z_frac - _naca4412(WING_SPAR_AT)[0]) * WING_CHORD)


def rib_half_thickness(x):
    return _naca4412(x)[1] * WING_CHORD


def _rib_profile(n=48):
    upper, lower = [], []
    for i in range(n + 1):
        x = 0.5 * (1 - math.cos(math.pi * i / n)) * WING_TE_CUT
        yc, yt, th = _naca4412(x)
        upper.append(_rib_point(x - yt * math.sin(th), yc + yt * math.cos(th)))
        lower.append(_rib_point(x + yt * math.sin(th), yc - yt * math.cos(th)))
    return Plane.YZ * Polygon(*(upper[::-1] + lower[1:]), align=None)


def wing_rib(servo=False):
    """Wing rib that slides onto the tube (the spar). Leading edge toward +Y, top toward +Z.

    Flip it over for the other wing. A 6 mm rod through the rear hole stops the ribs turning;
    the collar takes an M3 grub screw or glue. servo=True adds a 9 g servo opening.
    """
    body = Pos(RIB_T / 2, 0, 0) * extrude(_rib_profile(), RIB_T / 2, both=True)
    body += port._along_x(BORE_R + RIB_COLLAR_WALL, RIB_COLLAR_L, 0)
    body -= port._along_x(BORE_R, RIB_COLLAR_L + 2, -1)
    y, z = _rib_point(WING_ROD_AT, _naca4412(WING_ROD_AT)[0])
    body -= Pos(0, y, z) * port._along_x((WING_ROD_D + 0.2) / 2, RIB_T + 2, -1)
    y, z = _rib_point(0.50, _naca4412(0.50)[0])
    if servo:
        body -= Pos(RIB_T / 2, y, z) * Box(RIB_T + 2, SERVO_W, SERVO_H)
        for s in (-1, 1):
            body -= Pos(0, y + s * SERVO_SCREW_SPAN / 2, z) * port._along_x(1.0, RIB_T + 2, -1)
    else:
        body -= Pos(0, y, z) * port._along_x(6.0, RIB_T + 2, -1)          # lightening hole
    # grub screw into the collar from above
    body -= Pos(RIB_T + (RIB_COLLAR_L - RIB_T) / 2, 0, BORE_R + RIB_COLLAR_WALL) * Cylinder(1.4, 10)
    return body


TAIL_BLOCK_L = 40.0
TAIL_SHEET_T = 3.0          # stabiliser and fin are flat 3 mm sheet (balsa, foam board, print)


def tail_mount():
    """Block on the end of the tail boom: slots for a flat stabiliser and a flat fin."""
    x1 = END_WALL + TAIL_BLOCK_L
    slot = TAIL_SHEET_T + 0.3
    body = _sleeve() + Pos(END_WALL + TAIL_BLOCK_L / 2, 0, 0) * Box(TAIL_BLOCK_L, SLEEVE_SQ, SLEEVE_SQ)
    body -= _sleeve_cuts()
    x_slot = END_WALL + 4
    length = x1 - x_slot + 1
    body -= Pos(x_slot + length / 2, 0, 0) * Box(length, SLEEVE_SQ + 2, slot)            # stabiliser
    body -= Pos(x_slot + length / 2, 0, SLEEVE_SQ / 4 + 0.5) * Box(length, slot, SLEEVE_SQ / 2 + 1)  # fin
    for x in (x_slot + 8, x1 - 8):                         # M3 bolts clamp the stabiliser
        for s in (-1, 1):
            body -= Pos(x, s * 7, 0) * Cylinder(1.65, SLEEVE_SQ + 2)
    body -= Pos((x_slot + x1) / 2, 0, 7) * _y_cyl(1.65, SLEEVE_SQ + 2)                    # and the fin
    return body


# =========================================================================== rover
GEARMOTOR_D = 25.0
GEARMOTOR_BOSS_D = 7.0
GEARMOTOR_SCREWS = 17.0     # 2 x M3, centre distance
GEARMOTOR_SHAFT_D = 4.0
GEARMOTOR_SHAFT_FLAT = 3.5  # across the D flat
GEARMOTOR_SHAFT_L = 12.0
AXLE_DROP = 26.0            # wheel axis below the tube axis (motor lies under the tube)
PLATE_T = 6.0
WHEEL_D = 80.0
WHEEL_W = 20.0
HUB_R = 9.0
HUB_EXT = 8.0               # hub sticks out toward the motor; the grub screw sits here


def _gearmotor_cut(depth):
    """Boss hole and two screw holes of the gear motor face, along X, centred on the origin."""
    cut = port._along_x((GEARMOTOR_BOSS_D + 0.4) / 2, depth, -depth / 2)
    for s in (-1, 1):
        cut += Pos(0, s * GEARMOTOR_SCREWS / 2, 0) * port._along_x(1.65, depth, -depth / 2)
    return cut


def _d_bore(length):
    """D-shaped shaft bore along Z; the flat faces +Y (where the grub screw comes in)."""
    r = (GEARMOTOR_SHAFT_D + 0.2) / 2
    flat = GEARMOTOR_SHAFT_FLAT + 0.1 - r
    return Cylinder(r, length) & Pos(0, (flat - r) / 2, 0) * Box(2 * r, r + flat, length)


def gearmotor_mount():
    """Drive unit for LEFT/RIGHT ports: the gear motor hangs under the tube, shaft outward."""
    top, bottom = SLEEVE_SQ / 2, -(AXLE_DROP + GEARMOTOR_D / 2 + 3.5)
    body = _sleeve() + Pos(PLATE_T / 2, 0, (top + bottom) / 2) * Box(
        PLATE_T, GEARMOTOR_D + 7, top - bottom)
    body -= _sleeve_cuts()
    body -= Pos(PLATE_T / 2, 0, -AXLE_DROP) * _gearmotor_cut(PLATE_T + 2)
    return body


def wheel():
    """80 mm wheel for the gear motor's D shaft. Axis along Z; the hub extension (-Z) faces
    the motor. Smooth rim: add a wide rubber band or print a TPU tyre."""
    body = Cylinder(WHEEL_D / 2, WHEEL_W, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body -= Pos(0, 0, -1) * Cylinder(WHEEL_D / 2 - 5, WHEEL_W - 3, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body += Pos(0, 0, -HUB_EXT) * Cylinder(HUB_R, WHEEL_W + HUB_EXT, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for k in range(5):                                      # lightening holes in the web
        a = math.radians(72 * k + 36)
        body -= Pos(22 * math.cos(a), 22 * math.sin(a), WHEEL_W - 2) * Cylinder(7, 8)
    body -= _d_bore(2 * (WHEEL_W + HUB_EXT) + 2)
    body -= Pos(0, HUB_R / 2, -HUB_EXT / 2) * _y_cyl(1.4, HUB_R + 2)       # M3 grub screw pilot
    return body


SKID_FOOT_R = 8.0


def skid():
    """Sliding foot for the FRONT/BACK ports of the rover, level with the wheels."""
    foot_z = -(AXLE_DROP + WHEEL_D / 2) + SKID_FOOT_R
    leg_top = -SLEEVE_SQ / 2 + 1
    body = _sleeve() + Pos(-6, 0, (leg_top + foot_z) / 2) * Box(12, SLEEVE_SQ, leg_top - foot_z)
    body += Pos(-6, 0, foot_z) * _y_cyl(SKID_FOOT_R, SLEEVE_SQ)
    return body - _sleeve_cuts()


# =========================================================================== crawler
TRACK_PITCH = 16.0
TRACK_TEETH = 9
TRACK_LINKS = 27            # per side
TRACK_W = 28.0
LINK_T = 5.0
LINK_PIN_D = 2.0            # 1.75 mm filament as the hinge pin
LINK_CENTRE_W = 9.6         # width of the single rear knuckle
LINK_GAP = 0.4
WINDOW_L, WINDOW_W = 6.0, 11.0
SPROCKET_W = 10.0           # body and teeth; the link's window is 1 mm wider
TRACK_PITCH_R = TRACK_PITCH / (2 * math.sin(math.pi / TRACK_TEETH))
TRACK_AXLE_SPACING = (TRACK_LINKS - TRACK_TEETH) * TRACK_PITCH / 2      # 144 mm
TRACK_AXLE_Z = -18.0        # axles below the tube axis
TRACK_OFFSET = PLATE_T + 3 + TRACK_W / 2     # track centre plane, outboard of the plate


def track_link():
    """One track link. X along the track (pins at X = 0 and X = pitch), Y across, Z thickness."""
    p, r, half = TRACK_PITCH, LINK_T / 2, TRACK_W / 2
    inner = LINK_CENTRE_W / 2
    body = Pos(p / 2, 0, 0) * Box(p, TRACK_W, LINK_T)
    reach = 2 * (r + LINK_GAP)
    body -= Box(reach, 2 * (inner + LINK_GAP), LINK_T + 2)                    # room for the knuckle behind
    for s in (-1, 1):                                                         # room for the two ahead
        body -= Pos(p, s * (inner + (half - inner + 1) / 2), 0) * Box(reach, half - inner + 1, LINK_T + 2)
        w = half - inner - LINK_GAP
        body += Pos(0, s * (half - w / 2), 0) * _y_cyl(r, w)
    body += Pos(p, 0, 0) * _y_cyl(r, LINK_CENTRE_W)
    body -= Pos(p / 2, 0, 0) * Box(WINDOW_L, WINDOW_W, LINK_T + 2)            # sprocket tooth window
    for x in (0, p):
        body -= Pos(x, 0, 0) * _y_cyl(LINK_PIN_D / 2, TRACK_W + 2)
    return body


def track_sprocket(drive=True):
    """Nine-tooth sprocket. drive=True: D bore for the gear motor; False: 4.3 mm bore, idler
    on an M4 bolt. Axis along Z; the hub extension (-Z) faces the frame plate."""
    n, step = TRACK_TEETH, 2 * math.pi / TRACK_TEETH
    apothem = TRACK_PITCH_R * math.cos(step / 2)            # centre to the middle of a link
    flat = apothem - LINK_T / 2 - 0.2                       # the links' inner faces rest here
    corner = flat / math.cos(step / 2)
    body = extrude(Polygon(*[(corner * math.cos(k * step), corner * math.sin(k * step)) for k in range(n)],
                           align=None), SPROCKET_W / 2, both=True)
    tip = apothem + LINK_T / 2
    for k in range(n):
        body -= Pos(TRACK_PITCH_R * math.cos(k * step), TRACK_PITCH_R * math.sin(k * step), 0) * Cylinder(
            LINK_T / 2 + 0.6, SPROCKET_W + 2)                # the hinge knuckles sit in these
        a = (k + 0.5) * step
        tooth = Polygon((flat - 1, -2.4), (tip, -1.4), (tip, 1.4), (flat - 1, 2.4), align=None)
        body += Rot(0, 0, math.degrees(a)) * extrude(tooth, SPROCKET_W / 2, both=True)
    ext = TRACK_OFFSET - SPROCKET_W / 2 - PLATE_T - 1       # hub reaches to 1 mm off the plate
    body += Pos(0, 0, -SPROCKET_W / 2 - ext) * Cylinder(HUB_R, ext + SPROCKET_W,
                                                        align=(Align.CENTER, Align.CENTER, Align.MIN))
    if drive:
        body -= _d_bore(2 * (SPROCKET_W + ext) + 2)
        body -= Pos(0, HUB_R / 2, -SPROCKET_W / 2 - ext / 2) * _y_cyl(1.4, HUB_R + 2)
    else:
        body -= Cylinder(2.15, 2 * (SPROCKET_W + ext) + 2)
    return body


def track_frame():
    """Side plate of a track unit (LEFT/RIGHT ports): gear motor at +Y, idler slot at -Y."""
    top, bottom = SLEEVE_SQ / 2, TRACK_AXLE_Z - 16
    length = TRACK_AXLE_SPACING + 32
    body = _sleeve() + Pos(PLATE_T / 2, 0, (top + bottom) / 2) * Box(PLATE_T, length, top - bottom)
    body -= _sleeve_cuts()
    body -= Pos(PLATE_T / 2, TRACK_AXLE_SPACING / 2, TRACK_AXLE_Z) * Rot(90, 0, 0) * _gearmotor_cut(PLATE_T + 2)
    for dy in (-3, 0, 3):                                   # idler axle slot: 6 mm of track tension
        body -= Pos(0, -TRACK_AXLE_SPACING / 2 + dy, TRACK_AXLE_Z) * port._along_x(2.15, PLATE_T + 2, -1)
    body -= Pos(PLATE_T / 2, -TRACK_AXLE_SPACING / 2, TRACK_AXLE_Z) * Box(PLATE_T + 2, 6, 4.3)
    for s in (-1, 1):                                       # lightening windows
        body -= Pos(PLATE_T / 2, s * 38, TRACK_AXLE_Z + 2) * Box(PLATE_T + 2, 30, 18)
    return body


def track_ring():
    """Nine links wrapped round a sprocket (for the mesh check), sprocket axis along Z."""
    step = 2 * math.pi / TRACK_TEETH
    links = []
    for k in range(TRACK_TEETH):
        x, y = TRACK_PITCH_R * math.cos(k * step), TRACK_PITCH_R * math.sin(k * step)
        heading = math.degrees((k + 0.5) * step) + 90
        links.append(Pos(x, y, 0) * Rot(0, 0, heading) * Rot(90, 0, 0) * track_link())
    return links


# =========================================================================== boat
FLOAT_D = 65.0
SADDLE_T = 4.0
SADDLE_L = 44.0             # along the float
THRUST_Z = 75.0             # prop axis above the tube axis: 5-inch prop clears the hub and water
THRUST_PLATE_T = 8.0


def float_saddle():
    """Cradle that slides onto the tube (through bore) and straps to a 65 mm foam float lying
    fore-aft under it. Two straps or cable ties go through the slots."""
    r_in = FLOAT_D / 2 + 0.5
    r_out = r_in + SADDLE_T
    zc = -(SLEEVE_SQ / 2 + r_out) + 1.0                     # float axis; shell overlaps the block 1 mm
    body = Box(SLEEVE_L, SADDLE_L, SLEEVE_SQ)
    shell = Pos(0, 0, zc) * _y_cyl(r_out, SADDLE_L)
    shell &= Pos(0, 0, zc + 0.35 * r_in + 50) * Box(4 * r_out, SADDLE_L + 2, 100)       # top arc only
    body += shell + Pos(0, 0, -SLEEVE_SQ / 2 - 2) * Box(SLEEVE_L, SADDLE_L, 5)
    body -= Pos(0, 0, zc) * _y_cyl(r_in, SADDLE_L + 2)
    body -= port._along_x(BORE_R, SLEEVE_L + 2, -SLEEVE_L / 2 - 1)
    body -= _y_cyl(port.TUBE_PIN_D / 2, SADDLE_L + 2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            body -= Pos(sx * 27, sy * 12, zc + 22) * Box(3.5, 14, 30)                   # strap slots
    return body


def thruster_mount():
    """Mast on the tube end carrying a brushless motor with its axis fore-aft (along Y), for
    an air propeller. The plate is flush with one side so the part prints lying on that side;
    the motor can bolt to either face."""
    y = -SLEEVE_SQ / 2 + THRUST_PLATE_T / 2
    x = -SLEEVE_L / 2 + END_WALL / 2
    top = SLEEVE_SQ / 2
    body = _sleeve() + Pos(x, y, (top + THRUST_Z) / 2) * Box(SLEEVE_L + END_WALL, THRUST_PLATE_T, THRUST_Z - top)
    body += Pos(x, y, THRUST_Z) * _y_cyl(17, THRUST_PLATE_T)
    body += Pos(x, 0, top + 3) * Box(SLEEVE_L + END_WALL, SLEEVE_SQ, 6)                 # foot
    body -= _sleeve_cuts()
    body -= Pos(x, y, THRUST_Z) * Rot(90, 0, 0) * _motor_pattern(THRUST_PLATE_T + 2)
    return body
