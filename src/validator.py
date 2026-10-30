"""Model B - the independent validator.

Model B never trusts Model A's interpretation. It takes the original
drawing (the PartSpec) and the finished G-code as its only inputs,
replays the code through the material-removal simulator, and measures
the virtual part against the drawing: every feature, every tolerance.
It also runs machine-safety checks on the code itself (rapids below the
surface, cutting outside the stock, cutting with the spindle off) and a
gouge scan for material removed where the drawing has no feature.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .drawing import PartSpec
from .gcode import Program
from .simulator import CELL, Simulation


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.checks.append(Check(name, ok, detail))

    def format(self) -> str:
        lines = []
        for c in self.checks:
            lines.append(f"[{'PASS' if c.ok else 'FAIL'}] {c.name}: {c.detail}")
        lines.append(f"VERDICT: {'PASS' if self.passed else 'FAIL'} "
                     f"({sum(c.ok for c in self.checks)}/{len(self.checks)} checks passed)")
        return "\n".join(lines)


def _inside_other_feature(spec: PartSpec, x: float, y: float, skip) -> bool:
    for h in spec.holes:
        if h is skip:
            continue
        if (x - h.x) ** 2 + (y - h.y) ** 2 <= (h.diameter / 2 + 0.5) ** 2:
            return True
    for p in spec.pockets:
        if p is skip:
            continue
        if p.x - 0.5 <= x <= p.x + p.width + 0.5 and p.y - 0.5 <= y <= p.y + p.length + 0.5:
            return True
    return False


def validate(spec: PartSpec, prog: Program) -> Report:
    rep = Report()
    rep.add("PARSE", not prog.errors, "; ".join(prog.errors) if prog.errors else "program parsed cleanly")

    # Replay the code first: the simulator also watches rapid moves
    # against the material state at that moment.
    sim = Simulation(spec).run(prog)

    # --- machine-safety checks on the code itself ---
    rep.add("NO_RAPID_IN_MATERIAL", not sim.rapid_events,
            f"line {sim.rapid_events[0][0]}: {sim.rapid_events[0][1]}" if sim.rapid_events
            else "rapids stay clear of the material (vertical retracts allowed)")

    outside = [mv for mv in prog.moves if mv.kind == "G1" and
               (mv.x1 < -0.01 or mv.x1 > spec.stock_x + 0.01 or mv.y1 < -0.01 or mv.y1 > spec.stock_y + 0.01)]
    rep.add("NO_CUT_OUTSIDE_STOCK", not outside,
            f"cutting move leaves the stock at line {outside[0].line}" if outside else "all cutting stays inside the stock")

    spindle_hits = [mv for mv in prog.moves if mv.kind == "G1" and min(mv.z0, mv.z1) < 0 and not mv.spindle_on]
    rep.add("SPINDLE_ON_WHILE_CUTTING", not spindle_hits,
            f"cutting with spindle off at line {spindle_hits[0].line}" if spindle_hits else "spindle on for every cut")

    # --- measure the virtual part against the drawing ---
    slack = 0.35  # simulation resolution allowance, mm

    for i, h in enumerate(spec.holes, start=1):
        centre = sim.height_at(h.x, h.y)
        if h.thru:
            ok = centre <= -(spec.stock_z - 0.05)
            detail = f"hole {i} centre depth {-centre:.2f}mm vs stock {spec.stock_z:.2f}mm (through)"
        else:
            ok = abs(centre + h.depth) <= max(h.tol, slack)
            detail = f"hole {i} centre depth {-centre:.2f}mm vs required {h.depth:.2f}mm"
        rep.add(f"HOLE_{i}_DEPTH", ok, detail)
        gx, gy = h.x + h.diameter / 2 + 1.0, h.y
        if not _inside_other_feature(spec, gx, gy, h):
            guard = sim.height_at(gx, gy)
            rep.add(f"HOLE_{i}_DIAMETER", guard >= -0.4,
                    f"material 1mm outside hole {i} diameter is {'intact' if guard >= -0.4 else 'REMOVED - hole oversized or misplaced'}")

    for i, p in enumerate(spec.pockets, start=1):
        worst = float('-inf')
        x = p.x + 1.5
        while x <= p.x + p.width - 1.5:
            y = p.y + 1.5
            while y <= p.y + p.length - 1.5:
                worst = max(worst, sim.height_at(x, y))
                y += 2.0
            x += 2.0
        rep.add(f"POCKET_{i}_FLOOR", worst <= -p.depth + max(p.tol, slack),
                f"pocket {i} shallowest floor point {-worst:.2f}mm vs depth {p.depth:.2f}mm")
        guards = [(p.x + p.width / 2, p.y - 2.0), (p.x + p.width / 2, p.y + p.length + 2.0),
                  (p.x - 2.0, p.y + p.length / 2), (p.x + p.width + 2.0, p.y + p.length / 2)]
        bad = [(gx, gy) for gx, gy in guards
               if not _inside_other_feature(spec, gx, gy, p) and sim.height_at(gx, gy) < -0.4]
        rep.add(f"POCKET_{i}_WALLS", not bad,
                f"pocket {i} walls clean" if not bad else f"pocket {i} breaks its wall near ({bad[0][0]:.0f}, {bad[0][1]:.0f})")

    # --- gouge scan: material removed where the drawing has no feature ---
    import numpy as np
    ys, xs = np.mgrid[0:sim.ny, 0:sim.nx]
    cx, cy = xs * CELL, ys * CELL
    intended = np.zeros_like(sim.height, dtype=bool)
    for h in spec.holes:
        intended |= (cx - h.x) ** 2 + (cy - h.y) ** 2 <= (h.diameter / 2 + 0.6) ** 2
    for p in spec.pockets:
        intended |= (cx >= p.x - 0.6) & (cx <= p.x + p.width + 0.6) & (cy >= p.y - 0.6) & (cy <= p.y + p.length + 0.6)
    gouged = (sim.height < -0.35) & ~intended
    count = int(gouged.sum())
    if count:
        iy, ix = np.argwhere(gouged)[0]
        detail = f"{count} cells cut outside any feature, e.g. near ({ix * CELL:.1f}, {iy * CELL:.1f})"
    else:
        detail = "no material removed outside the drawn features"
    rep.add("NO_GOUGES", count == 0, detail)

    return rep
