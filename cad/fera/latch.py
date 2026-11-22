"""FERA port latch: a spring-loaded steel pin that drops into the plug, with a hall sensor.

All geometry is in the port frame (see port.py): the pin axis is vertical at
X = port.LATCH_X, Y = 0. `z_lid` is the underside of the hub lid in that frame.

How it works
  * The pin is a 4 mm steel dowel. A printed collar is glued on it; a compression spring
    between the collar and the ceiling of a tower on the lid pushes it down.
  * Pushing a plug in, the ramp on the plug's top lifts the pin; at full depth the pin
    snaps into the pocket. Pulling the plug out is then blocked by steel, not plastic snaps.
  * To release: lift the knob (6 mm) and pull the module out.
  * Visible: lifting the knob uncovers a groove on the tower (paint it red).
  * Sensed: a 2 x 1 mm magnet in the knob sits over a DRV5032AJ hall switch in the tower
    top when the pin is down. Measured with TI's thresholds (SLVSDC7H): on above 9.5 mT,
    guaranteed off below 3 mT. A 2 x 1 mm N52 disc gives about 39 mT at 2 mm (down) and
    1.2 mT at 8 mm (lifted). Output is open drain, low = latched, into the LATCHn inputs.
  * Secondary retention: a 2 mm pin (a piece of 1.75 mm filament works) through the cross
    hole in knob skirt and tower stops the knob being lifted.
"""
from build123d import Align, Box, Cylinder, Pos, Rot

from . import port

PIN_D = 4.0
PIN_L = 35.0                  # 4 x 35 mm steel dowel
LIFT = 6.0                    # knob travel to release
TIP_GAP = 0.5                 # pin tip above the pocket floor when latched
COLLAR_D = 8.0
COLLAR_H = 4.0
COLLAR_BORE = 4.05            # glue fit on the pin
BORE_D = 8.8                  # tower bore the collar slides in
SPRING_SOLID = 5.5            # longest solid length allowed for the spring
TOP_WALL = 2.5
TOP_HOLE_D = 4.6
TOWER_D = 15.2
BOSS_D = 10.0                 # on the hub base, under the collar
SKIRT_CLEAR = 0.3
SKIRT_T = 1.6
KNOB_GAP = 1.0                # knob above the tower top when latched
KNOB_TOP_T = 7.5
SLOT_W, SLOT_D = 2.4, 1.4     # key slot (outboard) and wire groove (inboard) on the tower
RIB_W, RIB_D = 2.0, 1.1
BAND_D = 0.6                  # paint groove, visible only when lifted
CROSS_D = 2.2
CROSS_Y = -6.0                # cross hole runs along X at this Y, through solid wall only
SENSOR = (3.6, 4.4, 1.8)      # TO-92 pocket: radial, tangential, depth (body 3.15 x 4.0 x 1.52)
SENSOR_R = 5.0                # pocket centre, inboard of the pin
MAGNET = (2.2, 1.1)           # 2 x 1 mm disc pocket: diameter, depth
WIRE_HOLE_D = 2.6


def tip_z():
    return port.PLUG_SQ / 2 - port.LATCH_DEPTH + TIP_GAP


def levels(z_lid):
    """Key heights in the port frame for a lid whose underside is at z_lid."""
    ceiling = z_lid + COLLAR_H + LIFT + SPRING_SOLID + 0.5
    top = ceiling + TOP_WALL
    knob0 = top + KNOB_GAP
    return dict(collar=z_lid, ceiling=ceiling, top=top, knob=knob0,
                knob_top=knob0 + KNOB_TOP_T, skirt=knob0 - 10.0,
                pin_top=tip_z() + PIN_L)


def _at(shape):
    return Pos(port.LATCH_X, 0, 0) * shape


def _zcyl(d, z0, z1):
    return Pos(0, 0, z0) * Cylinder(d / 2, z1 - z0, align=(Align.CENTER, Align.CENTER, Align.MIN))


def base_boss(z_lid):
    """Added to the hub base on top of the socket block: the collar's stop."""
    return _at(_zcyl(BOSS_D, port.SOCKET_BLOCK_SQ / 2 - 0.5, z_lid))


def tower(z_lid, z_lid_top):
    """Solid added to the lid (port frame)."""
    L = levels(z_lid)
    return _at(_zcyl(TOWER_D, z_lid_top - 0.5, L["top"]))


def tower_cut(z_lid, z_lid_top):
    """Removed from the lid + tower."""
    L = levels(z_lid)
    r = TOWER_D / 2
    cut = _zcyl(BORE_D, z_lid - 1, L["ceiling"]) + _zcyl(TOP_HOLE_D, L["ceiling"] - 1, L["top"] + 1)
    # key slot, outboard (+X)
    cut += Pos(r, 0, (z_lid_top + L["top"]) / 2 + 0.5) * Box(2 * SLOT_D, SLOT_W, L["top"] - z_lid_top + 1)
    # sensor pocket in the top face, inboard (-X), and a notch for its leads
    sx, sy, sd = SENSOR
    cut += Pos(-SENSOR_R, 0, L["top"] - sd / 2 + 0.01) * Box(sx, sy, sd)
    cut += Pos(-(r + SENSOR_R) / 2 - 0.5, 0, L["top"] - sd / 2 + 0.01) * Box(r - SENSOR_R + 1, SLOT_W, sd)
    # wire groove down the inboard side, then a hole through the lid
    cut += Pos(-r, 0, (z_lid_top + L["top"]) / 2) * Box(2 * SLOT_D, SLOT_W, L["top"] - z_lid_top + 0.1)
    hole_x = -(r - SLOT_D / 2)
    cut += Pos(hole_x, 0, 0) * _zcyl(WIRE_HOLE_D, z_lid - 1, z_lid_top + 0.5)
    # groove under the lid toward the hub centre, over the socket block
    cut += Pos(hole_x - 15, 0, z_lid + 0.75) * Box(30, WIRE_HOLE_D, 1.5 + 0.01)
    # paint band (visible when lifted)
    band = _zcyl(TOWER_D + 2, L["skirt"] + 1.0, L["skirt"] + LIFT - 0.5) - _zcyl(TOWER_D - 2 * BAND_D, 0, 200)
    cut += band
    # secondary-retention cross hole
    cut += Pos(0, CROSS_Y, L["skirt"] + 3.0) * Rot(0, 90, 0) * Cylinder(CROSS_D / 2, 40)
    return _at(cut)


def knob():
    """Pull knob in its own frame: pin axis = Z, underside of the top plate at Z = 0,
    -X faces the hub centre (magnet side). Glue the pin into the bore."""
    inner = TOWER_D + 2 * SKIRT_CLEAR
    outer = inner + 2 * SKIRT_T
    body = _zcyl(outer, -10.0, KNOB_TOP_T) - _zcyl(inner, -11.0, 0)
    rib_in, rib_out = TOWER_D / 2 - RIB_D, inner / 2 + 0.4          # rib rides in the key slot
    body += Pos((rib_in + rib_out) / 2, 0, -5.0) * Box(rib_out - rib_in, RIB_W, 10.0)
    body -= _zcyl(PIN_D + 0.05, -1, KNOB_TOP_T - 1.0)                # blind bore, 6.5 deep
    md, mh = MAGNET
    body -= Pos(-SENSOR_R, 0, 0) * _zcyl(md, -1, mh)
    body -= Pos(0, CROSS_Y, -10.0 + 3.0) * Rot(0, 90, 0) * Cylinder(CROSS_D / 2, 40)
    # grip ridges round the top edge
    for k in range(12):
        body -= Rot(0, 0, 15 + 30 * k) * Pos(outer / 2 + 0.4, 0, KNOB_TOP_T - 2.5) * Cylinder(1.0, 5.2)
    return body


def knob_placed(z_lid, lifted=False):
    L = levels(z_lid)
    return _at(Pos(0, 0, L["knob"] + (LIFT if lifted else 0)) * knob())


def collar():
    return _zcyl(COLLAR_D, 0, COLLAR_H) - _zcyl(COLLAR_BORE, -1, COLLAR_H + 1)


def gauge_height(z_lid):
    return z_lid - tip_z()


def setting_gauge(z_lid):
    """Slide it over the pin, stand the pin tip on the table, push the collar down onto the
    gauge and glue it: sets the collar-to-tip distance."""
    h = gauge_height(z_lid)
    return _zcyl(COLLAR_D + 4, 0, h) - _zcyl(PIN_D + 0.3, -1, h + 1)


def pin(z_lid, lifted=False):
    z0 = tip_z() + (LIFT if lifted else 0)
    return _at(_zcyl(PIN_D, z0, z0 + PIN_L))


def collar_placed(z_lid, lifted=False):
    return _at(Pos(0, 0, z_lid + (LIFT if lifted else 0)) * collar())


def spring_space(z_lid, lifted=False):
    L = levels(z_lid)
    z0 = z_lid + COLLAR_H + (LIFT if lifted else 0)
    return L["ceiling"] - z0
