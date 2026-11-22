"""Module-side printed parts. All are modelled in the port frame (see port.py)."""
import math

from build123d import Align, Box, Cylinder, Plane, Polygon, Pos, Rot, extrude

from . import port

# --- Quad arm --------------------------------------------------------------
QUAD_ARM_TUBE_L = 143.0         # 400 mm motor-to-motor diagonal for 9-inch props
PROP_D = 228.6                  # 9047 propeller (9 inch)
# 2212-class motors (A2212 / Readytosky 2212 920 KV): four M3 holes in a cross, one pair
# 16 mm apart and the other pair 19 mm apart. Measure your motor if it is another brand.
MOTOR_HOLES = ((8.0, 0.0), (-8.0, 0.0), (0.0, 9.5), (0.0, -9.5))
MOTOR_SCREW_D = 3.3
MOTOR_SHAFT_D = 9.0
MOTOR_PLATE_D = 32.0
MOTOR_PLATE_T = 5.0
SLEEVE_L = 25.0
SLEEVE_SQ = 24.0
MOTOR_OFFSET = MOTOR_PLATE_D / 2 + 3   # motor axis beyond the tube end


def motor_mount():
    """Sleeve that pins onto the tube end with a cantilevered motor plate.

    Local frame: tube axis along X, tube end at X = 0, motor axis at
    X = MOTOR_OFFSET pointing +Z.
    """
    top = SLEEVE_SQ / 2
    body = Pos(-SLEEVE_L / 2, 0, 0) * Box(SLEEVE_L, SLEEVE_SQ, SLEEVE_SQ)
    # web + plate, flush with the top of the sleeve
    body += Pos(MOTOR_OFFSET / 2, 0, top - MOTOR_PLATE_T / 2) * Box(
        MOTOR_OFFSET, SLEEVE_SQ, MOTOR_PLATE_T)
    body += Pos(3, 0, 0) * Box(6, SLEEVE_SQ, SLEEVE_SQ)       # end stop / stiffener
    plate = Cylinder(MOTOR_PLATE_D / 2, MOTOR_PLATE_T,
                     align=(Align.CENTER, Align.CENTER, Align.MAX))
    body += Pos(MOTOR_OFFSET, 0, top) * plate

    bore_r = (port.TUBE_OD + port.TUBE_BORE_CLEAR) / 2
    bore = Cylinder(bore_r, SLEEVE_L + 1, align=(Align.CENTER, Align.CENTER, Align.MIN))
    body -= Pos(-SLEEVE_L - 1, 0, 0) * Rot(0, 90, 0) * bore
    # wire exit from the tube up to the ESC/motor
    body -= Pos(-1, 0, 0) * Rot(0, 90, 0) * Cylinder(
        port.WIRE_HOLE_D / 2, 8, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # cross pin through sleeve + tube
    body -= Pos(-SLEEVE_L / 2, 0, 0) * Rot(90, 0, 0) * Cylinder(
        port.TUBE_PIN_D / 2, SLEEVE_SQ + 2)
    # motor screws + shaft clearance
    for hx, hy in MOTOR_HOLES:
        body -= Pos(MOTOR_OFFSET + hx, hy, top) * Cylinder(MOTOR_SCREW_D / 2, 4 * MOTOR_PLATE_T)
    body -= Pos(MOTOR_OFFSET, 0, top) * Cylinder(MOTOR_SHAFT_D / 2, 4 * MOTOR_PLATE_T)
    return body


def tube(length: float = QUAD_ARM_TUBE_L):
    """Carbon tube (reference geometry for assemblies, not printed)."""
    outer = Cylinder(port.TUBE_OD / 2, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    inner = Cylinder(port.TUBE_ID / 2, length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    x0 = -port.ENGAGE + port.END_WALL
    return Pos(x0, 0, 0) * Rot(0, 90, 0) * (outer - inner)


def quad_arm_assembly():
    """Plug + tube + motor mount, in the port frame. Returns a dict of parts."""
    tube_end = -port.ENGAGE + port.END_WALL + QUAD_ARM_TUBE_L
    return {
        "port_plug": port.plug(),
        "tube": tube(),
        "motor_mount": Pos(tube_end, 0, 0) * motor_mount(),
    }


# --- Printed one-piece quad arm ----------------------------------------------
# Plug, hollow box beam and motor plate in one print, for flying without carbon tubes.
# The motor sits where the tube version puts it, so prop clearances are the same.
ARM_MOTOR_X = -port.ENGAGE + port.END_WALL + QUAD_ARM_TUBE_L + MOTOR_OFFSET   # 135 mm
ARM_BEAM = 24.0                 # beam height and width, same as the plug
ARM_WALL = 1.6                  # four 0.4 mm perimeters: solid walls, no infill needed
ARM_SCREW_HEAD_R = 3.0          # clearance for the M3 heads under the plate


def arm_motor_holes():
    """Motor screw holes on the printed arm: the 2212 cross turned 45 degrees, so every
    screw head sits between the beam's side walls and is reached from below."""
    c = math.cos(math.radians(45))
    return [((x - y) * c, (x + y) * c) for x, y in MOTOR_HOLES]


def printed_arm():
    """Quad arm printed in one piece, standing as modelled (bottom flat on the bed).

    Port frame: plug toward -X, motor axis at X = ARM_MOTOR_X pointing +Z. The beam is a
    24 x 24 mm box with 1.6 mm walls; inside it the motor and ESC wires run back to the
    plug's wire hole. The beam's side walls carry on under the motor plate; its bottom and
    end stop short, so the motor screws are reached from below."""
    half = ARM_BEAM / 2
    holes = arm_motor_holes()
    reach = max(math.hypot(x, y) for x, y in holes) + ARM_SCREW_HEAD_R
    assert max(abs(y) for _, y in holes) + ARM_SCREW_HEAD_R < half - ARM_WALL, "heads hit the walls"
    body = port.plug(with_tube_bore=False)
    body -= Pos(0, 0, -half - 10) * Box(40, 60, 20)                  # flange flush with the bed
    beam_end = ARM_MOTOR_X - reach - 1.0
    x0 = port.FLANGE_T - 0.5
    body += Pos((x0 + beam_end) / 2, 0, 0) * Box(beam_end - x0, ARM_BEAM, ARM_BEAM)
    plate = Cylinder(MOTOR_PLATE_D / 2, MOTOR_PLATE_T, align=(Align.CENTER, Align.CENTER, Align.MAX))
    body += Pos(ARM_MOTOR_X, 0, half) * plate
    # side walls continue under the plate, sloped at 45 degrees so they print without support
    z_top = half - MOTOR_PLATE_T + 0.5
    x_tip = ARM_MOTOR_X + math.sqrt((MOTOR_PLATE_D / 2) ** 2 - half ** 2) - 0.5
    rib = Polygon((beam_end - 1, -half), (x_tip - (z_top + half), -half), (x_tip, z_top),
                  (beam_end - 1, z_top), align=None)
    rib = extrude(Plane.XZ * rib, ARM_WALL / 2, both=True)
    for s in (-1, 1):
        body += Pos(0, s * (half - ARM_WALL / 2), 0) * rib
    # hollow beam, closed at the plug end; wire hole into the plug
    inner = ARM_BEAM - 2 * ARM_WALL
    body -= Pos((x0 + 2 + beam_end + 1) / 2, 0, 0) * Box(beam_end + 1 - x0 - 2, inner, inner)
    body -= port._along_x(port.WIRE_HOLE_D / 2, port.ENGAGE + x0 + 4, -port.ENGAGE - 1)
    # motor screws and shaft clearance
    for hx, hy in holes:
        body -= Pos(ARM_MOTOR_X + hx, hy, 0) * Cylinder(MOTOR_SCREW_D / 2, 60)
    body -= Pos(ARM_MOTOR_X, 0, 0) * Cylinder(MOTOR_SHAFT_D / 2, 60)
    return body


def port_cap():
    """Blanking cap for an unused port."""
    return port.plug(with_tube_bore=False)
