"""Module-side printed parts. All are modelled in the port frame (see port.py)."""
from build123d import Align, Box, Cylinder, Pos, Rot

from . import port

# --- Quad arm --------------------------------------------------------------
QUAD_ARM_TUBE_L = 85.0          # ~284 mm diagonal: 5-inch prop tips clear the hub by >10 mm
PROP_D = 127.0                  # 5-inch propeller
MOTOR_PATTERN = 16.0           # 2207-class motors: M3 on a 16 x 16 mm square
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
    for sx in (-1, 1):
        for sy in (-1, 1):
            body -= Pos(MOTOR_OFFSET + sx * MOTOR_PATTERN / 2, sy * MOTOR_PATTERN / 2,
                        top) * Cylinder(MOTOR_SCREW_D / 2, 4 * MOTOR_PLATE_T)
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


def port_cap():
    """Blanking cap for an unused port."""
    return port.plug(with_tube_bore=False)
