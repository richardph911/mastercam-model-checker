"""Command-line application tying the two models together.

Usage:
  python -m src.app build    examples/plate.drawing [-o out/plate.nc]
  python -m src.app validate examples/plate.drawing out/plate.nc
  python -m src.app demo
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

from .codegen import generate
from .drawing import parse_drawing
from .gcode import parse_program
from .validator import validate


def _load_drawing(path: str):
    return parse_drawing(Path(path).read_text())


def cmd_build(args) -> int:
    spec = _load_drawing(args.drawing)
    code = generate(spec)
    out = Path(args.output) if args.output else Path("out") / (Path(args.drawing).stem + ".nc")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(code)
    print(f"Model A: read drawing '{spec.name}' "
          f"({len(spec.holes)} holes, {len(spec.pockets)} pockets) -> {out} "
          f"({len(code.splitlines())} lines of G-code)")
    return 0


def cmd_validate(args) -> int:
    spec = _load_drawing(args.drawing)
    prog = parse_program(Path(args.gcode).read_text())
    report = validate(spec, prog)
    print(f"Model B: validating {args.gcode} against drawing '{spec.name}'")
    print(report.format())
    return 0 if report.passed else 1


def _overlay_svg(spec, prog, path: Path) -> None:
    s = 4  # px per mm
    W, H = int(spec.stock_x * s), int(spec.stock_y * s)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
             f'<rect x="0" y="0" width="{W}" height="{H}" fill="#fafafa" stroke="#333"/>']
    for h in spec.holes:
        parts.append(f'<circle cx="{h.x * s}" cy="{H - h.y * s}" r="{h.diameter / 2 * s}" fill="none" stroke="#1565c0" stroke-width="1.5"/>')
    for p in spec.pockets:
        parts.append(f'<rect x="{p.x * s}" y="{H - (p.y + p.length) * s}" width="{p.width * s}" height="{p.length * s}" fill="none" stroke="#1565c0" stroke-width="1.5"/>')
    run: list[str] = []
    def flush():
        if len(run) > 1:
            parts.append(f'<polyline points="{" ".join(run)}" fill="none" stroke="#ef6c00" stroke-width="1"/>')
        run.clear()
    for mv in prog.moves:
        if mv.kind == "G1" and mv.z1 <= 0:
            if not run:
                run.append(f"{mv.x0 * s},{H - mv.y0 * s}")
            run.append(f"{mv.x1 * s},{H - mv.y1 * s}")
        else:
            flush()
    flush()
    parts.append("</svg>")
    path.write_text("\n".join(parts))


def cmd_demo(args) -> int:
    out = Path("out")
    out.mkdir(exist_ok=True)
    spec = _load_drawing("examples/plate.drawing")

    print("=" * 68)
    print("DEMO 1 - Model A builds, Model B validates the good program")
    print("=" * 68)
    code = generate(spec)
    (out / "plate.nc").write_text(code)
    print(f"Model A produced out/plate.nc ({len(code.splitlines())} lines)")
    good = validate(spec, parse_program(code))
    print(good.format())
    _overlay_svg(spec, parse_program(code), out / "overlay.svg")
    print("Toolpath overlay (design blue, toolpath orange): out/overlay.svg")

    print()
    print("=" * 68)
    print("DEMO 2 - Model A makes mistakes, Model B must catch them")
    print("        (hole 1 shifted +6mm in X, pocket cut 3mm instead of 5mm)")
    print("=" * 68)
    wrong = copy.deepcopy(spec)
    wrong.holes[0].x += 6.0
    wrong.pockets[0].depth = 3.0
    bad_code = generate(wrong)
    (out / "plate_bad.nc").write_text(bad_code)
    bad = validate(spec, parse_program(bad_code))
    print(bad.format())
    print()
    print(f"Demo result: good program {'PASSED' if good.passed else 'FAILED'} (expected PASS), "
          f"defective program {'PASSED' if bad.passed else 'FAILED'} (expected FAIL)")
    return 0 if good.passed and not bad.passed else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cam-model-checker", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("drawing"); b.add_argument("-o", "--output"); b.set_defaults(fn=cmd_build)
    v = sub.add_parser("validate"); v.add_argument("drawing"); v.add_argument("gcode"); v.set_defaults(fn=cmd_validate)
    d = sub.add_parser("demo"); d.set_defaults(fn=cmd_demo)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
