"""Model A, step 1 - read a drawing into a structured part specification.

The drawing format is a plain-text stand-in for an engineering print: one
annotation per line (stock size, a hole callout, a pocket callout) with
dimensions and tolerances - the same information a machinist reads off a
paper drawing. A production version would extract this from PDF / DXF /
STEP instead. The PartSpec produced here is the contract that Model B
later validates against, so it is kept independent of the code builder.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Hole:
    diameter: float
    x: float
    y: float
    thru: bool = True
    depth: float | None = None  # blind holes only
    tol: float = 0.5

    def required_depth(self, stock_z: float) -> float:
        """How deep the cut must reach, measured from the top face (Z0)."""
        if self.thru:
            return stock_z + 1.0  # break through the back face
        return float(self.depth)


@dataclass
class Pocket:
    width: float   # X size
    length: float  # Y size
    depth: float
    x: float       # lower-left corner
    y: float
    tol: float = 0.5


@dataclass
class PartSpec:
    name: str = "part"
    stock_x: float = 0.0
    stock_y: float = 0.0
    stock_z: float = 0.0
    material: str = ""
    holes: list[Hole] = field(default_factory=list)
    pockets: list[Pocket] = field(default_factory=list)


def _num(token: str, line_no: int) -> float:
    try:
        return float(token)
    except ValueError:
        raise ValueError(f"line {line_no}: expected a number, got {token!r}")


def parse_drawing(text: str) -> PartSpec:
    """Parse drawing text into a PartSpec. Raises ValueError on bad input."""
    spec = PartSpec()
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tok = line.upper().split()
        head = tok[0]
        if head == "PART":
            spec.name = line.split(None, 1)[1].strip()
        elif head == "STOCK":
            if len(tok) != 4:
                raise ValueError(f"line {line_no}: STOCK needs L W T")
            spec.stock_x, spec.stock_y, spec.stock_z = (_num(t, line_no) for t in tok[1:4])
        elif head == "MATERIAL":
            spec.material = line.split(None, 1)[1].strip()
        elif head == "HOLE":
            # HOLE D10 THRU AT 20 30 TOL 0.5   |   HOLE D6 DEPTH 4 AT 15 15
            if len(tok) < 7 or not tok[1].startswith("D"):
                raise ValueError(f"line {line_no}: bad HOLE callout: {raw.strip()!r}")
            dia = _num(tok[1][1:], line_no)
            thru = tok[2] == "THRU"
            depth = None if thru else _num(tok[3], line_no)
            at = tok.index("AT")
            x, y = _num(tok[at + 1], line_no), _num(tok[at + 2], line_no)
            tol = _num(tok[tok.index("TOL") + 1], line_no) if "TOL" in tok else 0.5
            spec.holes.append(Hole(dia, x, y, thru, depth, tol))
        elif head == "POCKET":
            # POCKET 40 30 DEPTH 5 AT 30 15 TOL 0.5
            if len(tok) < 9:
                raise ValueError(f"line {line_no}: bad POCKET callout: {raw.strip()!r}")
            w, l = _num(tok[1], line_no), _num(tok[2], line_no)
            depth = _num(tok[tok.index("DEPTH") + 1], line_no)
            at = tok.index("AT")
            x, y = _num(tok[at + 1], line_no), _num(tok[at + 2], line_no)
            tol = _num(tok[tok.index("TOL") + 1], line_no) if "TOL" in tok else 0.5
            spec.pockets.append(Pocket(w, l, depth, x, y, tol))
        else:
            raise ValueError(f"line {line_no}: unknown annotation {head!r}")
    if spec.stock_x <= 0 or spec.stock_y <= 0 or spec.stock_z <= 0:
        raise ValueError("drawing is missing a valid STOCK line")
    return spec
