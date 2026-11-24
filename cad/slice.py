"""Slice the printable parts with the engine of the installed Creality Slicer.

    cad/.venv/Scripts/python cad/slice.py            # all parts -> cad/out/gcode/
    cad/.venv/Scripts/python cad/slice.py port_plug  # just one

It uses the machine, nozzle, material and quality profiles that ship with Creality Slicer
4.8.2 (a Cura 4.8 build) for the printer set up in that slicer (Ender-3 Max Neo, 0.4 mm
nozzle, 1.75 mm PLA, Standard 0.2 mm), plus the temperature / flow / speed values saved in
the slicer by the user. Cura's front end normally resolves the setting formulas before it
calls the engine; this script does that resolution itself and hands CuraEngine a flat
settings file.

Each part is turned into its printing orientation first (see PARTS).
"""
import ast
import configparser
import json
import math
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SLICER = Path(r"C:\Program Files\Creality Slicer 4.8.2")
RES = SLICER / "resources"
MACHINE = "creality_ender3maxneo"
EXTRUDER = "creality_base_extruder_0"
HERE = Path(__file__).parent
STL_DIR = HERE / "out"
OUT = HERE / "out" / "gcode"

# --------------------------------------------------------------------------- settings
# Values saved in the user's slicer profile for this printer and filament (kept as tuned).
TUNED = dict(material_print_temperature=220, material_flow=102, cool_fan_speed=70,
             speed_print=40.0, speed_infill=50, speed_wall_0=30, infill_overlap=20,
             support_xy_distance=0.5, support_z_distance=0.15)
# Chosen here for these parts.
COMMON = dict(wall_line_count=4, top_layers=5, bottom_layers=5, infill_pattern="gyroid",
              adhesion_type="skirt", support_enable=False, material_bed_temperature=60)
LOAD = dict(infill_sparse_density=50)              # plugs, caps, motor mounts, test socket
# hub base and lid: big parts, so inner walls, skins and infill run faster than the tuned
# 20 mm/s (outer walls stay at the tuned 30 mm/s)
SHELL = dict(infill_sparse_density=30, speed_wall_x=40, speed_topbottom=30, speed_infill=60)
BRIDGES = dict(bridge_settings_enabled=True)       # socket roofs are printed as bridges
# Fast profile (the *_fast.gcode files, next to the standard ones): 0.28 mm layers, 25 % infill
# laid every second layer, faster inner walls / infill / skins. Walls and top/bottom layers stay
# as each part has them; the outer wall only goes from 30 to 35 mm/s. Not used for the arms
# (motor loads). The socket fit was chosen at 0.2 mm: check 0_fit_gauge_fast before the hub base.
FAST = dict(layer_height=0.28, infill_sparse_density=25, infill_sparse_thickness=0.56,
            speed_print=60, speed_infill=80, speed_wall_0=35, speed_wall_x=50,
            speed_topbottom=40, speed_travel=150)
FAST_PARTS = ("0_fit_gauge", "3_cap", "5_hub_base", "6_hub_lid", "7_battery_cover", "9_latch_knob_x4")

# rotations: rows of the matrix that maps model coordinates to print coordinates
AS_MODELLED = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
PLUS_X_DOWN = ((0, 0, 1), (0, 1, 0), (-1, 0, 0))   # the +X end of the part sits on the bed
FLIPPED = ((1, 0, 0), (0, -1, 0), (0, 0, -1))      # upside down
MINUS_X_DOWN = ((0, 0, -1), (0, 1, 0), (1, 0, 0))  # the -X end of the part sits on the bed
MINUS_Y_DOWN = ((1, 0, 0), (0, 0, -1), (0, 1, 0))  # lying on its -Y side

PARTS = {
    # name: (stl, rotation, copies, settings, support-free cylinder or None, note)
    # The cylinder (radius, height) is centred on the tube axis and is wider than the 16 mm
    # bore, so the ledge at the end of the bore gets no support column down the bore.
    "0_fit_gauge": ("fit_gauge", AS_MODELLED, 1,
                    {**BRIDGES, "infill_sparse_density": 20, "wall_line_count": 3, "top_layers": 4,
                     "bottom_layers": 4, "adhesion_type": "brim", "brim_width": 5}, None,
                    "Three short sockets, 0.20 / 0.30 / 0.40 mm clearance per side (1, 2, 3 notches)."),
    "1_coupon": ("port_coupon", AS_MODELLED, 1, {**LOAD, **BRIDGES}, None,
                 "Test socket, printed lying down exactly as the sockets in the hub print."),
    "2_plug": ("port_plug", PLUS_X_DOWN, 1,
               {**LOAD, "support_enable": True, "support_type": "buildplate",
                "adhesion_type": "brim", "brim_width": 5}, (10.0, 46.0),
               "Tube collar on the bed, bore vertical. Support only under the flange."),
    "3_cap": ("port_cap", PLUS_X_DOWN, 1, LOAD, None, "Flange face on the bed, no support."),
    "4_motor_mount": ("motor_mount", FLIPPED, 1, LOAD, None,
                      "Upside down: motor face on the bed, no support."),
    "5_hub_base": ("hub_base", AS_MODELLED, 1, {**SHELL, **BRIDGES}, None,
                   "Floor on the bed, no support: socket roofs and windows are bridges."),
    "6_hub_lid": ("hub_lid", AS_MODELLED, 1, {**SHELL, **BRIDGES}, None,
                  "Flat, no support: the four strap loops print as bridges."),
    "7_battery_cover": ("battery_cover", FLIPPED, 1,
                        {**SHELL, **BRIDGES, "wall_line_count": 3, "infill_sparse_density": 20,
                         "top_layers": 4, "bottom_layers": 4}, None,
                        "Optional. Upside down: roof on the bed, no support (tab gussets are 45 degrees)."),
    "8_arm_printed": ("printed_arm", AS_MODELLED, 1, {**LOAD, **BRIDGES}, None,
                      "One-piece quad arm (no tube, plug or motor mount needed). Bottom on the bed, no support."),
    "8_arm_printed_x4": ("printed_arm", AS_MODELLED, 4, {**LOAD, **BRIDGES}, None, "Four one-piece arms."),
    "9_latch_knob_x4": ("latch_knob", FLIPPED, 4, LOAD, None, "Knob top on the bed, no support."),
    "9_latch_collar_x4": ("latch_collar", AS_MODELLED, 4, {**LOAD, "adhesion_type": "brim", "brim_width": 4},
                          None, "Four collars for the latch pins."),
    "9_latch_gauge": ("latch_gauge", AS_MODELLED, 1, LOAD, None, "Sets each collar 9 mm above its pin tip."),
    "plug_x4": ("port_plug", PLUS_X_DOWN, 4,
                {**LOAD, "support_enable": True, "support_type": "buildplate",
                 "adhesion_type": "brim", "brim_width": 5}, (10.0, 46.0), "Four plugs."),
    "mount_x4": ("motor_mount", FLIPPED, 4, LOAD, None, "Four motor mounts."),
    # ---- plane
    "plane_nose_mount": ("nose_motor_mount", PLUS_X_DOWN, 1,
                         {**LOAD, "support_enable": True, "support_type": "everywhere"}, None,
                         "Motor face on the bed; support under the sleeve between the webs."),
    "plane_wing_rib": ("wing_rib", MINUS_X_DOWN, 1, LOAD, None, "Flat, collar up, no support."),
    "plane_wing_rib_x5": ("wing_rib", MINUS_X_DOWN, 5, LOAD, None, "Five plain ribs (one wing half)."),
    "plane_servo_rib": ("wing_servo_rib", MINUS_X_DOWN, 1, LOAD, None, "Rib with the 9 g servo opening."),
    "plane_tail_mount": ("tail_mount", MINUS_X_DOWN, 1, LOAD, None,
                         "Standing on the sleeve end, slots open upward, no support."),
    # ---- rover
    "rover_motor_mount": ("gearmotor_mount", PLUS_X_DOWN, 1, LOAD, None, "Motor plate on the bed, no support."),
    "rover_wheel": ("wheel", FLIPPED, 1, LOAD, None, "Outer face on the bed, hub extension up, no support."),
    "rover_skid": ("skid", MINUS_Y_DOWN, 1, LOAD, None, "Lying on its side, no support."),
    # ---- crawler
    "crawler_frame": ("track_frame", PLUS_X_DOWN, 1, LOAD, None, "Plate on the bed, no support."),
    "crawler_sprocket": ("track_sprocket", FLIPPED, 1, LOAD, None, "Hub extension up, no support."),
    "crawler_idler": ("track_idler", FLIPPED, 1, LOAD, None, "Hub extension up, no support."),
    "crawler_links_x28": ("track_link", AS_MODELLED, 28, LOAD, None,
                          "28 track links: one side (27) plus a spare. Pins are 1.75 mm filament."),
    # ---- boat
    "boat_float_saddle": ("float_saddle", MINUS_Y_DOWN, 1, LOAD, None, "Standing on its end, no support."),
    "boat_thruster_mount": ("thruster_mount", MINUS_Y_DOWN, 1, LOAD, None,
                            "Lying on the flush side, no support."),
}
for _name in FAST_PARTS:
    _stl, _rot, _n, _extra, _bore, _note = PARTS[_name]
    _fast = {**_extra, **FAST}
    if "infill_sparse_density" in _extra and _extra["infill_sparse_density"] < FAST["infill_sparse_density"]:
        _fast["infill_sparse_density"] = _extra["infill_sparse_density"]    # never more infill
    PARTS[_name + "_fast"] = (_stl, _rot, _n, _fast, _bore, _note + " Fast profile (0.28 mm layers).")


def flatten(node, out):
    for key, v in node.items():
        if v.get("type") != "category":
            out.setdefault(key, {}).update({k: x for k, x in v.items() if k != "children"})
        if "children" in v:
            flatten(v["children"], out)


def load_definition(name, folder):
    d = json.loads((RES / folder / f"{name}.def.json").read_text(encoding="utf-8"))
    out = load_definition(d["inherits"], "definitions") if d.get("inherits") else {}
    flatten(d.get("settings", {}), out)
    for key, props in d.get("overrides", {}).items():
        out.setdefault(key, {}).update(props)
    return out


def inst_values(path):
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    cp.read(path, encoding="utf-8")
    return dict(cp["values"]) if cp.has_section("values") else {}


def material_values(name):
    ns = {"m": "http://www.ultimaker.com/material"}
    root = ET.parse(RES / "materials" / f"{name}.xml.fdm_material").getroot()
    names = {"print temperature": "default_material_print_temperature",
             "heated bed temperature": "default_material_bed_temperature",
             "standby temperature": "material_standby_temperature"}
    out = {"material_diameter": root.find("m:properties/m:diameter", ns).text}
    for s in root.findall("m:settings/m:setting", ns):
        if s.get("key") in names:
            out[names[s.get("key")]] = s.text
    return out


class Resolver:
    """Cura's setting stack, flattened for a single-extruder machine."""

    def __init__(self, overrides):
        self.defs = load_definition(MACHINE, "definitions")
        for key, props in load_definition(EXTRUDER, "extruders").items():
            self.defs.setdefault(key, {}).update(props)
        q = RES / "quality" / "creality" / "base"
        self.layers = [                                    # highest priority first
            {k: v for k, v in overrides.items()},
            inst_values(q / "base_0.4_PLA_standard.inst.cfg"),
            inst_values(q / "base_global_standard.inst.cfg"),
            material_values("generic_pla_175"),
            inst_values(RES / "variants" / f"{MACHINE}_0.4.inst.cfg"),
        ]
        self.cache, self.busy, self.problems = {}, set(), []

    def _typed(self, key, raw):
        t = self.defs[key].get("type")
        if not isinstance(raw, str):
            return raw
        if t == "float":
            return float(raw)
        if t == "int":
            return int(float(raw))
        if t == "bool":
            return raw.strip().lower() == "true"
        return raw

    def _eval(self, key, expr):
        names = {n.id for n in ast.walk(ast.parse(expr, mode="eval")) if isinstance(n, ast.Name)}
        env = {"math": math, "extruderValue": lambda _i, k: self.get(k),
               "extruderValues": lambda k: [self.get(k)], "resolveOrValue": self.get,
               "defaultExtruderPosition": lambda: "0"}
        env.update({n: self.get(n) for n in names if n in self.defs})
        return eval(expr, env)                             # noqa: S307 - Cura's own formulas

    def get(self, key):
        if key in self.cache:
            return self.cache[key]
        d = self.defs[key]
        if key in self.busy:                               # circular formula: fall back
            return d.get("default_value")
        self.busy.add(key)
        try:
            for layer in self.layers:
                if key in layer:
                    raw = layer[key]
                    val = (self._eval(key, raw[1:]) if isinstance(raw, str) and raw.startswith("=")
                           else self._typed(key, raw))
                    break
            else:
                v = d.get("value")
                val = (self._eval(key, v) if isinstance(v, str) else v) if v is not None \
                    else d.get("default_value")
        except Exception as e:                             # noqa: BLE001
            self.problems.append(f"{key}: {e}")
            val = d.get("default_value")
        finally:
            self.busy.discard(key)
        self.cache[key] = val
        return val

    def flat(self):
        out = {}
        for key, d in self.defs.items():
            if "default_value" not in d and "value" not in d:
                continue
            val, t = self.get(key), d.get("type")
            if t in ("extruder", "optional_extruder"):
                val = str(int(val))
            elif t == "float":
                val = float(val)
            elif t == "int":
                val = int(val)
            elif t == "bool":
                val = bool(val)
            elif isinstance(val, (list, tuple)):
                val = json.dumps(val)
            out[key] = val
        for code in ("machine_start_gcode", "machine_end_gcode"):   # Cura fills {setting} fields
            out[code] = re.sub(r"\{(\w+)\}", lambda m: str(out.get(m.group(1), m.group(0))), out[code])
        if "{" not in self.defs["machine_start_gcode"].get("default_value", ""):
            pass                                            # no temperature fields: engine heats first
        return out


def write_engine_json(values, path):
    children = {k: {"label": k, "description": k, "type": "str", "default_value": v}
                for k, v in values.items()}
    path.write_text(json.dumps({"name": "FERA resolved settings", "version": 2,
                                "settings": {"resolved": {"label": "resolved", "type": "category",
                                                          "description": "", "children": children}}}),
                    encoding="utf-8")


# --------------------------------------------------------------------------- meshes
REC = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])


def read_stl(path):
    b = path.read_bytes()
    n = struct.unpack("<I", b[80:84])[0]
    return np.frombuffer(b, dtype=REC, count=n, offset=84)["v"].astype(np.float64)


def write_stl(tris, path):
    rec = np.zeros(len(tris), dtype=REC)
    rec["v"] = tris
    e1, e2 = tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    n = np.cross(e1, e2)
    rec["n"] = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    path.write_bytes(b"\0" * 80 + struct.pack("<I", len(tris)) + rec.tobytes())


def cylinder(radius, height, cx, cy, n=48):
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    ring = np.stack([cx + radius * np.cos(a), cy + radius * np.sin(a)], axis=1)
    tris = []
    for i in range(n):
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % n]
        tris += [[(x1, y1, 0), (x2, y2, 0), (x2, y2, height)], [(x1, y1, 0), (x2, y2, height), (x1, y1, height)],
                 [(cx, cy, 0), (x2, y2, 0), (x1, y1, 0)], [(cx, cy, height), (x1, y1, height), (x2, y2, height)]]
    return np.array(tris, dtype=np.float64)


def prepare(stl, rotation, copies, bore, workdir, name):
    """Rotate into print orientation, sit on z = 0, centre on the bed; returns mesh paths."""
    tris = read_stl(STL_DIR / f"{stl}.stl") @ np.array(rotation, dtype=np.float64).T
    lo, hi = tris.reshape(-1, 3).min(0), tris.reshape(-1, 3).max(0)
    tris -= np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
    size = hi - lo
    # where the part's own origin (the tube axis) ended up, for the support-free bore
    axis = -np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2])
    gap = 14 if max(size[0], size[1]) > 25 else 7
    px, py = size[0] + gap, size[1] + gap
    fits = [c for c in range(1, copies + 1)
            if c * px <= 280 and math.ceil(copies / c) * py <= 280]
    assert fits, f"{name}: {copies} copies do not fit the bed"
    cols = min(fits, key=lambda c: abs(c * px - math.ceil(copies / c) * py))    # squarest layout
    rows = math.ceil(copies / cols)
    spots = [((c - (cols - 1) / 2) * px, (r - (rows - 1) / 2) * py)
             for r in range(rows) for c in range(cols)][:copies]
    body = np.concatenate([tris + np.array([x, y, 0.0]) for x, y in spots])
    paths = [workdir / f"{name}.stl"]
    write_stl(body, paths[0])
    if bore:
        radius, height = bore
        blocker = np.concatenate([cylinder(radius, height, x + axis[0], y + axis[1]) for x, y in spots])
        paths.append(workdir / f"{name}_nosupport.stl")
        write_stl(blocker, paths[1])
    return paths, size


# --------------------------------------------------------------------------- g-code checks
def inspect(gcode_path, bed):
    xs, ys, segs, temps = [], [], [], {}
    x = y = z = e = 0.0
    layers, zmax, absolute_e = 0, 0.0, True
    for line in gcode_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(";LAYER:"):
            layers += 1
        code = line.split(";", 1)[0].split()
        if not code:
            continue
        if code[0] in ("M104", "M109", "M140", "M190"):
            s = [c for c in code[1:] if c.startswith("S")]
            if s and float(s[0][1:]) > 0:
                temps[code[0]] = float(s[0][1:])
        elif code[0] == "M83":
            absolute_e = False
        elif code[0] == "G92":
            for c in code[1:]:
                if c.startswith("E"):
                    e = float(c[1:])
        elif code[0] in ("G0", "G1"):
            nx, ny, nz, ne = x, y, z, e
            for c in code[1:]:
                if c[0] == "X":
                    nx = float(c[1:])
                elif c[0] == "Y":
                    ny = float(c[1:])
                elif c[0] == "Z":
                    nz = float(c[1:])
                elif c[0] == "E":
                    ne = float(c[1:]) if absolute_e else e + float(c[1:])
            if ne > e + 1e-6 and (nx != x or ny != y) and layers:
                segs.append((x, y, nx, ny, nz))
                xs += [x, nx]
                ys += [y, ny]
                zmax = max(zmax, nz)
            x, y, z, e = nx, ny, nz, ne
    box = (min(xs), min(ys), max(xs), max(ys))
    inside = box[0] >= 0 and box[1] >= 0 and box[2] <= bed[0] and box[3] <= bed[1]
    return dict(layers=layers, height=round(zmax, 2), box=[round(v, 1) for v in box], inside=inside,
                temps=temps), segs


def picture(segs, box, zmax, path):
    """Top view of every extrusion, darker = lower; a quick look at orientation and support."""
    scale = min(900 / max(box[2] - box[0], 1), 900 / max(box[3] - box[1], 1), 12)
    w, h = int((box[2] - box[0]) * scale) + 20, int((box[3] - box[1]) * scale) + 20
    img = Image.new("RGB", (w, h), (20, 22, 28))
    d = ImageDraw.Draw(img)
    for x1, y1, x2, y2, z in segs[::max(len(segs) // 60000, 1)]:
        t = z / max(zmax, 1e-6)
        col = (int(60 + 195 * t), int(110 + 100 * t), int(230 - 150 * t))
        d.line([(10 + (x1 - box[0]) * scale, h - 10 - (y1 - box[1]) * scale),
                (10 + (x2 - box[0]) * scale, h - 10 - (y2 - box[1]) * scale)], fill=col)
    img.save(path)


# --------------------------------------------------------------------------- main
def slice_part(name):
    stl, rotation, copies, extra, bore, note = PARTS[name]
    work = OUT / "work"
    work.mkdir(parents=True, exist_ok=True)
    resolver = Resolver({**TUNED, **COMMON, **extra})
    values = resolver.flat()
    settings = work / f"{name}.settings.json"
    write_engine_json(values, settings)
    meshes, size = prepare(stl, rotation, copies, bore, work, name)
    out = OUT / f"{name}.gcode"
    cmd = [str(SLICER / "CuraEngine.exe"), "slice", "-v", "-j", str(settings), "-e0", "-j", str(settings),
           "-l", str(meshes[0])]
    if len(meshes) > 1:
        cmd += ["-l", str(meshes[1]), "-s", "anti_overhang_mesh=true"]
    cmd += ["-o", str(out)]
    run = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    log = run.stdout + run.stderr
    (work / f"{name}.log").write_text(log, encoding="utf-8")
    if run.returncode or not out.exists():
        raise SystemExit(f"{name}: CuraEngine failed, see {work / (name + '.log')}")
    seconds = float(re.search(r"Print time \(s\): (\d+)", log).group(1))
    volume = float(re.search(r"Filament \(mm\^3\): (\d+)", log).group(1))
    grams = volume / 1000 * 1.24
    info, segs = inspect(out, (values["machine_width"], values["machine_depth"]))
    picture(segs, info["box"], info["height"], work / f"{name}.png")
    header = (f"; FERA {name}: {note}\n"
              f"; {values['machine_name']}, {values['machine_nozzle_size']} mm nozzle, PLA, "
              f"{values['layer_height']} mm layers, {values['wall_line_count']} walls, "
              f"{values['infill_sparse_density']:.0f}% {values['infill_pattern']} infill, "
              f"support {'on (' + values['support_type'] + ')' if values['support_enable'] else 'off'}, "
              f"{values['adhesion_type']}\n"
              f"; nozzle {values['material_print_temperature']:.0f} C, bed "
              f"{values['material_bed_temperature']:.0f} C, flow {values['material_flow']:.0f}%\n"
              f"; engine estimate {seconds / 3600:.1f} h, {grams:.0f} g PLA\n")
    # In command-line mode the engine writes its header before it knows the numbers; the real
    # one is in its log. Printer screens read ;TIME from it, so put the real one in the file.
    real = re.search(r"Gcode header after slicing:\n(.*?)End of gcode header\.", log, re.S).group(1)
    body = out.read_text(encoding="utf-8", errors="replace")
    body = real.strip() + "\n\n" + body[body.index(";Generated with"):]
    out.write_text(header + body, encoding="utf-8", newline="\n")
    ok = bool(info["inside"] and info["temps"].get("M109") == values["material_print_temperature"]
          and info["temps"].get("M190") == values["material_bed_temperature"]
          and abs(info["height"] - size[2]) < 0.35)
    print(f"{name:14s} {size[0]:5.0f} x {size[1]:3.0f} x {size[2]:3.0f} mm  {info['layers']:4d} layers  "
          f"{seconds / 3600:5.1f} h  {grams:5.0f} g  bed area used x {info['box'][0]}..{info['box'][2]} "
          f"y {info['box'][1]}..{info['box'][3]}  temps {info['temps']}  {'ok' if ok else 'CHECK'}")
    for p in resolver.problems[:5]:
        print("   setting not resolved:", p)
    info["inside"] = bool(info["inside"])
    return dict(name=name, hours=seconds / 3600, grams=grams, ok=ok, note=note, **info)


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(PARTS)
    OUT.mkdir(parents=True, exist_ok=True)
    results = [slice_part(n) for n in wanted]
    (OUT / "work" / "summary.json").write_text(json.dumps(results, indent=1))
    sys.exit(0 if all(r["ok"] for r in results) else 1)
