# Mastercam Model Checker

A two-model pipeline for CNC programming, built on one principle:
**the model that checks must not trust the model that builds.**

- **Model A — understands the drawing, builds the code.**
  Reads a dimensioned drawing into a structured part specification
  (features, dimensions, tolerances), plans operations, and generates
  G-code.
- **Model B — validates the builder.**
  Takes only the original drawing and the finished G-code. It replays
  the code through a material-removal simulator, measures the virtual
  part against the drawing feature by feature, runs machine-safety
  checks on the code itself, and issues a pass/fail report that points
  at exactly what is wrong.

Model B deliberately validates against the *original drawing*, never
against Model A's interpretation of it — if A misreads a dimension and
B checks against A's reading, both agree and the part is still wrong.

This is an independent prototype. It is not affiliated with Mastercam;
it works with plain G-code, so its output can be compared against a
Mastercam program for the same part.

> **Safety:** this is a research prototype. Never run generated G-code
> on a real machine without verifying it in a full machine simulator
> and reviewing it like any unproven program.

## Quick start

```bash
pip install -r requirements.txt

# Full demo: Model A builds a program, Model B passes it;
# then Model A "makes mistakes" and Model B must catch them.
python -m src.app demo

# Build G-code from a drawing
python -m src.app build examples/plate.drawing -o out/plate.nc

# Validate any G-code file against a drawing
python -m src.app validate examples/plate.drawing out/plate.nc
python -m src.app validate examples/plate.drawing examples/plate_bad.nc   # expected: FAIL

# Tests
python -m unittest discover -s tests -v
```

## The drawing format

A plain-text stand-in for an engineering print — one annotation per
line, the same information a machinist reads off a drawing:

```
PART demo-plate
STOCK 100 60 10
MATERIAL ALUMINUM 6061
HOLE D10 THRU AT 20 30 TOL 0.5
HOLE D10 THRU AT 80 30 TOL 0.5
POCKET 40 30 DEPTH 5 AT 30 15 TOL 0.5
```

## What Model B checks

| Check | Meaning |
| --- | --- |
| PARSE | Program parses; unsupported constructs are reported |
| NO_RAPID_IN_MATERIAL | No G0 rapid moves below the top surface |
| NO_CUT_OUTSIDE_STOCK | No cutting move leaves the stock |
| SPINDLE_ON_WHILE_CUTTING | Spindle is on for every cut below Z0 |
| HOLE_n_DEPTH | Hole reaches its required depth (through / blind) |
| HOLE_n_DIAMETER | Material just outside the hole diameter is intact |
| POCKET_n_FLOOR | Every point of the pocket floor reaches full depth |
| POCKET_n_WALLS | The pocket does not break outside its walls |
| NO_GOUGES | No material removed where the drawing has no feature |

The demo also writes `out/overlay.svg`: the design (blue) against the
generated toolpaths (orange).

## Layout

```
src/drawing.py    drawing text -> PartSpec (the contract)
src/codegen.py    Model A: PartSpec -> G-code
src/gcode.py      G-code parser (moves, tools, spindle state)
src/simulator.py  2.5D heightmap material-removal simulation
src/validator.py  Model B: checks + pass/fail report
src/app.py        CLI: build / validate / demo
examples/         sample drawing + a deliberately defective program
tests/            end-to-end pipeline tests
```

## Limitations and roadmap

Prototype limits: 2.5D parts (plates with holes and rectangular
pockets), linear moves only (no G2/G3 arcs yet), one setup, tool
diameters read from program header comments, simulation grid 0.25 mm.

Roadmap: extract the spec from real drawings (PDF/DXF/STEP, GD&T),
arc support, 3D stock simulation, toolpath import from CAM exports,
and ML risk flags trained on inspection outcomes (chatter, deflection,
tool wear) on top of the deterministic geometry checks.
