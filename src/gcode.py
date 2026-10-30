"""G-code parser shared by the simulator and Model B.

Reads a program into a list of moves with full machine state (position,
active tool, spindle). Tool diameters come from the program's own header
comments - e.g. (TOOL T1 DRILL D10) - so validation works from the code
alone, exactly what a checker on the shop floor would have.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_WORD = re.compile(r"([A-Z])\s*(-?\d+(?:\.\d+)?)")
_TOOL_COMMENT = re.compile(r"\(\s*TOOL\s+T(\d+)\s+(\w+)\s+D(\d+(?:\.\d+)?)\s*\)", re.I)


@dataclass
class Move:
    kind: str          # 'G0' rapid or 'G1' feed
    x0: float; y0: float; z0: float
    x1: float; y1: float; z1: float
    tool: int
    spindle_on: bool
    line: int


@dataclass
class Program:
    tools: dict[int, float] = field(default_factory=dict)  # tool no -> diameter
    moves: list[Move] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def parse_program(text: str) -> Program:
    prog = Program()
    for m in _TOOL_COMMENT.finditer(text):
        prog.tools[int(m.group(1))] = float(m.group(3))

    x = y = z = 0.0
    motion = "G0"
    tool = 0
    spindle = False
    for line_no, raw in enumerate(text.splitlines(), start=1):
        code = re.sub(r"\(.*?\)", "", raw).strip().upper()
        if not code:
            continue
        words = {letter: float(val) for letter, val in _WORD.findall(code)}
        if "T" in words and "M" in words and int(words["M"]) == 6:
            tool = int(words["T"])
        if "M" in words:
            if int(words["M"]) == 3:
                spindle = True
            elif int(words["M"]) in (5, 30):
                spindle = False
        if "G" in words:
            g = int(words["G"])
            if g in (0, 1):
                motion = f"G{g}"
            elif g in (2, 3):
                prog.errors.append(f"line {line_no}: arc moves (G{g}) not supported by this checker")
        if any(a in words for a in "XYZ"):
            nx, ny, nz = words.get("X", x), words.get("Y", y), words.get("Z", z)
            prog.moves.append(Move(motion, x, y, z, nx, ny, nz, tool, spindle, line_no))
            x, y, z = nx, ny, nz
    return prog
