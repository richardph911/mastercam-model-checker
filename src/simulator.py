"""Material-removal simulation (2.5D heightmap).

The stock is a grid of columns. Every feed move sweeps the active tool
along its path and lowers each column the tool covers to the move's Z.
The resulting heightmap is the virtual finished part - what the code
*would* make - which Model B then measures against the drawing.
Rapid (G0) moves never remove material.
"""
from __future__ import annotations

import math

import numpy as np

from .drawing import PartSpec
from .gcode import Program

CELL = 0.25  # mm per grid cell


class Simulation:
    def __init__(self, spec: PartSpec):
        self.spec = spec
        self.nx = int(round(spec.stock_x / CELL)) + 1
        self.ny = int(round(spec.stock_y / CELL)) + 1
        self.height = np.zeros((self.ny, self.nx))  # top surface height, Z0 = 0
        self.rapid_events: list[tuple[int, str]] = []

    def _check_rapid(self, mv) -> None:
        # A rapid is dangerous if it travels sideways while below the top
        # surface, or descends into material that is still there. A pure
        # vertical retract out of a cut is normal and allowed.
        import math as _math
        if _math.dist((mv.x0, mv.y0), (mv.x1, mv.y1)) > 1e-9 and min(mv.z0, mv.z1) < 0:
            self.rapid_events.append((mv.line, "rapid move travels sideways below the surface"))
        elif mv.z1 < mv.z0 and mv.z1 < self.height_at(mv.x1, mv.y1) - 0.01:
            self.rapid_events.append((mv.line, "rapid move descends into material"))

    def height_at(self, x: float, y: float) -> float:
        ix = min(max(int(round(x / CELL)), 0), self.nx - 1)
        iy = min(max(int(round(y / CELL)), 0), self.ny - 1)
        return float(self.height[iy, ix])

    def _stamp(self, x: float, y: float, z: float, r: float) -> None:
        x0 = max(int((x - r) / CELL), 0); x1 = min(int((x + r) / CELL) + 1, self.nx)
        y0 = max(int((y - r) / CELL), 0); y1 = min(int((y + r) / CELL) + 1, self.ny)
        if x0 >= x1 or y0 >= y1:
            return
        ys, xs = np.mgrid[y0:y1, x0:x1]
        mask = (xs * CELL - x) ** 2 + (ys * CELL - y) ** 2 <= r * r
        region = self.height[y0:y1, x0:x1]
        region[mask] = np.minimum(region[mask], z)

    def run(self, prog: Program) -> "Simulation":
        for mv in prog.moves:
            if mv.kind == "G0":
                self._check_rapid(mv)
                continue
            dia = prog.tools.get(mv.tool, 6.0)
            r = dia / 2.0
            dist = math.dist((mv.x0, mv.y0, mv.z0), (mv.x1, mv.y1, mv.z1))
            steps = max(1, int(dist / (CELL / 2)))
            for i in range(steps + 1):
                t = i / steps
                x = mv.x0 + (mv.x1 - mv.x0) * t
                y = mv.y0 + (mv.y1 - mv.y0) * t
                z = mv.z0 + (mv.z1 - mv.z0) * t
                if z < 0:
                    self._stamp(x, y, z, r)
        return self
