"""End-to-end tests: drawing -> Model A code -> Model B verdict."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.codegen import generate
from src.drawing import parse_drawing
from src.gcode import parse_program
from src.validator import validate

DRAWING = """
PART test-plate
STOCK 100 60 10
MATERIAL ALUMINUM 6061
HOLE D10 THRU AT 20 30 TOL 0.5
HOLE D10 THRU AT 80 30 TOL 0.5
POCKET 40 30 DEPTH 5 AT 30 15 TOL 0.5
"""


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.spec = parse_drawing(DRAWING)
        self.good_code = generate(self.spec)

    def test_drawing_parsed(self):
        self.assertEqual(self.spec.stock_x, 100)
        self.assertEqual(len(self.spec.holes), 2)
        self.assertEqual(len(self.spec.pockets), 1)
        self.assertTrue(self.spec.holes[0].thru)

    def test_codegen_emits_tool_table_and_moves(self):
        self.assertIn("(TOOL T1 DRILL D10)", self.good_code)
        self.assertIn("M30", self.good_code)
        prog = parse_program(self.good_code)
        self.assertEqual(prog.tools[1], 10.0)
        self.assertGreater(len(prog.moves), 50)
        self.assertEqual(prog.errors, [])

    def test_validator_passes_good_code(self):
        report = validate(self.spec, parse_program(self.good_code))
        self.assertTrue(report.passed, report.format())

    def test_validator_catches_shifted_hole(self):
        wrong = copy.deepcopy(self.spec)
        wrong.holes[0].x += 6.0
        report = validate(self.spec, parse_program(generate(wrong)))
        self.assertFalse(report.passed)
        failed = [c.name for c in report.checks if not c.ok]
        self.assertIn("HOLE_1_DEPTH", failed)

    def test_validator_catches_shallow_pocket(self):
        wrong = copy.deepcopy(self.spec)
        wrong.pockets[0].depth = 3.0
        report = validate(self.spec, parse_program(generate(wrong)))
        self.assertFalse(report.passed)
        failed = [c.name for c in report.checks if not c.ok]
        self.assertIn("POCKET_1_FLOOR", failed)

    def test_validator_catches_rapid_in_material(self):
        bad = self.good_code.replace("G0 Z5", "G0 Z-2", 1)
        report = validate(self.spec, parse_program(bad))
        self.assertFalse(report.passed)
        self.assertIn("NO_RAPID_IN_MATERIAL", [c.name for c in report.checks if not c.ok])


if __name__ == "__main__":
    unittest.main()
