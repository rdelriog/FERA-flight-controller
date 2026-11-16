"""Route outside KiCad and draw the result as a PNG (fast iteration / debug aid).

    cad/.venv/Scripts/python hardware/fera-core/gen/preview.py
Needs gen/pads.json (build_board.py --dump-pads). Red = top copper, blue = bottom,
green dots = vias, yellow rings = pads the router could not connect.
"""
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import design as D  # noqa: E402
import router as R  # noqa: E402

S = 14          # pixels per mm


def main():
    data = json.loads((HERE / "pads.json").read_text())
    pads, holes = data["pads"], [tuple(h) for h in data["holes"]]
    result = R.route(pads, holes, D, data.get("keepouts", ()), quick="--quick" in sys.argv)
    (HERE / "route_result.json").write_text(json.dumps(result))
    draw(pads, result)


def draw(pads, result, name="preview.png"):
    xs = [p[0] for p in D.OUTLINE]
    ys = [p[1] for p in D.OUTLINE]
    x0, y0 = min(xs) - 1, min(ys) - 1
    W, H = int((max(xs) - x0 + 1) * S), int((max(ys) - y0 + 1) * S)

    def P(x, y):
        return ((x - x0) * S, (y - y0) * S)

    img = Image.new("RGB", (W, H), (18, 22, 28))
    d = ImageDraw.Draw(img, "RGBA")
    d.polygon([P(*p) for p in D.OUTLINE], fill=(30, 52, 40), outline=(230, 230, 120))
    for p in pads:
        a = math.radians(p["rot"])
        c, s = math.cos(a), math.sin(a)
        hx, hy = p["sx"] / 2, p["sy"] / 2
        col = (200, 200, 200, 255) if "F" in p["layers"] else (110, 130, 200, 255)
        if p["round"]:
            cx, cy = P(p["x"], p["y"])
            d.ellipse([cx - hx * S, cy - hx * S, cx + hx * S, cy + hx * S], fill=col)
        else:
            pts = [P(p["x"] + lx * c + ly * s, p["y"] - lx * s + ly * c)
                   for lx, ly in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]
            d.polygon(pts, fill=col)
    for layer, col in (("B", (70, 130, 255, 210)), ("F", (255, 80, 70, 210))):
        for net, lay, x1, y1, x2, y2, w in result["segments"]:
            if lay == layer:
                d.line([P(x1, y1), P(x2, y2)], fill=col, width=max(int(w * S), 2))
    for pour in D.POURS:
        col = (255, 150, 60, 70) if pour["layer"] == "F" else (60, 150, 255, 50)
        d.polygon([P(*p) for p in pour["poly"]], fill=col)
    for net, x, y, dia, _drill in result["vias"]:
        cx, cy = P(x, y)
        r = dia / 2 * S
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(90, 220, 110, 255))
    index = {f"{p['ref']}.{p['num']}": p for p in pads}
    for net, where in result["unrouted"]:
        p = index.get(where)
        if p:
            cx, cy = P(p["x"], p["y"])
            d.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=(255, 230, 0, 255), width=3)
    img.save(HERE / name)
    print("wrote", HERE / name, img.size)


if __name__ == "__main__":
    main()
