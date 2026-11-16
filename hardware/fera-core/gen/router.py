"""Small two-layer maze router with rip-up and reroute, for the preliminary FERA Core layout.

Routes signals on the outer layers (F / B) of the six-layer board. Nets that
own an inner plane (GND, 3V3, VBAT) are not routed pad to pad: every surface
pad just gets a short stub to a via, and the plane does the rest.

Pure Python (no numpy) so it runs inside KiCad's interpreter. Geometry in mm,
relative to the board centre; the grid is 0.1 mm.
"""
import collections
import heapq
import math
import time
from array import array

GRID = 0.1
BLOCK = 0xFFFF
ORTH, DIAG, VIA_COST = 10, 14, 400
MAX_EXPANSIONS = 900_000
LANE = 0.6                      # escape lane reserved beyond each end of a narrow pad
MAX_RIPS = 160                   # total rip-up events allowed
RIPS_PER_NET = 3                 # per net and per round
ROUNDS = 4                       # extra rounds for nets that are still open
GHOST_PENALTY = 120              # cost of stepping on another net's track when planning a rip-up


def disk(radius):
    n = int(radius / GRID) + 1
    return [(dx, dy) for dx in range(-n, n + 1) for dy in range(-n, n + 1)
            if math.hypot(dx, dy) * GRID <= radius + 1e-9]


class Router:
    def __init__(self, pads, holes, D, keepouts=()):
        self.D = D
        self.clr = D.CLEARANCE
        self.hw0 = D.TRACK / 2
        xs = [p[0] for p in D.OUTLINE]
        ys = [p[1] for p in D.OUTLINE]
        self.x0, self.y0 = min(xs) - 2.0, min(ys) - 2.0
        self.W = int(round((max(xs) + 2.0 - self.x0) / GRID)) + 1
        self.H = int(round((max(ys) + 2.0 - self.y0) / GRID)) + 1
        self.N = self.W * self.H
        self.occ = [array("H", [BLOCK]) * self.N for _ in range(2)]
        self.novia = bytearray(self.N)
        self.codes = {}
        self.segments, self.vias, self.unrouted = [], [], []
        self.via_cells = {}                     # code -> set(cell)
        self.pads = pads
        self._outline()
        for x, y, drill in holes:
            r = drill / 2 + 0.25 + self.hw0
            for layer in (0, 1):
                self._mark(layer, x, y, 0, 0, 0, True, r, BLOCK)
            self._mark_novia(x, y, 0, 0, 0, True, r + 0.3)
        for p in pads:
            code = self.code(p["net"]) if p["net"] else BLOCK
            for layer in self._layers(p):
                self._mark(layer, p["x"], p["y"], p["sx"], p["sy"], p["rot"], p["round"],
                           p.get("clr", self.clr) + self.hw0, code)
            self._mark_novia(p["x"], p["y"], p["sx"], p["sy"], p["rot"], p["round"],
                             D.VIA_DIA / 2 + 0.05)
        for k in keepouts:                       # footprint rule areas (e.g. under the SD socket)
            xs, ys = [p[0] for p in k["points"]], [p[1] for p in k["points"]]
            grow = self.hw0 + 0.05               # a track's edge must stay out, not just its centre
            box = [(min(xs) - grow, min(ys) - grow), (max(xs) + grow, min(ys) - grow),
                   (max(xs) + grow, max(ys) + grow), (min(xs) - grow, max(ys) + grow)]
            for iy, i0, i1 in self._poly_rows(box):
                row = iy * self.W
                if k["tracks"]:
                    for layer in (0 if l == "F" else 1 for l in k["layers"]):
                        self.occ[layer][row + i0: row + i1 + 1] = array("H", [BLOCK]) * (i1 - i0 + 1)
                if k["vias"] or k["tracks"]:
                    self.novia[row + i0: row + i1 + 1] = bytes([1]) * (i1 - i0 + 1)
        # Escape lanes: reserve the strip off each end of a narrow pad for that pad's own
        # net, so an earlier track cannot run across the only way out of a fine-pitch pin.
        for p in pads:
            if not p["net"] or p["tht"] or p["round"]:
                continue
            lo, hi = sorted((p["sx"], p["sy"]))
            if lo > 0.8 or hi < 1.4 * lo:
                continue
            sx = p["sx"] + (2 * LANE if p["sx"] > p["sy"] else 0)
            sy = p["sy"] + (2 * LANE if p["sy"] > p["sx"] else 0)
            for layer in self._layers(p):
                self._mark(layer, p["x"], p["y"], sx, sy, p["rot"], False, 0.05, self.code(p["net"]))
        for x1, y1, x2, y2 in getattr(D, "NO_VIA_AREAS", ()):
            self._mark_novia((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1, 0, False, 0.0)
        for pour in D.POURS:                     # outer-layer pours belong to their net
            if pour["layer"] not in ("F", "B"):  # an island in a plane layer: no foreign plane vias
                x = [p[0] for p in pour["poly"]]
                y = [p[1] for p in pour["poly"]]
                self._mark_novia((min(x) + max(x)) / 2, (min(y) + max(y)) / 2, max(x) - min(x),
                                 max(y) - min(y), 0, False, D.VIA_DIA / 2 + 0.3)
                continue
            occ, code = self.occ[0 if pour["layer"] == "F" else 1], self.code(pour["net"])
            for iy, i0, i1 in self._poly_rows(pour["poly"]):
                for i in range(iy * self.W + i0, iy * self.W + i1 + 1):
                    v = occ[i]
                    if v == 0:
                        occ[i] = code
                    elif v != code:
                        occ[i] = BLOCK
        # every cell this close to a via centre must be free, so that other copper ends up
        # at least one full clearance from the via's edge (rounded up to the grid)
        self.via_chk = self._offsets(self._grid_up(D.VIA_DIA / 2 - self.hw0))
        for netname, x, y, dia, drill in D.STITCH_VIAS:
            self._lay_via(self.cell(x, y), self.code(netname), netname, dia=dia, drill=drill)

    # -- helpers -------------------------------------------------------------
    def code(self, net):
        if net not in self.codes:
            self.codes[net] = len(self.codes) + 1
        return self.codes[net]

    def cell(self, x, y):
        return int(round((y - self.y0) / GRID)) * self.W + int(round((x - self.x0) / GRID))

    def xy(self, i):
        return (round(self.x0 + (i % self.W) * GRID, 4), round(self.y0 + (i // self.W) * GRID, 4))

    @staticmethod
    def _grid_up(value):
        return math.ceil(value / GRID - 1e-9) * GRID

    def _poly_rows(self, poly):
        """Scanline fill: yields (row, first_col, last_col) spans inside a polygon."""
        n = len(poly)
        for iy in range(self.H):
            y = self.y0 + iy * GRID + 1e-7
            xs = []
            for k in range(n):
                (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
                if (y1 > y) != (y2 > y):
                    xs.append((x2 - x1) * (y - y1) / (y2 - y1) + x1)
            xs.sort()
            for a, b in zip(xs[::2], xs[1::2]):
                i0 = max(int(math.ceil((a - self.x0) / GRID)), 0)
                i1 = min(int(math.floor((b - self.x0) / GRID)), self.W - 1)
                if i1 >= i0:
                    yield iy, i0, i1

    def _offsets(self, radius):
        return [dy * self.W + dx for dx, dy in disk(radius)]

    @staticmethod
    def _layers(p):
        return [0 if l == "F" else 1 for l in p["layers"]]

    def _cells_in_shape(self, cx, cy, sx, sy, rot, rnd, inflate):
        """Yield cells whose centre lies within `inflate` of the shape (negative shrinks)."""
        reach = math.hypot(sx, sy) / 2 + max(inflate, 0) + GRID
        a = math.radians(rot)
        c, s = math.cos(a), math.sin(a)
        ix0 = max(int((cx - reach - self.x0) / GRID), 0)
        ix1 = min(int((cx + reach - self.x0) / GRID) + 1, self.W - 1)
        iy0 = max(int((cy - reach - self.y0) / GRID), 0)
        iy1 = min(int((cy + reach - self.y0) / GRID) + 1, self.H - 1)
        hx, hy = sx / 2, sy / 2
        for iy in range(iy0, iy1 + 1):
            wy = self.y0 + iy * GRID - cy
            for ix in range(ix0, ix1 + 1):
                wx = self.x0 + ix * GRID - cx
                lx, ly = wx * c - wy * s, wx * s + wy * c
                if rnd:
                    d = math.hypot(lx, ly) - hx
                else:
                    dx, dy = abs(lx) - hx, abs(ly) - hy
                    d = math.hypot(max(dx, 0), max(dy, 0)) if (dx > 0 or dy > 0) else max(dx, dy)
                if d <= inflate - 1e-6:
                    yield iy * self.W + ix

    def _mark(self, layer, cx, cy, sx, sy, rot, rnd, inflate, code):
        occ = self.occ[layer]
        for i in self._cells_in_shape(cx, cy, sx, sy, rot, rnd, inflate):
            v = occ[i]
            if v == 0:
                occ[i] = code
            elif v != code:
                occ[i] = BLOCK

    def _mark_novia(self, cx, cy, sx, sy, rot, rnd, inflate):
        for i in self._cells_in_shape(cx, cy, sx, sy, rot, rnd, inflate):
            self.novia[i] = 1

    def _outline(self):
        poly = self.D.OUTLINE
        n = len(poly)
        for iy, i0, i1 in self._poly_rows(poly):
            for layer in (0, 1):
                self.occ[layer][iy * self.W + i0: iy * self.W + i1 + 1] = array("H", [0]) * (i1 - i0 + 1)
        keep = 0.3 + self.hw0
        for k in range(n):
            (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
            length = math.hypot(x2 - x1, y2 - y1)
            rot = -math.degrees(math.atan2(y2 - y1, x2 - x1))
            cells = list(self._cells_in_shape((x1 + x2) / 2, (y1 + y2) / 2, length, 0.0, rot, False, keep))
            for i in cells:
                self.occ[0][i] = BLOCK
                self.occ[1][i] = BLOCK
                self.novia[i] = 1

    def pad_cells(self, p, code):
        """Grid cells inside the pad copper where a track of this net may end."""
        out = []
        for layer in self._layers(p):
            occ = self.occ[layer]
            if p["round"]:
                gen = self._cells_in_shape(p["x"], p["y"], p["sx"], p["sy"], p["rot"], True, -0.06)
            elif p.get("oval"):                      # stadium: use only its straight middle part
                r = min(p["sx"], p["sy"])
                gen = self._cells_in_shape(p["x"], p["y"], max(p["sx"] - r, 0.08),
                                           max(p["sy"] - r, 0.08), p["rot"], False, 0.0)
            else:
                gen = self._cells_in_shape(p["x"], p["y"], max(p["sx"] - 0.12, 0.08),
                                           max(p["sy"] - 0.12, 0.08), p["rot"], False, 0.0)
            for i in gen:
                if occ[i] in (0, code):
                    out.append(layer * self.N + i)
        return out

    # -- copper --------------------------------------------------------------
    def _via_ok(self, i, code, occs=None, novia=None):
        if (novia or self.novia)[i]:
            return False
        o0, o1 = occs or self.occ
        for off in self.via_chk:
            j = i + off
            v = o0[j]
            if v and v != code:
                return False
            v = o1[j]
            if v and v != code:
                return False
        return True

    def _lay_via(self, i, code, net, emit=True, dia=None, drill=None):
        dia, drill = dia or self.D.VIA_DIA, drill or self.D.VIA_DRILL
        offs = self._offsets(dia / 2 + self.clr + self.hw0 - 0.011)
        for occ in self.occ:
            for off in offs:
                j = i + off
                v = occ[j]
                if v == 0:
                    occ[j] = code
                elif v != code:
                    occ[j] = BLOCK
        for off in self._offsets(dia / 2 + self.D.VIA_DIA / 2 + 0.1):   # no touching vias
            self.novia[i + off] = 1
        self.via_cells.setdefault(code, set()).add(i)
        if emit:
            self.vias.append((net, *self.xy(i), dia, drill))
        else:                                               # a rippable signal via
            for off in self._offsets(self.D.VIA_DIA / 2 + 0.15):
                self.center[i + off] = net
                self.center[self.N + i + off] = net

    def _lay_path(self, path, code, net, width, emit=True):
        """Mark a path's copper. emit=True also records it as permanent output."""
        N = self.N
        offs = self._offsets(width / 2 + self.clr + self.hw0 - 0.011)
        for key in path:
            occ = self.occ[key // N]
            i = key % N
            for off in offs:
                j = i + off
                v = occ[j]
                if v == 0:
                    occ[j] = code
                elif v != code:
                    occ[j] = BLOCK
        if not emit:
            center = self.center
            for key in path:
                center[key] = net
        prev = path[0]
        for key in path[1:]:
            if key // N != prev // N:
                self._lay_via(prev % N, code, net, emit)
            prev = key
        if emit:
            self._emit(path, net, width, vias=False)

    def _emit(self, path, net, width, vias=True):
        """Turn a cell path into straight segments (and vias) in the output lists."""
        N = self.N
        run_start, prev, direction = path[0], path[0], None
        for key in path[1:]:
            if key // N != prev // N:                       # layer change
                if run_start != prev:
                    self._segment(net, run_start, prev, width)
                if vias:
                    self.vias.append((net, *self.xy(prev % N), self.D.VIA_DIA, self.D.VIA_DRILL))
                run_start, direction = key, None
            else:
                d = key - prev
                if direction is not None and d != direction:
                    self._segment(net, run_start, prev, width)
                    run_start = prev
                direction = d
            prev = key
        if run_start != prev:
            self._segment(net, run_start, prev, width)

    def _segment(self, net, a, b, width):
        layer = "F" if a // self.N == 0 else "B"
        self.segments.append((net, layer, *self.xy(a % self.N), *self.xy(b % self.N), width))

    # -- rip-up support ----------------------------------------------------------
    def snapshot(self):
        """Freeze the current state (pads, lanes, plane stubs) as the un-rippable base."""
        self.base_occ = [array("H", o) for o in self.occ]
        self.base_novia = bytearray(self.novia)
        self.base_via_cells = {k: set(v) for k, v in self.via_cells.items()}
        self.routed = {}                    # net -> [(path, width)]
        self.center = {}                    # key -> net, for finding who blocks a path

    def freeze(self, net, paths):
        """Make an already laid net permanent: emit it and fold it into the base state."""
        for path, width in paths:
            self._emit(path, net, width)
        self.snapshot()

    def add_guards(self):
        """Close the guard areas on the top layer to every net that is not already there."""
        occ = self.occ[0]
        for x1, y1, x2, y2 in getattr(self.D, "GUARDS", ()):
            for iy, i0, i1 in self._poly_rows([(x1, y1), (x2, y1), (x2, y2), (x1, y2)]):
                for i in range(iy * self.W + i0, iy * self.W + i1 + 1):
                    if occ[i] == 0:
                        occ[i] = BLOCK

    def rebuild(self):
        self.occ = [array("H", o) for o in self.base_occ]
        self.novia = bytearray(self.base_novia)
        self.via_cells = {k: set(v) for k, v in self.base_via_cells.items()}
        self.center = {}
        for net, paths in self.routed.items():
            code = self.code(net)
            for path, width in paths:
                self._lay_path(path, code, net, width, emit=False)

    def blockers(self, paths, net):
        """Routed nets whose copper is in the way of these (planned) paths."""
        offs = self._offsets(0.45)
        center, N = self.center, self.N
        found = set()
        for path in paths:
            for key in path:
                base = key - key % N
                i = key % N
                for off in offs:
                    other = center.get(base + i + off)
                    if other and other != net:
                        found.add(other)
        return found

    # -- search --------------------------------------------------------------
    def _search(self, sources, goal, bbox, code, width, allow_via=True, penalty=None,
                limit=MAX_EXPANSIONS, ghost=False):
        """A* from a set of source keys to the first key for which goal(key) is true.

        ghost=True plans against the base state only (ignoring every routed signal),
        charging GHOST_PENALTY for cells another net's track currently occupies.
        """
        W, N = self.W, self.N
        occs = self.base_occ if ghost else self.occ
        novia = self.base_novia if ghost else self.novia
        live = self.occ
        # a wider track needs its extra half-width (rounded up to the grid) free on each side
        wide = (self._offsets(self._grid_up(width / 2 - self.hw0))
                if width / 2 > self.hw0 + 1e-6 else None)
        moves = ((1, ORTH), (-1, ORTH), (W, ORTH), (-W, ORTH),
                 (W + 1, DIAG), (W - 1, DIAG), (-W + 1, DIAG), (-W - 1, DIAG))
        if bbox:
            bx0, by0, bx1, by1 = bbox

            def h(i):
                x, y = i % W, i // W
                dx = bx0 - x if x < bx0 else (x - bx1 if x > bx1 else 0)
                dy = by0 - y if y < by0 else (y - by1 if y > by1 else 0)
                return (dx + dy) * ORTH - (2 * ORTH - DIAG) * min(dx, dy)
        else:
            def h(i):
                return 0
        g = {}
        parent = {}
        heap = []
        for s in sources:
            g[s] = 0
            heap.append((h(s % N), 0, s))
        heapq.heapify(heap)
        pop, push = heapq.heappop, heapq.heappush
        expansions = 0
        while heap:
            _f, gc, key = pop(heap)
            if gc > g[key]:
                continue
            if goal(key):
                path = [key]
                while key in parent:
                    key = parent[key]
                    path.append(key)
                path.reverse()
                return path
            expansions += 1
            if expansions > limit:
                return None
            layer, i = divmod(key, N)
            occ = occs[layer]
            base = layer * N
            for d, cost in moves:
                j = i + d
                v = occ[j]
                if v and v != code:
                    continue
                if cost == DIAG:
                    dx = 1 if (d == W + 1 or d == -W + 1) else -1
                    dy = d - dx
                    v = occ[i + dx]
                    if v and v != code:
                        continue
                    v = occ[i + dy]
                    if v and v != code:
                        continue
                if wide:
                    ok = True
                    for off in wide:
                        v = occ[j + off]
                        if v and v != code:
                            ok = False
                            break
                    if not ok:
                        continue
                ng = gc + cost
                if penalty:
                    ng += penalty(j)
                if ghost and live[layer][j] != occ[j]:
                    ng += GHOST_PENALTY
                nk = base + j
                if ng < g.get(nk, 1 << 60):
                    g[nk] = ng
                    parent[nk] = key
                    push(heap, (ng + h(j), ng, nk))
            if allow_via and self._via_ok(i, code, occs, novia):
                nk = (1 - layer) * N + i
                ng = gc + VIA_COST
                if ghost and not self._via_ok(i, code):
                    ng += GHOST_PENALTY * 4
                if ng < g.get(nk, 1 << 60):
                    g[nk] = ng
                    parent[nk] = key
                    push(heap, (ng + h(i), ng, nk))
        return None

    # -- net strategies ------------------------------------------------------
    def plane_access(self, net):
        """Give every surface pad of a plane net a via."""
        code = self.code(net)
        width = self.D.WIDTHS.get(net, self.D.TRACK)
        N, W = self.N, self.W
        vias = self.via_cells.setdefault(code, set())
        # keep stubs out of the MCU fan-out ring so signals can escape
        ring_lo, ring_hi = 8.6, 11.5

        def penalty(j):
            x = abs(self.x0 + (j % W) * GRID)
            y = abs(self.y0 + (j // W) * GRID)
            m = x if x > y else y
            return 60 if ring_lo < m < ring_hi else 0

        def goal(key):
            i = key % N
            return i in vias or self._via_ok(i, code)

        for p in self.pads:
            if p["net"] != net or p["tht"]:
                continue
            src = self.pad_cells(p, code)
            path = self._search(src, goal, None, code, width, allow_via=False, penalty=penalty,
                                limit=60_000) if src else None
            if not path and width > self.D.TRACK:       # fall back to a thin stub
                path = self._search(src, goal, None, code, self.D.TRACK, allow_via=False,
                                    penalty=penalty, limit=60_000) if src else None
                w = self.D.TRACK
            else:
                w = width
            if not path:
                self.unrouted.append((net, f"{p['ref']}.{p['num']}"))
                continue
            self._lay_path(path, code, net, w)
            end = path[-1] % N
            if end not in vias:
                self._lay_via(end, code, net)

    def route_net(self, net, pads, ghost=False):
        """Connect all pads of a net. Returns (complete, paths, missing_pad_names)."""
        code = self.code(net)
        width = self.D.WIDTHS.get(net, self.D.TRACK)
        N, W = self.N, self.W
        cells = [self.pad_cells(p, code) for p in pads]

        def name(k):
            return f"{pads[k]['ref']}.{pads[k]['num']}"

        missing = [name(k) for k in range(len(pads)) if not cells[k]]
        todo = {k for k in range(1, len(pads)) if cells[k]}
        tree = set(cells[0])
        paths = []
        if not tree:
            return False, paths, [name(k) for k in range(len(pads))]
        while todo:
            target = {}
            for k in todo:
                for c in cells[k]:
                    target[c] = k
            xs = [c % N % W for c in target]
            ys = [c % N // W for c in target]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            w = width
            path = self._search(tree, target.__contains__, bbox, code, w, ghost=ghost)
            if path is None and width > self.D.TRACK:
                w = self.D.TRACK
                path = self._search(tree, target.__contains__, bbox, code, w, ghost=ghost)
            if path is None:
                missing += [name(k) for k in sorted(todo)]
                break
            k = target[path[-1]]
            paths.append((path, w))
            if not ghost:
                self._lay_path(path, code, net, w, emit=False)
            tree.update(path)
            tree.update(cells[k])
            todo.discard(k)
        return not missing, paths, missing


def route(pads, holes, D, keepouts=(), quick=False):
    """quick=True stops after the plane vias and the frozen nets (for the power check)."""
    def log(msg):
        print(msg, flush=True)

    t0 = time.time()
    r = Router(pads, holes, D, keepouts)
    for net in D.PLANES:
        r.plane_access(net)
    stub_failures = list(r.unrouted)
    for net, where in stub_failures:
        log(f"router: no plane via for {where} ({net})")
    log(f"router: plane stubs: {len(r.vias)} vias, {len(stub_failures)} failed, {time.time() - t0:.0f}s")
    r.snapshot()

    by_net = {}
    for p in pads:
        if p["net"] and p["net"] not in D.PLANES:
            by_net.setdefault(p["net"], []).append(p)
    for ps in by_net.values():
        ps.sort(key=lambda p: (p["x"], p["y"]))

    # Critical nets first, on an empty board, then frozen so nothing can rip them up.
    frozen = {}
    for net in getattr(D, "PRE_ROUTE", ()):
        if len(by_net.get(net, ())) < 2:
            continue
        ok, paths, missing = r.route_net(net, by_net[net])
        if ok:
            frozen[net] = paths
            r.freeze(net, paths)
        else:
            r.rebuild()
            log(f"router: pre-route of {net} failed at {missing}; left to the main pass")
    r.add_guards()
    r.snapshot()
    log(f"router: pre-routed and frozen: {', '.join(frozen) or 'none'}")

    jobs = []
    for net, ps in by_net.items():
        if len(ps) < 2 or net in frozen:
            continue
        span = (max(p["x"] for p in ps) - min(p["x"] for p in ps)
                + max(p["y"] for p in ps) - min(p["y"] for p in ps))
        # hand-picked hard nets first, then signals by length, then wide power nets
        rank = 0 if net in D.ROUTE_FIRST else (2 if net in D.WIDTHS else 1)
        jobs.append((rank, D.ROUTE_FIRST.index(net) if rank == 0 else span, net))
    jobs.sort()
    queue = collections.deque(() if quick else (j[2] for j in jobs))
    connections = (sum(len(by_net[j[2]]) - 1 for j in jobs)
                   + sum(len(by_net[n]) - 1 for n in frozen))
    rips_by = collections.Counter()
    rips, failed, rounds = 0, {}, 0
    best = None                             # (open connections, routed, failed) at a round end

    def keep_best():
        nonlocal best
        score = sum(len(v) for v in failed.values())
        if best is None or score < best[0]:
            best = (score, dict(r.routed), dict(failed))
            return True
        return False

    while queue or (failed and rounds < ROUNDS and rips < MAX_RIPS):
        if not queue:                       # another round for whatever is still open
            improved = keep_best()
            if rounds and (not improved or best[0] <= 1):
                break                       # later rounds only shuffle the problem around
            rounds += 1
            rips_by.clear()
            for net in failed:
                r.routed.pop(net, None)
                queue.append(net)
            r.rebuild()
            log(f"router: round {rounds + 1} for {sorted(failed)}")
            failed = {}
        net = queue.popleft()
        if net in r.routed:
            continue
        ok, paths, missing = r.route_net(net, by_net[net])
        if ok:
            r.routed[net] = paths
            failed.pop(net, None)
            continue
        # Blocked. Plan the net as if no other signal were routed, see who is in the way.
        r.rebuild()                                         # drop this net's partial copper
        plan_ok, plan, _ = r.route_net(net, by_net[net], ghost=True)
        victims = r.blockers([p for p, _w in plan], net) if plan_ok else set()
        if (plan_ok and victims and rips < MAX_RIPS and rips_by[net] < RIPS_PER_NET
                and len(victims) <= 14):
            rips += 1
            rips_by[net] += 1
            for v in victims:
                del r.routed[v]
            r.rebuild()
            ok, paths, missing = r.route_net(net, by_net[net])
            log(f"router: {net} ripped up {sorted(victims)} -> {'ok' if ok else 'still blocked'}")
            for v in victims:
                queue.appendleft(v)
        else:
            ok, paths, missing = r.route_net(net, by_net[net])      # keep what can be routed
        r.routed[net] = paths
        if ok:
            failed.pop(net, None)
        else:
            failed[net] = missing
            log(f"router: {net}: not routed to {missing}"
                + ("" if plan_ok else " (no path even on an empty board)"))

    if not queue:
        keep_best()
    if best and best[0] < sum(len(v) for v in failed.values()):
        log(f"router: keeping the best round ({best[0]} open) instead of the last one")
    if best:
        r.routed, failed = best[1], best[2]
    for net, paths in r.routed.items():
        for path, width in paths:
            r._emit(path, net, width)
    # length and via count per net, for the signal-integrity report
    report = {}
    for net, paths in list(frozen.items()) + list(r.routed.items()):
        length, nvias = 0.0, 0
        for path, _w in paths:
            for a, b in zip(path, path[1:]):
                if a // r.N != b // r.N:
                    nvias += 1
                else:
                    length += GRID * (1.0 if abs(a - b) in (1, r.W) else math.sqrt(2))
        report[net] = dict(length=round(length, 2), vias=nvias, pads=len(by_net[net]),
                           complete=net not in failed)
    unrouted = stub_failures + [(net, pad) for net, pads_ in failed.items() for pad in pads_]
    stats = dict(nets=len(jobs) + len(frozen), connections=connections,
                 unrouted_connections=sum(len(v) for v in failed.values()),
                 plane_stubs_failed=len(stub_failures), rip_ups=rips,
                 segments=len(r.segments), vias=len(r.vias), seconds=round(time.time() - t0))
    log(f"router: {stats}")
    return dict(segments=r.segments, vias=r.vias, unrouted=unrouted, stats=stats, nets=report)
