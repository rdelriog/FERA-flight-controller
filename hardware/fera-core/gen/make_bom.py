"""Write the grouped bill of materials for the generated board to bom/fera-core-revA.csv.

    python hardware/fera-core/gen/make_bom.py
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import design as D  # noqa: E402

OUT = HERE.parents[2] / "bom" / "fera-core-revA.csv"


def natural(ref):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2)))


def main():
    groups = defaultdict(list)
    for p in D.PARTS:
        if p["bom"]:
            groups[(p["value"], p["fp"], p["side"])].append(p)
    rows = []
    for (value, fp, side), parts in groups.items():
        refs = sorted((p["ref"] for p in parts), key=natural)
        notes = sorted({p["note"] for p in parts if p["note"]})
        rows.append((natural(refs[0]), [" ".join(refs), len(refs), value, fp.split(":")[1],
                                        "top" if side == "F" else "bottom", " ".join(notes)]))
    rows.sort()
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["References", "Qty", "Value", "Footprint", "Side", "Notes"])
        w.writerows(r for _k, r in rows)
    print(f"{sum(len(g) for g in groups.values())} parts in {len(rows)} lines -> {OUT}")


if __name__ == "__main__":
    main()
