"""Read the STM32H743VITx pin table (numbers, names, alternate functions) from KiCad's symbol library."""
import re
from pathlib import Path

KICAD_SHARE = Path(r"C:\Program Files\KiCad\8.0\share\kicad")


def _block(text, start):
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    raise ValueError("unbalanced")


def load(symbol="STM32H743VITx", lib="MCU_ST_STM32H7"):
    text = (KICAD_SHARE / "symbols" / f"{lib}.kicad_sym").read_text(encoding="utf-8")
    sym = _block(text, text.index(f'(symbol "{symbol}"'))
    ext = re.search(r'\(extends "([^"]+)"\)', sym)
    if ext:
        sym = _block(text, text.index(f'(symbol "{ext.group(1)}"'))
    pins = {}
    for m in re.finditer(r"\(pin \w+ \w+", sym):
        blk = _block(sym, m.start())
        name = re.search(r'\(name "([^"]*)"', blk).group(1)
        num = re.search(r'\(number "([^"]*)"', blk).group(1)
        alts = re.findall(r'\(alternate "([^"]*)"', blk)
        pins[num] = (name, alts)
    return pins


def netmap(D):
    """MCU pin number -> net name, from design.MCU_NETS (keyed by pin name)."""
    pins = load()
    out, used = {}, set()
    for num, (name, _alts) in pins.items():
        if num in D.MCU_VCAP:
            out[num] = D.MCU_VCAP[num]
            continue
        base = name.split("-")[0].split("/")[0]
        for key in (name, base, base.split("_")[0]):
            if key in D.MCU_NETS:
                out[num] = D.MCU_NETS[key]
                used.add(key)
                break
    missing = set(D.MCU_NETS) - used
    assert not missing, f"MCU pins not found in symbol: {missing}"
    return out


def check_functions(D):
    """Signals whose peripheral function is not offered on the chosen pin."""
    by_name = {}
    for _num, (name, alts) in load().items():
        by_name[name.split("-")[0].split("/")[0]] = (name, alts)
    bad = []
    for pin, func in D.MCU_FUNCS.items():
        name, alts = by_name.get(pin, ("", []))
        if not any(func == a or func in a.split("/") for a in alts) and func not in name:
            bad.append(f"{pin}: {func} not in {alts[:12]}")
    return bad


def part_nets(D, p):
    return netmap(D) if p["nets"] == "MCU" else p["nets"]


if __name__ == "__main__":
    pins = load()
    print(len(pins), "pins")
    for num in sorted(pins, key=int):
        print(num, pins[num][0])
