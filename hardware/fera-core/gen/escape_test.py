"""Can every signal net be routed on the board with only the fixed copper in place
(plane vias, pours, frozen nets)? Catches walled-in pads in seconds, before a long routing run.

    cad/.venv/Scripts/python hardware/fera-core/gen/escape_test.py     (needs gen/pads.json)
"""
import json
import sys
from pathlib import Path

G = Path(r"C:\FERA\modular-drone-starter\hardware\fera-core\gen")
sys.path.insert(0, str(G))
import design as D  # noqa: E402
import router as R  # noqa: E402

data = json.loads((G / "pads.json").read_text())
pads = data["pads"]
r = R.Router(pads, [tuple(h) for h in data["holes"]], D, data.get("keepouts", ()))
for net in D.PLANES:
    r.plane_access(net)
print("plane stub failures:", r.unrouted)
r.snapshot()
by_net = {}
for p in pads:
    if p["net"] and p["net"] not in D.PLANES:
        by_net.setdefault(p["net"], []).append(p)
for ps in by_net.values():
    ps.sort(key=lambda p: (p["x"], p["y"]))
for net in D.PRE_ROUTE:
    if len(by_net.get(net, ())) < 2:
        continue
    ok, paths, missing = r.route_net(net, by_net[net])
    if ok:
        r.freeze(net, paths)
    else:
        r.rebuild()
        print("pre-route failed:", net, missing)
r.add_guards()
r.snapshot()
bad = 0
for net, ps in by_net.items():
    if len(ps) < 2 or net in D.PRE_ROUTE:
        continue
    ok, _paths, missing = r.route_net(net, ps, ghost=True)
    if not ok:
        bad += 1
        print("no path on an otherwise empty board:", net, missing)
print("walled-in nets:", bad)
