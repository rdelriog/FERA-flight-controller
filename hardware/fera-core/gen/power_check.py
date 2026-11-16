"""DC current calculation for the battery path of the generated board.

    "C:/Program Files/KiCad/8.0/bin/python.exe" gen/build_board.py --dump-copper
    cad/.venv/Scripts/python gen/power_check.py

Reads the filled copper KiCad produced (gen/copper.json) and solves the resistor network
of the real geometry on a 0.2 mm grid:

  plus side : BAT+ pad -> top pour -> shunt -> top/bottom pours -> via field -> VBAT plane
              -> the "+" pad of each port connector
  minus side: the "-" pad of each port connector -> GND plane -> BAT- pad

The outer-layer ground fills are left out of the minus side, so that number is pessimistic.
Writes power_report.json and plots/power_density.png.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import design as D  # noqa: E402

H = 0.2                      # grid pitch, mm
SS = 4                       # supersampling when rasterising
RHO = 1.72e-5                # copper resistivity, ohm.mm (20 C)
TEMP_FACTOR = 1.2            # copper at roughly 70 C
PLATING = 0.020              # via barrel plating, mm
SHUNT = 0.0002               # ohm
CONTACT = 0.0008             # ohm, one XT30 contact (Amass spec)
BIG = 1e6                    # siemens: ties the cells of one pad together

xs = [p[0] for p in D.OUTLINE]
ys = [p[1] for p in D.OUTLINE]
X0, Y0 = min(xs) - 1.0, min(ys) - 1.0
NX = int(math.ceil((max(xs) + 1.0 - X0) / H))
NY = int(math.ceil((max(ys) + 1.0 - Y0) / H))

LAYERS = ["F", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B"]
THICK = {"F": D.COPPER_MM["F.Cu"], "B": D.COPPER_MM["B.Cu"], **{k: v for k, v in D.COPPER_MM.items()}}


def depth(layer):
    """Distance from the top copper surface down to this layer, mm."""
    z, order = 0.0, ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
    name = {"F": "F.Cu", "B": "B.Cu"}.get(layer, layer)
    for i, n in enumerate(order):
        if n == name:
            return z
        z += D.COPPER_MM[n] + D.DIELECTRIC_MM[i][1]
    raise KeyError(layer)


def raster(polys):
    """Coverage (0..1) of each grid cell by a list of polygons-with-holes."""
    img = Image.new("L", (NX * SS, NY * SS), 0)
    d = ImageDraw.Draw(img)
    for rings in polys:
        for k, ring in enumerate(rings):
            pts = [((x - X0) / H * SS, (y - Y0) / H * SS) for x, y in ring]
            if len(pts) >= 3:
                d.polygon(pts, fill=255 if k == 0 else 0)
    a = np.asarray(img, dtype=np.float32) / 255.0
    return a.reshape(NY, SS, NX, SS).mean(axis=(1, 3))


def pad_cells(p, shrink=0.0):
    """Grid cells inside a pad (rectangle or circle for through-hole pads)."""
    a = math.radians(p["rot"])
    c, s = math.cos(a), math.sin(a)
    r = math.hypot(p["sx"], p["sy"]) / 2 + H
    out = []
    for iy in range(int((p["y"] - r - Y0) / H), int((p["y"] + r - Y0) / H) + 1):
        for ix in range(int((p["x"] - r - X0) / H), int((p["x"] + r - X0) / H) + 1):
            wx, wy = X0 + (ix + 0.5) * H - p["x"], Y0 + (iy + 0.5) * H - p["y"]
            lx, ly = wx * c - wy * s, wx * s + wy * c
            if abs(lx) <= p["sx"] / 2 - shrink and abs(ly) <= p["sy"] / 2 - shrink:
                out.append((iy, ix))
    return out


class Network:
    def __init__(self):
        self.index, self.rows, self.cols, self.vals = {}, [], [], []
        self.links = []                      # (a, b, g, tag, where)

    def node(self, key):
        if key not in self.index:
            self.index[key] = len(self.index)
        return self.index[key]

    def link(self, a, b, g, tag, where=None):
        self.links.append((self.node(a), self.node(b), g, tag, where))

    def add_layer(self, layer, cover, net):
        """In-plane conductances between neighbouring copper cells of one filled layer."""
        g_sheet = THICK[layer] / (RHO * TEMP_FACTOR)            # siemens per square
        mask = cover > 0.5
        for iy, ix in zip(*np.nonzero(mask)):
            self.node((net, layer, int(iy), int(ix)))
        for dy, dx in ((0, 1), (1, 0)):
            a = mask[:NY - dy, :NX - dx] & mask[dy:, dx:]
            g = g_sheet * np.minimum(cover[:NY - dy, :NX - dx], cover[dy:, dx:])
            for iy, ix in zip(*np.nonzero(a)):
                iy, ix = int(iy), int(ix)
                self.link((net, layer, iy, ix), (net, layer, iy + dy, ix + dx), float(g[iy, ix]),
                          layer, (iy, ix, dy, dx))
        return mask

    def solve(self, inject, ground):
        n = len(self.index)
        a = np.array([l[0] for l in self.links])
        b = np.array([l[1] for l in self.links])
        g = np.array([l[2] for l in self.links])
        m = coo_matrix((np.concatenate([g, g, -g, -g]),
                        (np.concatenate([a, b, a, b]), np.concatenate([a, b, b, a]))), shape=(n, n)).tocsr()
        rhs = np.zeros(n)
        for key, amps in inject.items():
            rhs[self.index[key]] += amps
        keep = np.ones(n, dtype=bool)
        keep[self.index[ground]] = False
        used = np.zeros(n, dtype=bool)          # drop copper islands that carry nothing
        used[a] = used[b] = True
        keep &= used
        v = np.zeros(n)
        v[keep] = spsolve(m[keep][:, keep].tocsc(), rhs[keep])
        return v, a, b, g


def cell(x, y):
    return int((y - Y0) / H), int((x - X0) / H)


def build(copper, system):
    """system = 'plus' (VBAT_IN and VBAT) or 'minus' (GND plane only)."""
    net = Network()
    masks = {}
    for z in copper["zones"]:
        if system == "plus" and z["net"] in ("VBAT", "VBAT_IN"):
            masks[(z["net"], z["layer"])] = net.add_layer(z["layer"], raster(z["polys"]), z["net"])
        if system == "minus" and z["net"] == "GND" and z["layer"] == "In1.Cu":
            masks[(z["net"], z["layer"])] = net.add_layer(z["layer"], raster(z["polys"]), z["net"])

    def has(n, layer, iy, ix):
        m = masks.get((n, layer))
        return m is not None and 0 <= iy < NY and 0 <= ix < NX and m[iy, ix]

    nvias = 0
    if system == "plus":
        for v in copper["vias"]:
            if v["net"] not in ("VBAT", "VBAT_IN"):
                continue
            iy, ix = cell(v["x"], v["y"])
            present = [l for l in ("F", "In3.Cu", "B") if has(v["net"], l, iy, ix)]
            area = math.pi * (v["drill"] * PLATING - PLATING ** 2)
            for l1, l2 in zip(present, present[1:]):
                length = depth(l2) - depth(l1)
                net.link((v["net"], l1, iy, ix), (v["net"], l2, iy, ix),
                         area / (RHO * TEMP_FACTOR * length), "via", (v["x"], v["y"], v["drill"]))
            nvias += len(present) > 1 and v["net"] == "VBAT"
    terminals = {}
    for p in copper["pads"]:
        name = f"{p['ref']}.{p['num']}"
        if system == "plus":
            layers = (["F", "In3.Cu", "B"] if p["tht"] else ["F"]) if p["net"] in ("VBAT", "VBAT_IN") else None
            wanted = p["ref"] in ("J9", "R6") or (p["tht"] and p["ref"] in ("J1", "J2", "J3", "J4"))
        else:
            layers = ["In1.Cu"] if p["net"] == "GND" and p["tht"] else None
            wanted = p["ref"] in ("J10", "J1", "J2", "J3", "J4")
        if not layers or not wanted:
            continue
        cells = pad_cells(p)
        n = 0
        for layer in layers:
            for iy, ix in cells:
                if has(p["net"], layer, iy, ix):
                    net.link(("pad", name), (p["net"], layer, iy, ix), BIG, "tie")
                    n += 1
        if n:
            terminals[name] = ("pad", name)
    if system == "plus":
        net.link(("pad", "R6.1"), ("pad", "R6.4"), 1 / SHUNT, "shunt")
    return net, terminals, masks, nvias


def run(copper, amps_per_port):
    report = {"amps_per_port": amps_per_port, "total_amps": 4 * amps_per_port}
    density = np.zeros((NY, NX))
    for system in ("plus", "minus"):
        net, term, masks, nvias = build(copper, system)
        ports = [f"J{i}.{'2' if system == 'plus' else '1'}" for i in (1, 2, 3, 4)]
        battery = "J9.1" if system == "plus" else "J10.1"
        missing = [t for t in ports + [battery] if t not in term]
        assert not missing, f"{system}: terminals not found in copper: {missing}"
        sign = 1 if system == "plus" else -1
        inject = {term[p]: -sign * amps_per_port for p in ports}
        v, a, b, g = net.solve(inject, term[battery])
        dv = v[a] - v[b]
        power = g * dv ** 2
        amps = g * np.abs(dv)
        tags = np.array([l[3] for l in net.links])
        by = {t: float(power[tags == t].sum()) for t in sorted(set(tags)) if t != "tie"}
        sec = {"watts": {k: round(x, 3) for k, x in by.items()}, "watts_total": round(sum(by.values()), 3),
               "drop_mV": {p.split(".")[0]: round(1000 * abs(v[net.index[term[p]]]), 2) for p in ports}}
        if system == "plus":
            via_amps = amps[tags == "via"]
            sec["via_field"] = dict(vias=nvias, max_amps=round(float(via_amps.max()), 2),
                                    mean_amps=round(4 * amps_per_port / max(nvias, 1), 2))
        # current density per cell (A per mm of width -> A/mm2), ignoring the pad ties
        peak = 0.0
        for (na, nb, gg, tag, where), i_link in zip(net.links, amps):
            if tag in ("tie", "via", "shunt"):
                continue
            iy, ix, dy, dx = where
            j = i_link / (H * THICK[tag])
            density[iy, ix] = max(density[iy, ix], j)
            peak = max(peak, j)
        sec["peak_A_per_mm2"] = round(peak, 1)
        report[system] = sec
    contact = 8 * amps_per_port ** 2 * CONTACT
    board = report["plus"]["watts_total"] + report["minus"]["watts_total"]
    report["connector_contacts_W"] = round(contact, 2)
    report["board_copper_and_shunt_W"] = round(board, 2)
    report["worst_port_loop_mohm"] = round(
        max(report["plus"]["drop_mV"][p] + report["minus"]["drop_mV"][p] for p in report["plus"]["drop_mV"])
        / amps_per_port, 3)
    return report, density


def picture(density, name):
    top = max(float(np.percentile(density[density > 0], 99.7)), 1e-6)
    t = np.clip(density / top, 0, 1)
    rgb = np.zeros((NY, NX, 3), dtype=np.uint8)
    rgb[..., 0] = (255 * np.clip(2 * t, 0, 1)).astype(np.uint8)
    rgb[..., 1] = (255 * np.clip(2 - 2 * t, 0, 1) * (density > 0)).astype(np.uint8)
    rgb[..., 2] = (60 * (density > 0)).astype(np.uint8)
    img = Image.fromarray(rgb).resize((NX * 3, NY * 3), Image.NEAREST)
    d = ImageDraw.Draw(img)
    d.line([((x - X0) / H * 3, (y - Y0) / H * 3) for x, y in D.OUTLINE + D.OUTLINE[:1]], fill=(230, 230, 120))
    d.text((8, 8), f"current density, worst layer per cell; red = {top:.0f} A/mm2 or more", fill=(255, 255, 255))
    out = HERE.parent / "plots" / name
    out.parent.mkdir(exist_ok=True)
    img.save(out)
    return out


def main():
    copper = json.loads((HERE / "copper.json").read_text())
    results = {}
    for label, amps in (("continuous", 15.0), ("burst", 30.0)):
        rep, density = run(copper, amps)
        results[label] = rep
        print(f"--- {label}: {amps:.0f} A per port, {4 * amps:.0f} A total")
        for system in ("plus", "minus"):
            s = rep[system]
            print(f"  {system:5s} side: {s['watts_total']:.2f} W  {s['watts']}")
            print(f"          drop to ports (mV): {s['drop_mV']}   peak density {s['peak_A_per_mm2']} A/mm2")
        print(f"  via field: {rep['plus']['via_field']}")
        print(f"  board copper + shunt: {rep['board_copper_and_shunt_W']} W,"
              f" connector contacts: {rep['connector_contacts_W']} W,"
              f" worst port loop: {rep['worst_port_loop_mohm']} mOhm")
        if label == "continuous":
            print("  picture:", picture(density, "power_density.png"))
    (HERE / "power_report.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
