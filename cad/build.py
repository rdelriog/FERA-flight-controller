"""Build every FERA printed part into cad/out/ and run interface checks.

    cad/.venv/Scripts/python cad/build.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build123d import Box, Compound, Pos, export_step, export_stl  # noqa: E402

from fera import hub, modules, port  # noqa: E402

OUT = Path(__file__).parent / "out"


def check(name: str, ok: bool, detail: str = ""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name} {detail}")
    if not ok:
        check.failed = True


check.failed = False


def render(shape, path, eye=(-260, -200, 220), size=1100):
    """Hidden-line isometric preview as a PNG (for quick visual review)."""
    from PIL import Image, ImageDraw
    centre = shape.bounding_box().center()
    origin = (centre.X + eye[0], centre.Y + eye[1], centre.Z + eye[2])
    visible, _ = shape.project_to_viewport(origin, look_at=centre)
    polys = []
    for e in visible:
        n = 2 if e.geom_type.name == "LINE" else 24
        polys.append([(e @ (i / n)).X for i in range(n + 1)]
                     and [((e @ (i / n)).X, (e @ (i / n)).Y) for i in range(n + 1)])
    xs = [x for pl in polys for x, _ in pl]
    ys = [y for pl in polys for _, y in pl]
    scale = (size - 60) / max(max(xs) - min(xs), max(ys) - min(ys))
    img = Image.new("RGB", (size, int((max(ys) - min(ys)) * scale) + 60), "white")
    draw = ImageDraw.Draw(img)
    for pl in polys:
        draw.line([((x - min(xs)) * scale + 30, (max(ys) - y) * scale + 30) for x, y in pl],
                  fill=(30, 60, 110), width=2)
    img.save(path)


def other_modes(base, lid):
    """Starter parts for plane, rover, crawler and boat: export, check, assemble."""
    import math

    from build123d import Cylinder, Pos, Rot

    from fera import modes as m

    parts = {
        "nose_motor_mount": m.nose_motor_mount(), "wing_rib": m.wing_rib(),
        "wing_servo_rib": m.wing_rib(servo=True), "tail_mount": m.tail_mount(),
        "gearmotor_mount": m.gearmotor_mount(), "wheel": m.wheel(), "skid": m.skid(),
        "track_frame": m.track_frame(), "track_sprocket": m.track_sprocket(),
        "track_idler": m.track_sprocket(drive=False), "track_link": m.track_link(),
        "float_saddle": m.float_saddle(), "thruster_mount": m.thruster_mount(),
    }
    print("Other modes, parts:")
    for name, part in parts.items():
        solids = len(part.solids())
        bb = part.bounding_box().size
        print(f"  {name:16s} {bb.X:6.1f} x {bb.Y:6.1f} x {bb.Z:5.1f} mm  "
              f"{part.volume / 1000:6.1f} cm3  solids={solids}")
        check(f"{name} is one valid solid", solids == 1 and part.is_valid)
        export_step(part, str(OUT / f"{name}.step"))
        export_stl(part, str(OUT / f"{name}.stl"))

    print("Other modes, checks:")
    stub = port._along_x(port.TUBE_OD / 2, 80, -40) - port._along_x(port.TUBE_ID / 2, 82, -41)
    end = port._along_x(port.TUBE_OD / 2, 40, -40) - port._along_x(port.TUBE_ID / 2, 42, -41)
    for name in ("nose_motor_mount", "tail_mount", "gearmotor_mount", "skid", "track_frame",
                 "thruster_mount"):
        clash = (parts[name] & end).volume
        check(f"tube fits {name}", clash < 0.5, f"(overlap {clash:.2f} mm3)")
    for name in ("wing_rib", "wing_servo_rib", "float_saddle"):
        clash = (parts[name] & stub).volume
        check(f"tube passes through {name}", clash < 0.5, f"(overlap {clash:.2f} mm3)")
    wall = m.rib_half_thickness(m.WING_SPAR_AT) - m.BORE_R
    check("wing rib keeps 2.5 mm of material around the spar", wall >= 2.5, f"({wall:.1f} mm)")
    wheel_bottom = -m.AXLE_DROP - m.WHEEL_D / 2
    skid_bottom = parts["skid"].bounding_box().min.Z
    check("rover skids are level with the wheels", abs(wheel_bottom - skid_bottom) < 0.2,
          f"(wheel {wheel_bottom:.1f}, skid {skid_bottom:.1f} mm below the tube axis)")
    hub_bottom = -hub.PORT_Z
    check("rover ground clearance under the hub is at least 30 mm", hub_bottom - wheel_bottom >= 30,
          f"({hub_bottom - wheel_bottom:.0f} mm)")
    ring = m.track_ring()
    clash = sum((parts["track_sprocket"] & link).volume for link in ring)
    check("track links wrap the sprocket without interference", clash < 1.0, f"(overlap {clash:.2f} mm3)")
    clash = (ring[0] & ring[1]).volume + (parts["track_link"]
                                         & Pos(m.TRACK_PITCH, 0, 0) * parts["track_link"]).volume
    check("neighbouring track links clear each other (straight and wrapped)", clash < 0.5,
          f"(overlap {clash:.2f} mm3)")
    track_bottom = m.TRACK_AXLE_Z - (m.TRACK_PITCH_R * math.cos(math.pi / m.TRACK_TEETH) + m.LINK_T / 2)
    check("crawler ground clearance under the hub is at least 20 mm", hub_bottom - track_bottom >= 20,
          f"({hub_bottom - track_bottom:.0f} mm)")

    def arm(length):
        """Plug + tube in the port frame, and the X of the tube end."""
        return [port.plug(), modules.tube(length)], -port.ENGAGE + port.END_WALL + length

    def on_ports(names, items):
        return [hub.port_location(n) * it for n in names for it in items]

    def finish(name, solids, eye=(-420, -330, 300)):
        export_step(Compound(children=solids), str(OUT / f"assembly_{name}.step"))
        render(Compound(children=solids), OUT / f"assembly_{name}.png", eye=eye)
        clash = sum((base & s).volume for s in solids[2:] if s.bounding_box().min.Z < 60
                    and len(s.solids()) == 1 and s.volume < 80000)
        check(f"{name}: modules do not cut into the hub", clash < 2.0, f"(overlap {clash:.2f} mm3)")

    # plane: tractor nose, two wing halves on tube spars, tail boom
    span_tube, boom = 450.0, 400.0
    solids = [base, lid]
    items, x_end = arm(60.0)
    solids += on_ports(["FRONT"], items + [Pos(x_end, 0, 0) * parts["nose_motor_mount"]])
    items, x_end = arm(boom)
    solids += on_ports(["BACK"], items + [Pos(x_end, 0, 0) * parts["tail_mount"]])
    wing, x_end = arm(span_tube)
    stations = [22 + k * (x_end - 22 - m.RIB_COLLAR_L) / 5 for k in range(6)]
    rod_y, rod_z = m._rib_point(m.WING_ROD_AT, m._naca4412(m.WING_ROD_AT)[0])
    for side, flip in (("RIGHT", 0), ("LEFT", 180)):        # leading edge toward the FRONT port
        ribs = [Pos(x, 0, 0) * Rot(0, 0, flip) * Pos(-m.RIB_T / 2 if flip else 0, 0, 0)
                * parts["wing_servo_rib" if k == 3 else "wing_rib"] for k, x in enumerate(stations)]
        rod = Pos(stations[0], rod_y * (-1 if flip else 1), rod_z) * port._along_x(
            m.WING_ROD_D / 2, stations[-1] - stations[0] + m.RIB_T)
        solids += on_ports([side], wing + ribs + [rod])
    finish("plane", solids, eye=(-700, -900, 600))
    half_span = hub.ACROSS_FLATS / 2 + x_end
    print(f"Plane: span {2 * half_span:.0f} mm, chord {m.WING_CHORD:.0f} mm, "
          f"ribbed area {2 * (stations[-1] - stations[0]) * m.WING_CHORD / 1e4:.1f} dm2")

    # rover: gear motor and wheel left and right, skids front and back
    items, x_end = arm(modules.QUAD_ARM_TUBE_L)
    solids = [base, lid]
    solids += on_ports(["LEFT", "RIGHT"], items + [
        Pos(x_end, 0, 0) * parts["gearmotor_mount"],
        Pos(x_end + m.PLATE_T + 1 + m.HUB_EXT, 0, -m.AXLE_DROP) * Rot(0, 90, 0) * parts["wheel"]])
    solids += on_ports(["FRONT", "BACK"], items + [Pos(x_end, 0, 0) * parts["skid"]])
    finish("rover", solids)
    track_w = 2 * (hub.ACROSS_FLATS / 2 + x_end + m.PLATE_T + 1 + m.HUB_EXT + m.WHEEL_W / 2)
    print(f"Rover: wheel track {track_w:.0f} mm, skids {2 * (hub.ACROSS_FLATS / 2 + x_end - 6):.0f} mm apart")

    # crawler: a track unit left and right (links shown wrapped on the sprockets only)
    items, x_end = arm(60.0)
    unit = [Pos(x_end, 0, 0) * parts["track_frame"]]
    for y, key in ((m.TRACK_AXLE_SPACING / 2, "track_sprocket"), (-m.TRACK_AXLE_SPACING / 2, "track_idler")):
        place = Pos(x_end + m.TRACK_OFFSET, y, m.TRACK_AXLE_Z) * Rot(0, 90, 0)
        unit += [place * parts[key]] + [place * link for link in ring]
    solids = [base, lid] + on_ports(["LEFT", "RIGHT"], items + unit)
    finish("crawler", solids)
    print(f"Crawler: {m.TRACK_LINKS} links per side, axles {m.TRACK_AXLE_SPACING:.0f} mm apart, "
          f"track centres {2 * (hub.ACROSS_FLATS / 2 + x_end + m.TRACK_OFFSET):.0f} mm apart")

    # boat: a float and an air-propeller mast left and right
    items, x_end = arm(120.0)
    float_z = -(modules.SLEEVE_SQ / 2 + m.FLOAT_D / 2 + 0.5 + m.SADDLE_T) + 1.0
    foam = Pos(x_end - 45, 0, float_z) * Rot(90, 0, 0) * Cylinder(m.FLOAT_D / 2, 320)
    solids = [base, lid] + on_ports(["LEFT", "RIGHT"], items + [
        Pos(x_end - 45, 0, 0) * parts["float_saddle"], Pos(x_end, 0, 0) * parts["thruster_mount"], foam])
    finish("boat", solids)
    prop_inner = hub.ACROSS_FLATS / 2 + x_end - modules.SLEEVE_L / 2 - modules.PROP_D / 2
    check("boat propellers clear the hub", prop_inner > hub.ACROSS_FLATS / 2 + 5,
          f"(inner tip {prop_inner:.0f} mm from the centre, hub edge {hub.ACROSS_FLATS / 2:.0f} mm)")
    lift = 2 * math.pi * (m.FLOAT_D / 2) ** 2 * 320 / 1e6
    print(f"Boat: two 320 mm floats displace {lift:.1f} kg fully submerged")


def main():
    OUT.mkdir(exist_ok=True)
    arm = modules.quad_arm_assembly()
    parts = {
        "hub_base": hub.base(),
        "hub_lid": hub.lid(),
        "port_plug": arm["port_plug"],
        "motor_mount": modules.motor_mount(),
        "port_cap": modules.port_cap(),
        "port_coupon": port.coupon(),
    }

    print("Parts:")
    for name, part in parts.items():
        solids = len(part.solids())
        bb = part.bounding_box().size
        print(f"  {name:12s} {bb.X:6.1f} x {bb.Y:6.1f} x {bb.Z:5.1f} mm  "
              f"{part.volume / 1000:6.1f} cm3  solids={solids}")
        check(f"{name} is one valid solid", solids == 1 and part.is_valid)
        export_step(part, str(OUT / f"{name}.step"))
        export_stl(part, str(OUT / f"{name}.stl"))

    print("Interface checks:")
    base = parts["hub_base"]
    for pname in hub.PORT_ANGLES:
        loc = hub.port_location(pname)
        clash = (base & (loc * arm["port_plug"])).volume
        check(f"plug clears socket at {pname}", clash < 0.5, f"(overlap {clash:.2f} mm3)")
    wrong = hub.port_location("FRONT") * (
        port.plug().rotate(__import__("build123d").Axis.X, 90))
    clash = (base & wrong).volume
    check("plug rotated 90 deg is blocked by the key", clash > 5, f"(overlap {clash:.1f} mm3)")
    clash = (arm["port_plug"] & arm["tube"]).volume
    check("tube fits plug bore", clash < 0.5, f"(overlap {clash:.2f} mm3)")
    clash = (arm["motor_mount"] & arm["tube"]).volume
    check("tube fits motor mount bore", clash < 0.5, f"(overlap {clash:.2f} mm3)")
    clash = (parts["hub_lid"] & base).volume
    check("lid sits on base without overlap", clash < 0.5, f"(overlap {clash:.2f} mm3)")

    # battery on the lid
    import math
    lid = parts["hub_lid"]
    pack = hub.battery()
    a = math.radians(hub.BATTERY_ANGLE)

    def in_pack(x, y, margin):
        along, across = x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)
        return abs(along) < hub.BATTERY_MAX[0] / 2 + margin and abs(across) < hub.BATTERY_MAX[1] / 2 + margin

    latch = [(r * math.cos(math.radians(ang)), r * math.sin(math.radians(ang)))
             for ang in hub.PORT_ANGLES.values() for r in [hub.ACROSS_FLATS / 2 + port.LATCH_X]]
    screws = list(hub._diagonals())
    check("battery (up to %d x %d mm) leaves all four latch holes free" % hub.BATTERY_MAX[:2],
          not any(in_pack(x, y, hub.LATCH_ACCESS_D / 2) for x, y in latch))
    check("battery leaves the four lid screws free", not any(in_pack(x, y, 3.0) for x, y in screws))
    ex, ey = hub.lead_exit_xy()
    check("battery lead slot is beside the pack, not under it",
          not in_pack(ex, ey, hub.LEAD_EXIT[0] / 2), f"(slot at {ex:.0f}, {ey:.0f} mm)")
    clash = (lid & pack).volume
    check("battery sits between the strap loops", clash < 0.5, f"(overlap {clash:.2f} mm3)")
    clash = (base & (Pos(ex, ey, hub.HEIGHT - 10) * Box(hub.LEAD_EXIT[0], hub.LEAD_EXIT[1], 20))).volume
    check("nothing in the hub blocks the lead slot", clash < 0.5, f"(overlap {clash:.2f} mm3)")
    for name, size in hub.BATTERY_SIZES.items():
        check(f"{name} pack ({size[0]:.0f} x {size[1]:.0f} x {size[2]:.0f} mm) fits the envelope",
              all(s <= m for s, m in zip(size, hub.BATTERY_MAX)))
    print(f"Battery: on the lid at {hub.BATTERY_ANGLE:.0f} deg, top of the largest pack "
          f"{hub.HEIGHT + hub.LID_T + hub.BATTERY_MAX[2]:.0f} mm above the hub floor")

    pcb = hub.board_solid()
    clash = (base & pcb).volume
    check("FERA Core PCB fits inside the hub", clash < 0.5, f"(overlap {clash:.2f} mm3)")
    export_step(pcb, str(OUT / "fera_core_pcb_outline.step"))
    render(Compound(children=[base, pcb]), OUT / "hub_with_pcb.png", eye=(-120, -160, 330))

    quad = [base, parts["hub_lid"], hub.battery(hub.BATTERY_SIZES["4S 1500 mAh"])]
    for pname in hub.PORT_ANGLES:
        loc = hub.port_location(pname)
        quad += [loc * p for p in arm.values()]
    export_step(Compound(children=quad), str(OUT / "assembly_quad.step"))
    motor_r = hub.ACROSS_FLATS / 2 - port.ENGAGE + port.END_WALL \
        + modules.QUAD_ARM_TUBE_L + modules.MOTOR_OFFSET
    print(f"Quad: motor-to-motor diagonal {2 * motor_r:.0f} mm")
    check("5-inch props clear each other", motor_r * 2 ** 0.5 > 127 + 5,
          f"(adjacent motor spacing {motor_r * 2 ** 0.5:.0f} mm)")

    render(Compound(children=quad), OUT / "assembly_quad.png")
    render(Compound(children=[base, hub.port_location("FRONT") * arm["port_plug"]]),
           OUT / "hub_base.png")
    tip_gap = motor_r - modules.PROP_D / 2 - hub.ACROSS_FLATS / 2
    check("prop tips clear the hub footprint by 8 mm", tip_gap >= 8, f"(gap {tip_gap:.1f} mm)")
    other_modes(base, parts["hub_lid"])
    print(f"Output: {OUT}")
    sys.exit(1 if check.failed else 0)


if __name__ == "__main__":
    main()
