"""Run KiCad's DRC on the generated board (including schematic parity) and print a summary,
then report the routed length of the critical signals and the trace impedance.

    python check_board.py [-v]           (any Python 3)
"""
import collections
import json
import math
import subprocess
import sys
from pathlib import Path

CLI = r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe"
HERE = Path(__file__).parent
BOARD = HERE.parent / "fera-core.kicad_pcb"
REPORT = HERE / "drc.json"
sys.path.insert(0, str(HERE))
import design as D  # noqa: E402

# signal groups whose routed length matters, with the fastest edge/bit rate they carry
GROUPS = [
    ("USB full speed (12 Mbit/s)", ["USB_D_P", "USB_D_N"]),
    ("USB connector side", ["USB_CONN_D_P", "USB_CONN_D_N"]),
    ("IMU SPI4 (up to 24 MHz)", ["IMU_SCK", "IMU_MOSI", "IMU_MISO", "IMU_CS", "IMU_DRDY"]),
    ("microSD SDMMC1 (up to 50 MHz)", ["SD_CK", "SD_CMD", "SD_D0", "SD_D1", "SD_D2", "SD_D3"]),
    ("Crystal 16 MHz", ["OSC_IN", "OSC_OUT"]),
    ("Current sense pair", ["ISNS_P", "ISNS_N"]),
]


def microstrip(w, h, t, er):
    """Characteristic impedance of a surface trace over a plane (Hammerstad / IPC-2141)."""
    we = w + t / math.pi * (1 + math.log(2 * h / t))          # effective width for thickness
    u = we / h
    eeff = (er + 1) / 2 + (er - 1) / 2 / math.sqrt(1 + 12 / u)
    if u <= 1:
        z0 = 60 / math.sqrt(eeff) * math.log(8 / u + u / 4)
    else:
        z0 = 120 * math.pi / (math.sqrt(eeff) * (u + 1.393 + 0.667 * math.log(u + 1.444)))
    return z0, eeff


def signal_report():
    path = HERE / "route_report.json"
    if not path.exists():
        return
    nets = json.loads(path.read_text()).get("nets", {})
    h = D.DIELECTRIC_MM[0][1]
    z0, eeff = microstrip(D.TRACK, h, D.COPPER_MM["F.Cu"], D.EPSILON_R)
    gap = D.NETCLASSES["USB"]["dp_gap"]
    zdiff = 2 * z0 * (1 - 0.48 * math.exp(-0.96 * gap / h))
    delay = math.sqrt(eeff) / 0.2998                           # ps per mm
    print(f"\nSignals (outer layers, {D.TRACK} mm track over {h} mm prepreg, er {D.EPSILON_R}):")
    print(f"  single-ended about {z0:.0f} ohm, {delay:.1f} ps/mm; a {D.TRACK}/{gap} mm pair about {zdiff:.0f} ohm")
    lines = []
    for title, names in GROUPS:
        rows = [(n, nets[n]) for n in names if n in nets]
        if not rows:
            continue
        lengths = [r["length"] for _n, r in rows]
        skew = max(lengths) - min(lengths)
        print(f"  {title}")
        for n, r in rows:
            state = "" if r["complete"] else "  INCOMPLETE"
            print(f"    {n:14s} {r['length']:6.1f} mm  {r['vias']} vias{state}")
        print(f"    longest {max(lengths):.1f} mm = {max(lengths) * delay / 1000:.2f} ns, "
              f"spread {skew:.1f} mm = {skew * delay:.0f} ps")
        lines.append((title, max(lengths), skew, sum(r["vias"] for _n, r in rows)))
    (HERE / "signal_report.json").write_text(json.dumps(
        dict(z0=round(z0, 1), zdiff=round(zdiff, 1), ps_per_mm=round(delay, 2),
             groups=[dict(group=t, longest_mm=l, spread_mm=round(s, 2), vias=v) for t, l, s, v in lines]),
        indent=1))


def main():
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "--severity-all", "--all-track-errors",
                    "--schematic-parity", "-o", str(REPORT), str(BOARD)], check=True, capture_output=True)
    data = json.loads(REPORT.read_text(encoding="utf-8"))
    violations = data.get("violations", [])
    unconnected = data.get("unconnected_items", [])
    parity = data.get("schematic_parity", [])
    by_type = collections.Counter((v["severity"], v["type"]) for v in violations)
    print(f"DRC: {len(violations)} violations, {len(unconnected)} unconnected items, "
          f"{len(parity)} schematic parity issues")
    for (sev, typ), n in sorted(by_type.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}  {sev:8s} {typ}")
    if "-v" in sys.argv:
        for v in violations:
            if v["severity"] == "error":
                where = v["items"][0].get("pos", {})
                print(f"  {v['type']}: {v['description']} @ ({where.get('x')}, {where.get('y')}) "
                      + " | ".join(i["description"] for i in v["items"]))
    for p in parity[:15]:
        print(f"  parity: {p['description']} | " + "; ".join(i["description"] for i in p["items"])[:160])
    nets = collections.Counter()
    for u in unconnected:
        for item in u["items"][:1]:
            d = item["description"]
            nets[d[d.find("["):d.find("]") + 1]] += 1
    for net, n in nets.most_common(40):
        print(f"  unconnected {n:3d}  {net}")
    signal_report()
    out = HERE.parent / "plots"
    out.mkdir(exist_ok=True)
    for name, layers in (("top", "F.Cu,F.SilkS,Edge.Cuts"), ("bottom", "B.Cu,B.SilkS,Edge.Cuts"),
                         ("gnd-plane", "In1.Cu,Edge.Cuts"), ("vbat-plane", "In3.Cu,Edge.Cuts"),
                         ("placement", "F.Fab,F.CrtYd,B.Fab,Edge.Cuts")):
        subprocess.run([CLI, "pcb", "export", "pdf", "--layers", layers, "-o",
                        str(out / f"{name}.pdf"), str(BOARD)], check=False, capture_output=True)
    print(f"\nplots: {out}")


if __name__ == "__main__":
    main()
