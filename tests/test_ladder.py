import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from marin_tracker.config import HERO_STEPS, LADDER_GRID_PATH  # noqa: E402
from marin_tracker.ladder import build_baseline, interpolate_prediction  # noqa: E402


class MatchedProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = build_baseline(LADDER_GRID_PATH)

    def prediction_at_fraction(self, fraction):
        row = next(
            row for row in self.baseline["fractions"] if row["fraction"] == fraction
        )
        return row["hero"]["prediction"]

    def test_official_fixtures(self):
        self.assertAlmostEqual(self.prediction_at_fraction(0.05), 2.3920926134624465, places=12)
        self.assertAlmostEqual(self.prediction_at_fraction(0.10), 2.3261427192062980, places=12)
        self.assertAlmostEqual(self.prediction_at_fraction(1.00), 2.0387845986743045, places=12)

    def test_d2048_terminal_extrapolation(self):
        terminal = self.baseline["fractions"][-1]
        d2048 = next(row for row in terminal["rungs"] if row["rung"] == "d2048")
        self.assertEqual(d2048["status"], "extrapolated_d2048")
        self.assertAlmostEqual(d2048["loss"], 2.4087081241607664, places=12)

    def test_d2048_observed_extrapolated_boundary(self):
        at_80 = next(row for row in self.baseline["fractions"] if row["fraction"] == 0.80)
        at_85 = next(row for row in self.baseline["fractions"] if row["fraction"] == 0.85)
        d2048_80 = next(row for row in at_80["rungs"] if row["rung"] == "d2048")
        d2048_85 = next(row for row in at_85["rungs"] if row["rung"] == "d2048")
        self.assertEqual(d2048_80["status"], "observed")
        self.assertEqual(d2048_85["status"], "extrapolated_d2048")

    def test_step_32999_direction_cannot_flip(self):
        prediction = interpolate_prediction(self.baseline, 32_999, HERO_STEPS)
        self.assertTrue(prediction["available"])
        self.assertAlmostEqual(prediction["prediction"], 2.3465101574845844, places=12)
        residual = 2.2781243324279785 - prediction["prediction"]
        self.assertAlmostEqual(residual, -0.06838582505660584, places=12)
        self.assertLess(residual, 0)

    def test_before_five_percent_is_unavailable(self):
        prediction = interpolate_prediction(self.baseline, 1_000, HERO_STEPS)
        self.assertFalse(prediction["available"])
        self.assertIn("5%", prediction["reason"])

    def test_after_registered_budget_is_unavailable(self):
        prediction = interpolate_prediction(self.baseline, HERO_STEPS + 1, HERO_STEPS)
        self.assertFalse(prediction["available"])

    def test_invalid_numeric_boundaries_raise(self):
        for step in (-1, float("nan"), float("inf")):
            with self.subTest(step=step), self.assertRaises(ValueError):
                interpolate_prediction(self.baseline, step, HERO_STEPS)
        for total in (0, -1, float("nan")):
            with self.subTest(total=total), self.assertRaises(ValueError):
                interpolate_prediction(self.baseline, 1000, total)


if __name__ == "__main__":
    unittest.main()
