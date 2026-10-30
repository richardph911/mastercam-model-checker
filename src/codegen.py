"""Model A, step 2 - build G-code from a PartSpec.

Strategy per feature (2.5D, linear moves only):
- Holes: a drill of the hole diameter, peck-plunged to depth.
- Pockets: a flat endmill running contour-parallel passes from the wall
  inward, in depth steps, plus a centre pass if a strip is left over.

The program carries a tool table in its header comments so Model B can
read tool diameters from the code itself, the same way a machinist
reads the setup sheet.
"""
from __future__ import annotations

from .drawing import PartSpec

SAFE_Z = 5.0
ENDMILL_DIA = 6.0


def _f(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def generate(spec: PartSpec) -> str:
    lines: list[str] = []
    out = lines.append
    out(f"(PART {spec.name})")
    out(f"(STOCK {_f(spec.stock_x)} X {_f(spec.stock_y)} X {_f(spec.stock_z)}  MATERIAL {spec.material})")

    # Tool table: one drill per hole diameter, one endmill if pockets exist.
    drills: dict[float, int] = {}
    tool_no = 0
    for h in spec.holes:
        if h.diameter not in drills:
            tool_no += 1
            drills[h.diameter] = tool_no
    endmill_tool = None
    if spec.pockets:
        tool_no += 1
        endmill_tool = tool_no
    for dia, tno in drills.items():
        out(f"(TOOL T{tno} DRILL D{_f(dia)})")
    if endmill_tool:
        out(f"(TOOL T{endmill_tool} ENDMILL D{_f(ENDMILL_DIA)})")

    out("G21 (MM)")
    out("G90 G17 G54")
    out("G40 G49 G80")

    for h in spec.holes:
        tno = drills[h.diameter]
        depth = h.required_depth(spec.stock_z)
        out(f"(HOLE D{_f(h.diameter)} AT {_f(h.x)} {_f(h.y)})")
        out(f"T{tno} M6")
        out("S1200 M3")
        out(f"G0 X{_f(h.x)} Y{_f(h.y)}")
        out(f"G0 Z{_f(SAFE_Z)}")
        steps = 3
        for i in range(1, steps + 1):
            out(f"G1 Z{_f(-depth * i / steps)} F120")
            if i < steps:
                out("G0 Z2")
                out(f"G0 X{_f(h.x)} Y{_f(h.y)}")
        out(f"G0 Z{_f(SAFE_Z)}")
        out("M5")

    for p in spec.pockets:
        r = ENDMILL_DIA / 2.0
        stepover = ENDMILL_DIA * 0.7
        out(f"(POCKET {_f(p.width)} X {_f(p.length)} DEPTH {_f(p.depth)} AT {_f(p.x)} {_f(p.y)})")
        out(f"T{endmill_tool} M6")
        out("S2400 M3")
        passes: list[float] = []
        d = r
        while d <= min(p.width, p.length) / 2.0:
            passes.append(d)
            d += stepover
        depth_steps = []
        z = 2.5
        while z < p.depth:
            depth_steps.append(z)
            z += 2.5
        depth_steps.append(p.depth)
        for inset in passes:
            x0, x1 = p.x + inset, p.x + p.width - inset
            y0, y1 = p.y + inset, p.y + p.length - inset
            out(f"G0 X{_f(x0)} Y{_f(y0)}")
            out(f"G0 Z{_f(SAFE_Z)}")
            for dep in depth_steps:
                out(f"G1 Z{_f(-dep)} F200")
                out(f"G1 X{_f(x1)} Y{_f(y0)} F600")
                out(f"G1 X{_f(x1)} Y{_f(y1)} F600")
                out(f"G1 X{_f(x0)} Y{_f(y1)} F600")
                out(f"G1 X{_f(x0)} Y{_f(y0)} F600")
            out(f"G0 Z{_f(SAFE_Z)}")
        # Centre strip pass if the contour steps left one behind.
        last = passes[-1] if passes else r
        if min(p.width, p.length) / 2.0 - last > 0.1:
            cy = p.y + p.length / 2.0
            out(f"G0 X{_f(p.x + r)} Y{_f(cy)}")
            out(f"G0 Z{_f(SAFE_Z)}")
            for dep in depth_steps:
                out(f"G1 Z{_f(-dep)} F200")
                out(f"G1 X{_f(p.x + p.width - r)} Y{_f(cy)} F600")
                out(f"G1 X{_f(p.x + r)} Y{_f(cy)} F600")
            out(f"G0 Z{_f(SAFE_Z)}")
        out("M5")

    out("G0 Z50")
    out("M30")
    return "\n".join(lines) + "\n"
