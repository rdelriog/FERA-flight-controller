"""Render the router's occupancy map to a PNG (debug aid).

    cad/.venv/Scripts/python hardware/fera-core/gen/debug_map.py [x0 y0 x1 y1] [--routed]
Colours: white free, black blocked, colours = owned by a net.
"""
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import design as D  # noqa: E402
import router as R  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    win = [float(a) for a in args[:4]] if len(args) >= 4 else [-12, -12, 12, 12]
    data = json.loads((HERE / "pads.json").read_text())
    r = R.Router(data["pads"], [tuple(h) for h in data["holes"]], D, data.get("keepouts", ()))
    if "--stubs" in sys.argv or "--routed" in sys.argv:
        for net in D.PLANES:
            r.plane_access(net)
    scale = 8
    for layer in (0, 1):
        ix0, iy0 = int((win[0] - r.x0) / R.GRID), int((win[1] - r.y0) / R.GRID)
        ix1, iy1 = int((win[2] - r.x0) / R.GRID), int((win[3] - r.y0) / R.GRID)
        img = Image.new("RGB", (ix1 - ix0, iy1 - iy0), "white")
        px = img.load()
        occ = r.occ[layer]
        for iy in range(iy0, iy1):
            for ix in range(ix0, ix1):
                v = occ[iy * r.W + ix]
                if v == R.BLOCK:
                    px[ix - ix0, iy - iy0] = (0, 0, 0)
                elif v:
                    px[ix - ix0, iy - iy0] = ((v * 67) % 200 + 40, (v * 131) % 200 + 40, (v * 29) % 200 + 40)
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
        img.save(HERE / f"debug_{'FB'[layer]}.png")
    print("wrote debug_F.png, debug_B.png for window", win)


if __name__ == "__main__":
    main()
