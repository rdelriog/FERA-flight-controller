"""Generate hardware/fera-core/fera-core.kicad_pcb from design.py.

Run with KiCad's own Python:
    "C:\\Program Files\\KiCad\\8.0\\bin\\python.exe" build_board.py [--no-route]
"""
import json
import subprocess
import sys
import time
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
import design as D  # noqa: E402
import ids  # noqa: E402
import mcu_pins  # noqa: E402
import router as R  # noqa: E402

FP_DIR = Path(r"C:\Program Files\KiCad\8.0\share\kicad\footprints")
OUT = Path(__file__).parent.parent / "fera-core.kicad_pcb"
PROJECT_LIBS = {"fera": OUT.parent / "fera.pretty"}        # footprints that live in this repo
CX, CY = 100.0, 100.0          # board centre in KiCad page coordinates
mm = pcbnew.FromMM


def pt(x, y):
    return pcbnew.VECTOR2I(mm(CX + x), mm(CY + y))


def stackup_sexpr():
    """KiCad board stack-up block built from design.py (copper weights, dielectrics)."""
    rows = ['(layer "F.SilkS" (type "Top Silk Screen"))', '(layer "F.Paste" (type "Top Solder Paste"))',
            '(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))']
    names = list(D.COPPER_MM)
    for i, name in enumerate(names):
        rows.append(f'(layer "{name}" (type "copper") (thickness {D.COPPER_MM[name]}))')
        if i < len(D.DIELECTRIC_MM):
            kind, thick = D.DIELECTRIC_MM[i]
            rows.append(f'(layer "dielectric {i + 1}" (type "{kind}") (thickness {thick}) '
                        f'(material "FR4") (epsilon_r {D.EPSILON_R}) (loss_tangent 0.02))')
    rows += ['(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))',
             '(layer "B.Paste" (type "Bottom Solder Paste"))', '(layer "B.SilkS" (type "Bottom Silk Screen"))',
             '(copper_finish "ENIG")', '(dielectric_constraints no)']
    return "(stackup\n\t\t\t" + "\n\t\t\t".join(rows) + "\n\t\t)"


def write_stackup():
    text = OUT.read_text(encoding="utf-8")
    if "(stackup" in text:
        return
    i = text.index("(setup")
    text = text[:i] + "(setup\n\t\t" + stackup_sexpr() + text[i + len("(setup"):]
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print("stack-up written: inner layers", D.COPPER_MM["In1.Cu"], "mm copper")


def build():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    bds = board.GetDesignSettings()
    bds.m_MinClearance = mm(D.CLEARANCE)
    bds.m_TrackMinWidth = mm(D.TRACK)
    bds.m_ViasMinSize = mm(D.VIA_DIA)
    bds.m_MinThroughDrill = mm(D.VIA_DRILL)
    bds.m_CopperEdgeClearance = mm(0.3)
    nc = bds.m_NetSettings.m_DefaultNetClass
    nc.SetClearance(mm(D.CLEARANCE))
    nc.SetTrackWidth(mm(D.TRACK))
    nc.SetViaDiameter(mm(D.VIA_DIA))
    nc.SetViaDrill(mm(D.VIA_DRILL))

    # outline
    n = len(D.OUTLINE)
    for i in range(n):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pt(*D.OUTLINE[i]))
        seg.SetEnd(pt(*D.OUTLINE[(i + 1) % n]))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(mm(0.1))
        board.Add(seg)

    nets = {}

    def net(name):
        if name not in nets:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
            nets[name] = ni
        return nets[name]

    titles = dict(D.SECTIONS)
    for p in D.PARTS:
        lib, name = p["fp"].split(":")
        fp = pcbnew.FootprintLoad(str(PROJECT_LIBS.get(lib, FP_DIR / f"{lib}.pretty")), name)
        assert fp, f"footprint not found: {p['fp']}"
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        # link the footprint to its schematic symbol (same UUIDs as make_schematic.py)
        fp.SetPath(pcbnew.KIID_PATH(ids.symbol_path(p["section"], p["ref"])))
        fp.SetSheetname(titles[p["section"]])
        fp.SetSheetfile(f"{p['section']}.kicad_sch")
        attrs = fp.GetAttributes() & ~pcbnew.FP_EXCLUDE_FROM_BOM
        fp.SetAttributes(attrs if p["bom"] else attrs | pcbnew.FP_EXCLUDE_FROM_BOM)
        board.Add(fp)
        fp.SetPosition(pt(p["x"], p["y"]))
        if p["side"] == "B":
            fp.Flip(fp.GetPosition(), False)
        fp.SetOrientationDegrees(p["rot"])
        netmap = mcu_pins.part_nets(D, p)
        seen = set()
        for pad in fp.Pads():
            num = pad.GetNumber()
            if num in netmap:
                pad.SetNet(net(netmap[num]))
                seen.add(num)
        unknown = set(netmap) - seen
        assert not unknown, f"{p['ref']}: pads {unknown} not in footprint {name}"
        # Through-hole pads already sit solidly in the inner planes, and the ground pads of the
        # bottom-side capacitors are boxed in under the MCU: give both a solid connection to
        # the outer ground fills too, instead of thermal spokes that have no room.
        for pad in fp.Pads():
            if pad.GetNetname() and (pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
                                     or (p["side"] == "B" and pad.GetNetname() == "GND")):
                setter = getattr(pad, "SetLocalZoneConnection", None) or pad.SetZoneConnection
                setter(pcbnew.ZONE_CONNECTION_FULL)
        # unused pins carry the "unconnected-(...)" net names KiCad gave them in the schematic
        for pad in fp.Pads():
            name_nc = NC_NETS.get((p["ref"], pad.GetNumber()))
            if name_nc and not pad.GetNetname():
                pad.SetNet(net(name_nc))
    return board, nets


def schematic_nc_nets():
    """(ref, pad) -> net name for the single-pin nets in the schematic's netlist, if exported."""
    path = OUT.parent / "gen" / "schematic.net"
    if not path.exists():
        print("note: gen/schematic.net not found - run make_schematic.py --check first")
        return {}
    import make_schematic as M
    text = path.read_text(encoding="utf-8")
    out = {}
    for n in M.child(M.parse(text, text.index("(export")), "nets")[1:]:
        name = M.unq(M.child(n, "name")[1])
        if name.startswith("unconnected-"):
            for node in n:
                if isinstance(node, list) and node[0] == "node":
                    out[(M.unq(M.child(node, "ref")[1]), M.unq(M.child(node, "pin")[1]))] = name
    return out


NC_NETS = schematic_nc_nets()


# ---------------------------------------------------------------------------
# Placement checks
# ---------------------------------------------------------------------------
def inside_outline(x, y):
    poly, hit, n = D.OUTLINE, False, len(D.OUTLINE)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


EDGE_PARTS = {"J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J12", "J11"}   # may overhang


def check_placement(board):
    boxes, problems = [], []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        cy = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False, False)
        box = [pcbnew.ToMM(v) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())]
        box = [box[0] - CX, box[1] - CY, box[2] - CX, box[3] - CY]
        tht = any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH for p in fp.Pads())
        boxes.append((ref, fp.IsFlipped(), tht, box))
        if ref not in EDGE_PARTS:
            for x, y in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])):
                if not inside_outline(x, y):
                    problems.append(f"{ref} extends outside the board at ({x:.1f}, {y:.1f})")
                    break
    for i, (ra, sa, ta, a) in enumerate(boxes):
        for rb, sb, tb, b in boxes[i + 1:]:
            if sa != sb and not (ta or tb):
                continue        # opposite sides, no through-hole parts involved
            if sa != sb and (ta and tb) is False and not (ta or tb):
                continue
            ox = min(a[2], b[2]) - max(a[0], b[0])
            oy = min(a[3], b[3]) - max(a[1], b[1])
            if ox > 0.05 and oy > 0.05:
                if sa != sb and {ra, rb} & {"U1"}:
                    continue    # caps under the MCU are intentional
                problems.append(f"{ra} overlaps {rb} by {ox:.2f} x {oy:.2f} mm")
    return problems


# ---------------------------------------------------------------------------
# Geometry export for the router
# ---------------------------------------------------------------------------
def _mm_or_zero(getter):
    try:
        v = getter()
        return pcbnew.ToMM(v) if isinstance(v, int) else 0.0
    except Exception:
        return 0.0


def export_pads(board):
    """Pads, bare holes and footprint keep-out areas, in board-centre millimetres."""
    pads, holes, keepouts = [], [], []
    for fp in board.GetFootprints():
        fp_clr = _mm_or_zero(fp.GetLocalClearance)
        for z in fp.Zones():
            if not z.GetIsRuleArea() or not (z.GetDoNotAllowTracks() or z.GetDoNotAllowVias()):
                continue
            chain = z.Outline().Outline(0)
            pts = [(pcbnew.ToMM(chain.CPoint(i).x) - CX, pcbnew.ToMM(chain.CPoint(i).y) - CY)
                   for i in range(chain.PointCount())]
            keepouts.append(dict(
                ref=fp.GetReference(), points=pts,
                layers=[l for l, lid in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)) if z.IsOnLayer(lid)],
                tracks=bool(z.GetDoNotAllowTracks()), vias=bool(z.GetDoNotAllowVias())))
        for pad in fp.Pads():
            pos = pad.GetPosition()
            x, y = pcbnew.ToMM(pos.x) - CX, pcbnew.ToMM(pos.y) - CY
            size = pad.GetSize()
            sx, sy = pcbnew.ToMM(size.x), pcbnew.ToMM(size.y)
            layers = [l for l, lid in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)) if pad.IsOnLayer(lid)]
            attr = pad.GetAttribute()
            drill = pcbnew.ToMM(pad.GetDrillSize().x)
            if attr == pcbnew.PAD_ATTRIB_NPTH or (not layers and drill > 0):
                holes.append((x, y, drill))
                continue
            if not layers:
                continue            # paste-only apertures
            pads.append(dict(
                ref=fp.GetReference(), num=pad.GetNumber(),
                net=None if pad.GetNetname().startswith("unconnected-") else pad.GetNetname() or None,
                x=x, y=y, sx=sx, sy=sy, rot=pad.GetOrientationDegrees(), layers=layers,
                round=pad.GetShape() == pcbnew.PAD_SHAPE_CIRCLE
                or (pad.GetShape() == pcbnew.PAD_SHAPE_OVAL and abs(sx - sy) < 1e-6),
                oval=pad.GetShape() == pcbnew.PAD_SHAPE_OVAL and abs(sx - sy) >= 1e-6,
                clr=max(D.CLEARANCE, fp_clr, _mm_or_zero(pad.GetLocalClearance)),
                tht=attr == pcbnew.PAD_ATTRIB_PTH, drill=drill))
    return pads, holes, keepouts


# ---------------------------------------------------------------------------
# Copper
# ---------------------------------------------------------------------------
LAYER = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu,
         "In3.Cu": pcbnew.In3_Cu, "In4.Cu": pcbnew.In4_Cu}


def add_tracks(board, nets, result):
    for netname, layer, x1, y1, x2, y2, w in result["segments"]:
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pt(x1, y1))
        t.SetEnd(pt(x2, y2))
        t.SetWidth(mm(w))
        t.SetLayer(LAYER[layer])
        t.SetNet(nets[netname])
        board.Add(t)
    for netname, x, y, dia, drill in result["vias"]:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pt(x, y))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetWidth(mm(dia))
        v.SetDrill(mm(drill))
        v.SetNet(nets[netname])
        board.Add(v)


def add_zone(board, netinfo, layer, points, priority=0, solid=True, clearance=0.2):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(netinfo)
    outline = z.Outline()
    outline.NewOutline()
    for x, y in points:
        outline.Append(mm(CX + x), mm(CY + y))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(mm(clearance))
    z.SetMinThickness(mm(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if solid else pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.25))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    board.Add(z)
    return z


def add_zones(board, nets):
    for netname, layers in D.PLANES.items():
        for layer in layers:
            add_zone(board, nets[netname], LAYER[layer], D.OUTLINE)
    for pour in D.POURS:
        add_zone(board, nets[pour["net"]], LAYER[pour["layer"]], pour["poly"], priority=2)
    # ground fill on the outer layers
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        add_zone(board, nets["GND"], layer, D.OUTLINE, solid=False, clearance=0.25)


def fill_zones():
    """Fill zones on the saved board. KiCad 8.0 crashes if asked to fill a board that was
    built in memory, so this runs in a fresh process on the file."""
    board = pcbnew.LoadBoard(str(OUT))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(OUT), board)
    print(f"filled {len(board.Zones())} zones")
    write_stackup()
    write_netclasses()


def write_netclasses():
    """Net classes (USB pair, power, current sense) into the project file."""
    pro = OUT.with_suffix(".kicad_pro")
    data = json.loads(pro.read_text(encoding="utf-8"))
    ns = data.setdefault("net_settings", {})
    default = next((c for c in ns.get("classes", []) if c.get("name") == "Default"), None) or {
        "name": "Default", "bus_width": 12, "wire_width": 6, "line_style": 0,
        "microvia_diameter": 0.3, "microvia_drill": 0.1,
        "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)"}
    default.update(clearance=D.CLEARANCE, track_width=D.TRACK, via_diameter=D.VIA_DIA,
                   via_drill=D.VIA_DRILL, diff_pair_width=D.TRACK, diff_pair_gap=D.CLEARANCE,
                   diff_pair_via_gap=0.25)
    classes, patterns = [default], []
    for name, c in D.NETCLASSES.items():
        k = dict(default, name=name, clearance=c["clearance"], track_width=c["track"])
        if "dp_width" in c:
            k.update(diff_pair_width=c["dp_width"], diff_pair_gap=c["dp_gap"])
        classes.append(k)
        patterns += [{"netclass": name, "pattern": n} for n in c["nets"]]
    ns["classes"], ns["netclass_patterns"] = classes, patterns
    ns.setdefault("meta", {"version": 3})
    pro.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"net classes: {', '.join(D.NETCLASSES)}")


def dump_copper():
    """Filled copper of the power nets, vias and pads -> gen/copper.json (for power_check.py)."""
    board = pcbnew.LoadBoard(str(OUT))
    rev = {v: k for k, v in LAYER.items()}
    zones = []
    for z in board.Zones():
        net = z.GetNetname()
        if net not in ("GND", "VBAT", "VBAT_IN"):
            continue
        for lid in z.GetLayerSet().Seq():
            polys = z.GetFilledPolysList(lid)
            rings = []
            for i in range(polys.OutlineCount()):
                chains = [polys.Outline(i)] + [polys.Hole(i, j) for j in range(polys.HoleCount(i))]
                rings.append([[(round(pcbnew.ToMM(c.CPoint(k).x) - CX, 4),
                                round(pcbnew.ToMM(c.CPoint(k).y) - CY, 4))
                               for k in range(c.PointCount())] for c in chains])
            zones.append(dict(net=net, layer=rev[lid], polys=rings))
    vias = [dict(net=t.GetNetname(), x=pcbnew.ToMM(t.GetPosition().x) - CX,
                 y=pcbnew.ToMM(t.GetPosition().y) - CY, dia=pcbnew.ToMM(t.GetWidth()),
                 drill=pcbnew.ToMM(t.GetDrill()))
            for t in board.GetTracks() if t.GetClass() == "PCB_VIA"]
    pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() in ("GND", "VBAT", "VBAT_IN"):
                pos, size = pad.GetPosition(), pad.GetSize()
                pads.append(dict(ref=fp.GetReference(), num=pad.GetNumber(), net=pad.GetNetname(),
                                 x=pcbnew.ToMM(pos.x) - CX, y=pcbnew.ToMM(pos.y) - CY,
                                 sx=pcbnew.ToMM(size.x), sy=pcbnew.ToMM(size.y),
                                 rot=pad.GetOrientationDegrees(),
                                 drill=pcbnew.ToMM(pad.GetDrillSize().x),
                                 tht=pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH))
    (OUT.parent / "gen" / "copper.json").write_text(json.dumps(dict(zones=zones, vias=vias, pads=pads)))
    print(f"copper.json: {len(zones)} zone layers, {len(vias)} vias, {len(pads)} pads")


def main():
    if "--fill-only" in sys.argv:
        fill_zones()
        return 0
    if "--dump-copper" in sys.argv:
        dump_copper()
        return 0
    t0 = time.time()
    board, nets = build()
    problems = check_placement(board)
    print(f"{len(board.GetFootprints())} footprints, {len(nets)} nets")
    for p in problems:
        print("  PLACEMENT:", p)
    if "--dump-pads" in sys.argv:           # for debugging the router outside KiCad
        pads, holes, keepouts = export_pads(board)
        (OUT.parent / "gen" / "pads.json").write_text(json.dumps(
            dict(pads=pads, holes=holes, keepouts=keepouts)))
        return 0
    if "--no-route" not in sys.argv:
        pads, holes, keepouts = export_pads(board)
        cached = OUT.parent / "gen" / "route_result.json"
        if "--use-result" in sys.argv:        # routed beforehand by preview.py
            result = json.loads(cached.read_text())
            print("using", cached.name, result["stats"])
        else:
            result = R.route(pads, holes, D, keepouts)
        add_tracks(board, nets, result)
        (OUT.parent / "gen" / "route_report.json").write_text(json.dumps(
            {k: result[k] for k in ("unrouted", "stats", "nets")}, indent=1))
        add_zones(board, nets)
    pcbnew.SaveBoard(str(OUT), board)
    if "--no-route" not in sys.argv:
        sys.stdout.flush()
        subprocess.run([sys.executable, __file__, "--fill-only"], check=True)
    print(f"saved {OUT} in {time.time() - t0:.0f}s")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
