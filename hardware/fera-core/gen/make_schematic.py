"""Generate the KiCad 8 schematic for FERA Core from design.py.

    python hardware/fera-core/gen/make_schematic.py            write the schematic
    python hardware/fera-core/gen/make_schematic.py --check    also run ERC and compare the
                                                               exported netlist with design.py

Output (next to the board file):
    fera-core.kicad_sch        root sheet: one box per page
    <section>.kicad_sch        one page per section() in design.py
    fera.kicad_sym             project symbols (IMU, barometer, XT30, shunt-free power symbols)

Every pin gets a short wire and a net label (power nets get a power symbol), so the
schematic is a faithful, ERC-checkable picture of the netlist rather than a hand-drawn one.
Symbols come from KiCad's own libraries wherever one exists, which is what lets
--check compare each net against the library's pin names.
"""
import collections
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import design as D  # noqa: E402
import ids  # noqa: E402
import mcu_pins  # noqa: E402

OUT = HERE.parent
SYMDIR = mcu_pins.KICAD_SHARE / "symbols"
CLI = r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe"
REV = "A (preliminary)"
G = 2.54                       # schematic grid
STUB = 2.54                    # wire length between a pin and its label
POWER_NETS = ["GND", "3V3", "5V", "VSYS", "VBAT", "3V3S", "3V3A", "3V3P"]
# Nets fed through an inductor, shunt, bead or connector: ERC needs to be told they are driven.
FLAG_NETS = ["GND", "VBAT_IN", "VBAT", "5V", "VSYS", "3V3", "3V3A", "USB_VBUS"]

# --------------------------------------------------------------------------- symbols to use
SYMBOLS = {
    "U1": "MCU_ST_STM32H7:STM32H743VITx", "U2": "fera:ICM-42688-P", "U3": "fera:DPS368",
    "U4": "Sensor_Energy:INA226", "U5": "Regulator_Switching:LMR33630ADDA",
    "U6": "Regulator_Switching:TLV62569DBV", "U7": "Regulator_Linear:LP5907MFX-3.3",
    "U8": "Power_Protection:USBLC6-2SC6",
    **{f"U{i}": "Power_Management:TPS2069CDBV" for i in (9, 10, 11, 12)},
    **{f"U{i}": "Power_Protection:USBLC6-4SC6" for i in (13, 14, 15, 16)},
    "U17": "Regulator_Linear:LP5907MFX-3.3", "Y1": "Device:Crystal_GND24", "R6": "Device:R_Shunt",
    "FB1": "Device:FerriteBead", "C20": "Device:C_Polarized", "D1": "Device:D_Schottky",
    "D5": "Device:D_Zener", "D6": "Device:D_Schottky", "D7": "Device:D_Zener",
    "C31": "Device:C_Polarized", "SW1": "Switch:SW_Push",
    "J9": "Connector_Generic:Conn_01x01", "J10": "Connector_Generic:Conn_01x01",
    "J11": "Connector:Micro_SD_Card_Det_Hirose_DM3AT",
    "J12": "Connector:USB_C_Receptacle_USB2.0_16P",
    "J13": "Connector:Conn_ARM_SWD_TagConnect_TC2030-NL",
    "J14": "Connector_Generic_MountingPin:Conn_01x06_MountingPin",
    "J15": "Connector_Generic_MountingPin:Conn_01x06_MountingPin",
    "J16": "Connector_Generic_MountingPin:Conn_01x06_MountingPin",
    "J17": "Connector_Generic_MountingPin:Conn_01x04_MountingPin",
    **{f"J{i}": "fera:XT30PW-F" for i in (1, 2, 3, 4)},
    **{f"J{i}": "Connector_Generic:Conn_02x04_Odd_Even" for i in (5, 6, 7, 8)},
}
BY_PREFIX = {"C": "Device:C", "R": "Device:R", "RN": "Device:R_Pack04", "L": "Device:L", "D": "Device:LED",
             "TP": "Connector:TestPoint", "H": "Mechanical:MountingHole_Pad"}
LEADERS = ("U", "J", "Y", "SW")           # parts that start a new block on the page

NOTES = {
    "mcu": "STM32H743VIT6. Pin allocation and the reasoning behind it: pinmap.md.\n"
           "Unused pins carry a no-connect flag; they are the spares listed in pinmap.md.",
    "sensors": "ICM-42688-P pin-out from TDK DS-000347 rev 1.2 (table 9): pin 7 must be grounded,\n"
               "pin 9 (INT2/FSYNC/CLKIN) is grounded because FSYNC is not used.\n"
               "Barometer: DPS368 (DPS310 successor), I2C address 0x76. Sensors run from the 3V3S LDO.",
    "power": "Battery current path: J9 -> R6 (0.2 mOhm shunt, Kelvin sense pads 2/3) -> VBAT plane -> ports.\n"
             "INA226 at I2C 0x40. D5 clamps spikes on VBAT. 5 V buck (LMR33630) feeds the ports' 5 V rail.\n"
             "VSYS = 5 V through D6 or USB through D1 (io page): feeds the 3.3 V buck (TLV62569), the sensor LDO\n"
             "and the GPS / TELEM / RC connectors, so USB never reaches the 5 V port rail or the battery side.\n"
             "No reverse-polarity protection on this revision.",
    "io": "USB-C is full-speed only (USB_D_P / USB_D_N), ESD-protected by U8. D1 and D6 diode-OR USB and 5 V into VSYS.\n"
          "J13 is a Tag-Connect TC2030 SWD footprint (no part fitted).",
    "ports": "Four identical FERA ports. XT30PW-F polarity per the Amass drawing: pad 1 = minus, pad 2 = plus\n"
             "(plus is the contact at the flat end of the housing). Rated 15 A continuous, 30 A momentary.\n"
             "Signal header pin order is a routing placeholder; the logical order is in docs/port-spec.md.\n"
             "Per port: TPS2069C switch (1.5 A, enable + fault to the MCU) for the module's 5 V, 100 ohm in series\n"
             "with S1-S3 and ID, 1 k in the shared telemetry line, USBLC6-4 clamp on the contact side.\n"
             "Port 3.3 V comes from its own current-limited LDO (3V3P, sensors page).",
}

# --------------------------------------------------------------------------- s-expressions
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\(|\)|[^\s()"]+')


def parse(text, start=0):
    """Parse the s-expression that starts at text[start]; atoms stay raw tokens."""
    stack = []
    for m in TOKEN.finditer(text, start):
        t = m.group()
        if t == "(":
            node = []
            if stack:
                stack[-1].append(node)
            stack.append(node)
        elif t == ")":
            done = stack.pop()
            if not stack:
                return done
        else:
            stack[-1].append(t)
    raise ValueError("unbalanced s-expression")


def q(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def unq(t):
    return t[1:-1].replace('\\"', '"').replace("\\\\", "\\") if t.startswith('"') else t


def dump(node, depth=1):
    if not isinstance(node, list):
        return node
    flat = "(" + " ".join(dump(c, 0) for c in node) + ")"
    if len(flat) <= 96 or not any(isinstance(c, list) for c in node):
        return flat
    pad = "\t" * depth
    head = [c for c in node if not isinstance(c, list)]
    rows = [pad + dump(c, depth + 1) for c in node if isinstance(c, list)]
    return "(" + " ".join(head) + "\n" + "\n".join(rows) + "\n" + "\t" * (depth - 1) + ")"


def child(node, head):
    return next((c for c in node if isinstance(c, list) and c and c[0] == head), None)


def num(v):
    v = round(float(v), 4)
    return str(int(v)) if v == int(v) else f"{v:.4f}".rstrip("0")


# --------------------------------------------------------------------------- symbol libraries
_libtext, _trees = {}, {}


def lib_tree(lib_id):
    """The (flattened) library definition of a symbol as a tree named by its bare name."""
    if lib_id in _trees:
        return _trees[lib_id]
    lib, name = lib_id.split(":")
    if lib == "fera":
        tree = FERA[name]
    else:
        if lib not in _libtext:
            _libtext[lib] = (SYMDIR / f"{lib}.kicad_sym").read_text(encoding="utf-8")
        text = _libtext[lib]
        m = re.search(r'^\t\(symbol ' + re.escape(q(name)) + r"\s", text, re.M)
        assert m, f"symbol not found: {lib_id}"
        tree = parse(text, m.start() + 1)
        ext = child(tree, "extends")
        if ext:                                   # derived symbol: body comes from its parent
            parent = lib_tree(f"{lib}:{unq(ext[1])}")
            pname = unq(parent[1])
            props = {unq(c[1]): c for c in parent if isinstance(c, list) and c[0] == "property"}
            props.update({unq(c[1]): c for c in tree if isinstance(c, list) and c[0] == "property"})
            flat = ["symbol", q(name)]
            flat += [c for c in parent[2:] if not isinstance(c, list) or c[0] not in ("property", "symbol")]
            flat += list(props.values())
            for c in parent:
                if isinstance(c, list) and c[0] == "symbol":
                    flat.append(["symbol", q(name + unq(c[1])[len(pname):])] + c[2:])
            tree = flat
    _trees[lib_id] = tree
    return tree


Pin = collections.namedtuple("Pin", "number name etype x y angle length hidden")


def lib_pins(lib_id):
    pins, units = [], set()
    tree = lib_tree(lib_id)
    for sub in tree:
        if not (isinstance(sub, list) and sub[0] == "symbol"):
            continue
        units.add(int(unq(sub[1]).rsplit("_", 2)[1]))
        for c in sub:
            if isinstance(c, list) and c[0] == "pin":
                at = child(c, "at")
                hide = child(c, "hide")
                pins.append(Pin(unq(child(c, "number")[1]), unq(child(c, "name")[1]), c[1],
                                float(at[1]), float(at[2]), int(float(at[3])) % 360,
                                float(child(c, "length")[1]),
                                "hide" in c or (hide is not None and hide[1] == "yes")))
    assert max(units) <= 1, f"{lib_id}: multi-unit symbols are not supported"
    return pins


def lib_prop(lib_id, name, default=""):
    for c in lib_tree(lib_id):
        if isinstance(c, list) and c[0] == "property" and unq(c[1]) == name:
            return unq(c[2])
    return default


# --------------------------------------------------------------------------- project symbols
def font(size=1.27, hide=False, justify=None):
    e = ["effects", ["font", ["size", num(size), num(size)]]]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append(["hide", "yes"])
    return e


def prop(name, value, x, y, angle=0, hide=False, justify=None, size=1.27):
    return ["property", q(name), q(value), ["at", num(x), num(y), num(angle)], font(size, hide, justify)]


def box_symbol(name, ref, descr, datasheet, left, right):
    """A plain rectangular symbol. left/right: lists of (number, pin name, electrical type)."""
    rows = max(len(left), len(right))
    longest = max(len(n) for _num, n, _t in left + right)
    w = max(10.16, G * round((2 * longest * 1.1 + 6) / G))
    h = G * (rows + 1)
    tree = ["symbol", q(name), ["pin_names", ["offset", "1.016"]], ["exclude_from_sim", "no"],
            ["in_bom", "yes"], ["on_board", "yes"],
            prop("Reference", ref, -w / 2, h / 2 + 1.27, justify="left"),
            prop("Value", name, -w / 2 + 6, h / 2 + 1.27, justify="left"),
            prop("Footprint", "", 0, 0, hide=True), prop("Datasheet", datasheet, 0, 0, hide=True),
            prop("Description", descr, 0, 0, hide=True),
            ["symbol", q(name + "_0_1"),
             ["rectangle", ["start", num(-w / 2), num(h / 2)], ["end", num(w / 2), num(-h / 2)],
              ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", "background"]]]]]
    body = ["symbol", q(name + "_1_1")]
    for side, pins in ((-1, left), (1, right)):
        for i, (number, pname, etype) in enumerate(pins):
            y = h / 2 - G * (i + 1)
            body.append(["pin", etype, "line",
                         ["at", num(side * (w / 2 + G)), num(y), "0" if side < 0 else "180"],
                         ["length", "2.54"], ["name", q(pname), font()], ["number", q(number), font()]])
    tree.append(body)
    return tree


def power_symbol(net):
    """Power symbol whose net name is its value. GND points down, rails point up."""
    gnd = net == "GND"
    art = ([["polyline", ["pts", ["xy", "0", "0"], ["xy", "0", "-1.27"], ["xy", "1.27", "-1.27"],
                          ["xy", "0", "-2.54"], ["xy", "-1.27", "-1.27"], ["xy", "0", "-1.27"]],
             ["stroke", ["width", "0"], ["type", "default"]], ["fill", ["type", "none"]]]] if gnd else
           [["polyline", ["pts", ["xy", "-0.762", "1.27"], ["xy", "0", "2.54"]],
             ["stroke", ["width", "0"], ["type", "default"]], ["fill", ["type", "none"]]],
            ["polyline", ["pts", ["xy", "0", "0"], ["xy", "0", "2.54"]],
             ["stroke", ["width", "0"], ["type", "default"]], ["fill", ["type", "none"]]],
            ["polyline", ["pts", ["xy", "0", "2.54"], ["xy", "0.762", "1.27"]],
             ["stroke", ["width", "0"], ["type", "default"]], ["fill", ["type", "none"]]]])
    return ["symbol", q(net), ["power"], ["pin_numbers", "hide"], ["pin_names", ["offset", "0"], "hide"],
            ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            prop("Reference", "#PWR", 0, -6.35 if gnd else -3.81, hide=True),
            prop("Value", net, 0, -3.81 if gnd else 3.556),
            prop("Footprint", "", 0, 0, hide=True), prop("Datasheet", "", 0, 0, hide=True),
            prop("Description", f'Power symbol, creates a global label with name "{net}"', 0, 0, hide=True),
            prop("ki_keywords", "global power", 0, 0, hide=True),
            ["symbol", q(net + "_0_1")] + art,
            ["symbol", q(net + "_1_1"),
             ["pin", "power_in", "line", ["at", "0", "0", "270" if gnd else "90"], ["length", "0"],
              ["name", q("~"), font()], ["number", q("1"), font()]]]]


FERA = {
    "ICM-42688-P": box_symbol(
        "ICM-42688-P", "U", "6-axis IMU, SPI, LGA-14. Pin-out: TDK DS-000347 rev 1.2 table 9.",
        "https://invensense.tdk.com/products/motion-tracking/6-axis/icm-42688-p/",
        [("8", "VDD", "power_in"), ("5", "VDDIO", "power_in"), ("13", "AP_SCLK", "input"),
         ("14", "AP_SDI", "input"), ("1", "AP_SDO", "output"), ("12", "AP_CS", "input"),
         ("4", "INT1", "output"), ("9", "INT2/FSYNC/CLKIN", "input")],
        [("6", "GND", "power_in"), ("7", "RESV_GND", "passive"), ("2", "RESV", "no_connect"),
         ("3", "RESV", "no_connect"), ("10", "RESV", "no_connect"), ("11", "RESV", "no_connect")]),
    "DPS368": box_symbol(
        "DPS368", "U", "Barometric pressure sensor, LGA-8 2.0 x 2.5 mm, pin-compatible with DPS310.",
        "https://www.infineon.com/cms/en/product/sensor/pressure-sensors/pressure-sensors-for-iot/dps368/",
        [("8", "VDD", "power_in"), ("6", "VDDIO", "power_in"), ("2", "CSB", "input"),
         ("4", "SCK/SCL", "input"), ("3", "SDI/SDA", "bidirectional")],
        [("1", "GND", "power_in"), ("7", "GND", "power_in"), ("5", "SDO/ADDR", "passive")]),
    "XT30PW-F": box_symbol(
        "XT30PW-F", "J", "Amass XT30PW-F board socket. Pad 1 is minus, pad 2 is plus (flat end).",
        "https://www.tme.eu/Document/f383737e340bfdab1f665284174b4ea2/XT30PW-F.pdf",
        [("2", "PLUS", "passive"), ("1", "MINUS", "passive")], []),
    **{net: power_symbol(net) for net in POWER_NETS},
}


def write_project_lib():
    body = "\n".join("\t" + dump(tree, 2) for tree in FERA.values())
    (OUT / "fera.kicad_sym").write_text(
        '(kicad_symbol_lib\n\t(version 20231120)\n\t(generator "fera-gen")\n\t(generator_version "8.0")\n'
        + body + "\n)\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------- placing parts
DIRS = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}       # lib angle -> screen vector


def text_len(s):
    return 1.05 * len(s or "")


class Item:
    """One symbol on a page, with everything attached to its pins."""

    def __init__(self, part, lib_id, netmap, pseudo=False):
        self.part, self.lib_id, self.pseudo = part, lib_id, pseudo
        self.ref = part["ref"]
        self.pins = lib_pins(lib_id)
        numbers = {p.number for p in self.pins}
        missing = set(netmap) - numbers
        assert not missing, f"{self.ref}: pins {sorted(missing)} are not in symbol {lib_id}"
        self.netmap = netmap
        self.leader = self.ref.startswith(LEADERS) and not pseudo
        two_pin = sorted(numbers) == ["1", "2"] and all(p.x == 0 for p in self.pins)
        self.text_above = not two_pin and not pseudo and len(self.pins) > 1
        # vertical two-pin parts: turn them so ground is at the bottom and rails at the top
        n1, n2 = netmap.get("1"), netmap.get("2")
        self.rot = 180 if two_pin and (n1 == "GND" or (n2 in POWER_NETS and n2 != "GND"
                                                        and n1 not in POWER_NETS)) else 0
        self.groups = self._groups()
        self._extents()
        self.x = self.y = 0.0

    def offset(self, px, py):
        s = -1 if self.rot == 180 else 1
        return (s * px, -s * py)

    def _groups(self):
        """Pins sharing a connection point are handled together (stacked power pins)."""
        by_pos = collections.OrderedDict()
        for p in self.pins:
            by_pos.setdefault(self.offset(p.x, p.y), []).append(p)
        groups = []
        for (ox, oy), pins in by_pos.items():
            nets = {self.netmap.get(p.number) for p in pins} - {None}
            assert len(nets) <= 1, f"{self.ref}: stacked pins {[p.number for p in pins]} on nets {nets}"
            p = pins[0]
            d = DIRS[(p.angle + 180 + self.rot) % 360]
            net = next(iter(nets), None)
            visible = any(not x.hidden for x in pins)
            nc_type = all(x.etype == "no_connect" for x in pins)
            kind = ("power" if net in POWER_NETS else "label") if net else \
                   ("nc" if visible and not nc_type else "none")
            groups.append(dict(ox=ox, oy=oy, d=d, net=net, kind=kind, pins=pins, prev=None,
                               base=(ox - d[0] * p.length, oy - d[1] * p.length)))
        # neighbouring pins on the same power net: one symbol, the rest join it with a wire
        runs = collections.defaultdict(list)
        for g in groups:
            if g["kind"] == "power":
                across = g["oy"] if g["d"][1] else g["ox"]
                runs[(g["net"], g["d"], round(across, 3))].append(g)
        for (_net, d, _a), run in runs.items():
            run.sort(key=lambda g: g["ox"] if d[1] else g["oy"])
            for a, b in zip(run, run[1:]):
                gap = (b["ox"] - a["ox"]) if d[1] else (b["oy"] - a["oy"])
                if gap <= 2 * G + 0.01:
                    b["kind"], b["prev"] = "bus", a
        return groups

    def _extents(self):
        xs, ys = [-G, G], [-G, G]
        for g in self.groups:
            reach = {"power": STUB + 4.2 + (text_len(g["net"]) if g["d"][0] else 2.2), "bus": STUB,
                     "label": STUB + 3.2 + text_len(g["net"] or ""), "nc": 1.3, "none": 0}[g["kind"]]
            for px, py in ((g["ox"] + g["d"][0] * reach, g["oy"] + g["d"][1] * reach), g["base"]):
                xs.append(px)
                ys.append(py)
            side = 1.6 if g["kind"] != "none" else 0
            if g["d"][0]:
                ys += [g["oy"] - side, g["oy"] + side]
            else:
                xs += [g["ox"] - side, g["ox"] + side]
        body_r = max(g["base"][0] for g in self.groups) if self.groups else G
        self.body_l = min(g["base"][0] for g in self.groups) if self.groups else -G
        if self.text_above:                      # reference and value on one line above everything
            self.text_y = min(ys) - 2.6
            ys.append(self.text_y - 2.2)
            xs.append(self.body_l + 1.35 * text_len(self.ref + "   " + self.part["value"]) + 2)
        else:
            xs.append(max(body_r, 1.3) + 1.6 + text_len(max(self.ref, self.part["value"], key=len)))
        self.left, self.right, self.top, self.bottom = -min(xs), max(xs), -min(ys), max(ys)
        self.w, self.h = self.left + self.right, self.top + self.bottom

    def place(self, x0, y0):
        """Put the item's bounding box corner at (x0, y0), origin snapped to the grid."""
        self.x = G * -(-(x0 + self.left) // G)
        self.y = G * -(-(y0 + self.top) // G)


PAPER = [("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594)]
MARGIN_L, MARGIN_T, MARGIN_R, MARGIN_B = 16, 42, 14, 46
GAP_X, GAP_Y = 9, 12


def layout(items):
    """Flow layout: each leader starts a block and its passives sit in rows beneath it."""
    blocks = []
    for it in items:
        if it.leader or not blocks:
            blocks.append([it])
            if it.leader and it.h > 110:          # a very tall part gets its column to itself
                blocks.append([])
        else:
            blocks[-1].append(it)
    blocks = [b for b in blocks if b]
    for paper, pw, ph in PAPER:
        x, y, col_w, ok = MARGIN_L, MARGIN_T, 0, True
        for block in blocks:
            lead, sats = (block[0], block[1:]) if block[0].leader else (None, block)
            wrap = max(lead.w if lead else 0, 105)
            rows, cur, cur_w = [], [], 0
            for s in sats:
                if cur and cur_w + s.w > wrap:
                    rows.append(cur)
                    cur, cur_w = [], 0
                cur.append(s)
                cur_w += s.w + 3
            if cur:
                rows.append(cur)
            bw = max([lead.w if lead else 0] + [sum(s.w + 3 for s in r) for r in rows])
            bh = (lead.h if lead else 0) + sum(max(s.h for s in r) + 5 for r in rows)
            if y > MARGIN_T and y + bh > ph - MARGIN_B:          # next column
                x, y, col_w = x + col_w + GAP_X, MARGIN_T, 0
            yy = y
            if lead:
                lead.place(x, yy)
                yy += lead.h + 5
            for r in rows:
                xx = x
                for s in r:
                    s.place(xx, yy)
                    xx += s.w + 3
                yy += max(s.h for s in r) + 5
            col_w = max(col_w, bw)
            ok = ok and x + col_w <= pw - MARGIN_R + 0.1 and y + bh <= ph - MARGIN_B + 0.1
            y += bh + GAP_Y
        if ok:
            return paper
    return PAPER[-1][0]


# --------------------------------------------------------------------------- writing a page
class Page:
    def __init__(self, key, title, number):
        self.key, self.title, self.number = key, title, number
        self.out, self.used, self.count = [], collections.OrderedDict(), collections.Counter()
        self.path = f"/{ids.ROOT}" if key == "root" else f"/{ids.ROOT}/{ids.sheet(key)}"

    def uid(self, *k):
        self.count[k[0]] += 1
        return ids.uid(self.key, *k, self.count[k[0]])

    def use(self, lib_id):
        if lib_id not in self.used:
            tree = list(lib_tree(lib_id))
            tree[1] = q(lib_id)
            self.used[lib_id] = tree

    def wire(self, a, b):
        self.out.append(f'(wire (pts (xy {num(a[0])} {num(a[1])}) (xy {num(b[0])} {num(b[1])})) '
                        f'(stroke (width 0) (type default)) (uuid {q(self.uid("wire"))}))')

    def text(self, s, x, y, size=1.5):
        self.out.append(f'(text {q(s)} (exclude_from_sim no) (at {num(x)} {num(y)} 0) '
                        f'(effects (font (size {num(size)} {num(size)})) (justify left top)) '
                        f'(uuid {q(self.uid("text"))}))')

    def label(self, net, x, y, d):
        angle = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[d]
        just = "left" if angle in (0, 90) else "right"
        self.out.append(
            f'(global_label {q(net)} (shape passive) (at {num(x)} {num(y)} {angle}) '
            f'(effects (font (size 1.27 1.27)) (justify {just})) (uuid {q(self.uid("label"))}) '
            f'(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at 0 0 0) '
            f'(effects (font (size 1.27 1.27)) (hide yes))))')

    def junction(self, x, y):
        self.out.append(f'(junction (at {num(x)} {num(y)}) (diameter 0) (color 0 0 0 0) '
                        f'(uuid {q(self.uid("junction"))}))')

    def no_connect(self, x, y):
        self.out.append(f'(no_connect (at {num(x)} {num(y)}) (uuid {q(self.uid("nc"))}))')

    def power(self, net, x, y, d):
        lib_id = f"fera:{net}"
        self.use(lib_id)
        up = {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}
        down = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}
        angle = (down if net == "GND" else up)[d]
        tip = 2.54
        if d[0]:                                  # sideways: text centred beyond the tip
            tx, ty, just = x + d[0] * (tip + 1.0 + text_len(net) / 2), y, None
        else:
            tx, ty, just = x, y + d[1] * (tip + 1.4), None
        text_angle = 90 if angle in (90, 270) else 0      # field angles are relative to the symbol
        ref = f"#PWR{next(PWR_COUNTER):04d}"
        uid = self.uid("pwr")
        self.out.append(dump(
            ["symbol", ["lib_id", q(lib_id)], ["at", num(x), num(y), str(angle)], ["unit", "1"],
             ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"], ["dnp", "no"],
             ["uuid", q(uid)],
             prop("Reference", ref, x, y, hide=True),
             prop("Value", net, tx, ty, angle=text_angle, justify=just),
             prop("Footprint", "", x, y, hide=True), prop("Datasheet", "", x, y, hide=True),
             prop("Description", "", x, y, hide=True),
             ["pin", q("1"), ["uuid", q(ids.uid(uid, "pin"))]],
             ["instances", ["project", q(ids.PROJECT),
                            ["path", q(self.path), ["reference", q(ref)], ["unit", "1"]]]]]))

    def symbol(self, it):
        p, x, y = it.part, it.x, it.y
        self.use(it.lib_id)
        uid = ids.uid("flag", it.ref) if it.pseudo else ids.symbol(it.ref)
        if it.pseudo:
            fields = [prop("Reference", it.ref, x, y, hide=True),
                      prop("Value", "PWR_FLAG", x, y - 4.6)]
        elif it.text_above:
            size = 1.6 if it.leader else 1.27
            fields = [prop("Reference", it.ref, x + it.body_l, y + it.text_y, justify="left", size=size),
                      prop("Value", p["value"], x + it.body_l + text_len(it.ref) * size / 1.27 + 2.5,
                           y + it.text_y, justify="left", size=size)]
        else:
            tx = x + max(1.3, max(g["base"][0] for g in it.groups)) + 1.5
            fields = [prop("Reference", it.ref, tx, y - 1.27, justify="left"),
                      prop("Value", p["value"], tx, y + 1.27, justify="left")]
        fields += [prop("Footprint", "" if it.pseudo else p["fp"], x, y, hide=True),
                   prop("Datasheet", lib_prop(it.lib_id, "Datasheet", "~"), x, y, hide=True),
                   prop("Description", lib_prop(it.lib_id, "Description"), x, y, hide=True)]
        if p.get("note"):
            fields.append(prop("Note", p["note"], x, y, hide=True))
        on_board = "no" if it.pseudo else "yes"
        in_bom = "yes" if p.get("bom", True) and not it.pseudo else "no"
        self.out.append(dump(
            ["symbol", ["lib_id", q(it.lib_id)], ["at", num(x), num(y), str(it.rot)], ["unit", "1"],
             ["exclude_from_sim", "no"], ["in_bom", in_bom], ["on_board", on_board], ["dnp", "no"],
             ["uuid", q(uid)]] + fields
            + [["pin", q(pin.number), ["uuid", q(ids.uid(uid, "pin", pin.number))]] for pin in it.pins]
            + [["instances", ["project", q(ids.PROJECT),
                              ["path", q(self.path), ["reference", q(it.ref)], ["unit", "1"]]]]]))
        for g in it.groups:
            px, py = x + g["ox"], y + g["oy"]
            ex, ey = px + g["d"][0] * STUB, py + g["d"][1] * STUB
            if g["kind"] == "nc":
                self.no_connect(px, py)
            elif g["kind"] == "bus":
                prev = g["prev"]
                qx, qy = x + prev["ox"] + prev["d"][0] * STUB, y + prev["oy"] + prev["d"][1] * STUB
                self.wire((px, py), (ex, ey))
                self.wire((qx, qy), (ex, ey))
                if prev["kind"] == "bus":
                    self.junction(qx, qy)
            elif g["kind"] in ("power", "label"):
                self.wire((px, py), (ex, ey))
                (self.power if g["kind"] == "power" else self.label)(g["net"], ex, ey, g["d"])

    def sheet_box(self, key, title, page, x, y, w=70, h=22):
        uid = ids.sheet(key)
        self.out.append(
            f'(sheet (at {num(x)} {num(y)}) (size {w} {h}) (fields_autoplaced yes) '
            f'(stroke (width 0.1524) (type solid)) (fill (color 255 255 225 1.0)) (uuid {q(uid)}) '
            f'(property "Sheetname" {q(title)} (at {num(x)} {num(y - 0.8)} 0) '
            f'(effects (font (size 1.6 1.6)) (justify left bottom))) '
            f'(property "Sheetfile" {q(key + ".kicad_sch")} (at {num(x)} {num(y + h + 0.8)} 0) '
            f'(effects (font (size 1.27 1.27)) (justify left top))) '
            f'(instances (project {q(ids.PROJECT)} (path {q("/" + ids.ROOT)} (page {q(str(page))})))))')

    def write(self, paper, file_uuid, pages=None):
        libs = "\n".join("\t\t" + dump(t, 3) for t in self.used.values())
        body = "\n".join("\t" + s for s in self.out)
        date = datetime.date.today().isoformat()
        tail = ""
        if pages:
            inst = " ".join(f'(path {q(path)} (page {q(str(n))}))' for path, n in pages)
            tail = f"\t(sheet_instances {inst})\n"
        name = "fera-core" if self.key == "root" else self.key
        (OUT / f"{name}.kicad_sch").write_text(
            f'(kicad_sch\n\t(version 20231120)\n\t(generator "fera-gen")\n\t(generator_version "8.0")\n'
            f'\t(uuid {q(file_uuid)})\n\t(paper {q(paper)})\n'
            f'\t(title_block (title {q("FERA Core - " + self.title)}) (date {q(date)}) (rev {q(REV)}) '
            f'(company "The Modular Drone Co") '
            f'(comment 1 "Generated from gen/design.py by gen/make_schematic.py - edit design.py, not this file"))\n'
            f'\t(lib_symbols\n{libs}\n\t)\n{body}\n{tail})\n', encoding="utf-8", newline="\n")


PWR_COUNTER = iter(range(1, 100000))


def symbol_for(p):
    if p["ref"] in SYMBOLS:
        return SYMBOLS[p["ref"]]
    return BY_PREFIX[re.match(r"[A-Z]+", p["ref"]).group()]


def generate():
    write_project_lib()
    pages = [("/", 1)]
    root = Page("root", "Overview", 1)
    for n, (key, title) in enumerate(D.SECTIONS, start=2):
        page = Page(key, title, n)
        items = [Item(p, symbol_for(p), mcu_pins.part_nets(D, p)) for p in D.PARTS if p["section"] == key]
        for i, net in enumerate(FLAG_NETS, start=1):     # on the first page that uses the net
            home = next(p["section"] for p in D.PARTS if net in mcu_pins.part_nets(D, p).values())
            if home == key:
                items.append(Item(dict(ref=f"#FLG{i:02d}", value="PWR_FLAG", note=""),
                                  "power:PWR_FLAG", {"1": net}, pseudo=True))
        paper = layout(items)
        page.text(title, MARGIN_L, 12, size=4)
        page.text(NOTES.get(key, ""), MARGIN_L, 21, size=1.7)
        for it in items:
            page.symbol(it)
        page.write(paper, ids.uid("file", key))
        root.sheet_box(key, title, n, 30 + 82 * ((n - 2) % 3), 72 + 42 * ((n - 2) // 3))
        pages.append((f"/{ids.sheet(key)}", n))
        print(f"  page {n}: {key:8s} {len(items):3d} symbols on {paper}")
    root.text("FERA Core rev A", 30, 20, size=6)
    root.text("Flight controller and power distribution board of the FERA modular vehicle hub.\n"
              "STM32H743 + ICM-42688-P + DPS368, 4S battery input with current sense, four identical module ports.\n"
              "Each box below is one page. Nets are joined by name: every pin carries a label or a power symbol.",
              30, 34, size=2.2)
    root.text("Generated from hardware/fera-core/gen/design.py, the same file the\n"
              "board is built from, and checked against it (gen/make_schematic.py --check).\n"
              "Footprints on the board carry the UUIDs of these symbols, so\n"
              "'Update PCB from Schematic' matches them directly.",
              30, 158, size=1.8)
    root.write("A4", ids.ROOT, pages)


# --------------------------------------------------------------------------- checks
SUSPECT = [  # (pin-name pattern, the net must match this pattern)
    (r"^(GND|VSS|VSSA|PGND|AGND|EP|MINUS|SHIELD|SHLD)$", r"^GND$"),
    (r"^(VDD|VDDIO|VDDA|VREF\+|VBAT|VS|VIN|IN|PLUS|VBUS|VCC)$", r"^(3V3|3V3A|3V3S|5V|VSYS|VBAT|USB_VBUS|BUCK_VCC)$"),
    (r"^OUT$", r"^(P\d_5V|3V3S|3V3P)$"),
]


def design_netlist():
    out = {}
    for p in D.PARTS:
        for number, net in mcu_pins.part_nets(D, p).items():
            out[(p["ref"], number)] = net
    return out


def pin_report():
    """Net against library pin name for every IC and connector; flags obvious mismatches."""
    lines, bad = [], []
    for p in D.PARTS:
        lib_id = symbol_for(p)
        if not p["ref"].startswith(("U", "J", "Y", "SW", "D", "R6")):
            continue
        netmap = mcu_pins.part_nets(D, p)
        lines.append(f"{p['ref']}  {p['value']}  [{lib_id}]")
        for pin in sorted(lib_pins(lib_id), key=lambda x: (len(x.number), x.number)):
            net = netmap.get(pin.number)
            flag = ""
            for name_rx, net_rx in SUSPECT:
                if re.match(name_rx, pin.name) and net and not re.match(net_rx, net):
                    flag = "   <-- check"
                    bad.append(f"{p['ref']}.{pin.number} ({pin.name}) on {net}")
                if re.match(name_rx, pin.name) and not net and pin.etype != "no_connect":
                    flag = "   <-- unconnected supply pin"
                    bad.append(f"{p['ref']}.{pin.number} ({pin.name}) unconnected")
            lines.append(f"    {pin.number:>4}  {pin.name:<28} {pin.etype:<14} {net or '-'}{flag}")
    (HERE / "pin_check.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bad


def check():
    ok = True
    bad = mcu_pins.check_functions(D)
    print(f"MCU alternate functions: {len(D.MCU_FUNCS) - len(bad)} of {len(D.MCU_FUNCS)} found on their pins")
    for b in bad:
        print("   ", b)
    suspects = pin_report()
    print(f"pin names against nets: {len(suspects)} to look at (full table in gen/pin_check.txt)")
    for s in suspects:
        print("   ", s)

    sch = OUT / "fera-core.kicad_sch"
    net_file, erc_file = HERE / "schematic.net", HERE / "erc.json"
    subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(net_file),
                    str(sch)], check=True, capture_output=True)
    text = net_file.read_text(encoding="utf-8")
    tree = parse(text, text.index("(export"))
    got = {}
    for net in child(tree, "nets")[1:]:
        name = unq(child(net, "name")[1]).lstrip("/")
        for node in net:
            if isinstance(node, list) and node[0] == "node":
                got[(unq(child(node, "ref")[1]), unq(child(node, "pin")[1]))] = name
    want = design_netlist()
    diffs = []
    for key in sorted(set(got) | set(want)):
        g, w = got.get(key), want.get(key)
        if g != w and not (w is None and g and g.startswith("unconnected-")):
            diffs.append(f"{key[0]}.{key[1]}: schematic {g}, design {w}")
    print(f"netlist: {len(want)} pin-to-net assignments in design.py, {len(diffs)} differ in the schematic")
    for d in diffs[:40]:
        print("   ", d)
    ok = ok and not diffs and not bad

    subprocess.run([CLI, "sch", "erc", "--format", "json", "--severity-all", "-o", str(erc_file),
                    str(sch)], check=True, capture_output=True)
    erc = json.loads(erc_file.read_text(encoding="utf-8"))
    counts = collections.Counter()
    samples = collections.defaultdict(list)
    for sheet in erc.get("sheets", []):
        for v in sheet.get("violations", []):
            counts[(v["severity"], v["type"])] += 1
            if len(samples[v["type"]]) < 4:
                samples[v["type"]].append(v["description"] + " | "
                                          + "; ".join(i["description"] for i in v["items"]))
    print(f"ERC: {sum(n for (s, _t), n in counts.items() if s == 'error')} errors, "
          f"{sum(n for (s, _t), n in counts.items() if s == 'warning')} warnings")
    for (sev, typ), n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {sev:8s} {typ}")
        if "-v" in sys.argv:
            for s in samples[typ]:
                print("          ", s[:230])
    plots = OUT / "plots"
    plots.mkdir(exist_ok=True)
    subprocess.run([CLI, "sch", "export", "pdf", "-o", str(plots / "schematic.pdf"), str(sch)],
                   check=False, capture_output=True)
    print(f"schematic PDF: {plots / 'schematic.pdf'}")
    return ok


if __name__ == "__main__":
    generate()
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
