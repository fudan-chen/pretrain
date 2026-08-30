import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_v2 import audit  # noqa: E402
from collect_ladder_grid import METRIC, _select_grid  # noqa: E402


class AuditLabTests(unittest.TestCase):
    def test_context_mismatch_suppresses_audited_comparison(self):
        result = audit(context_length=8192)
        self.assertEqual(result["applicability"]["status"], "mismatch")
        self.assertFalse(result["comparison_allowed_under_audited_context"])
        self.assertIsNone(result["audited_context_comparison"])

    def test_simulated_residual_changes_interpretation(self):
        positive = audit(simulated_residual=0.1)
        negative = audit(simulated_residual=-0.1)
        equal = audit(simulated_residual=0.0)
        self.assertIn("实测高于", positive["simulated_interpretation"])
        self.assertIn("实测低于", negative["simulated_interpretation"])
        self.assertIn("参考相同", equal["simulated_interpretation"])

    def test_ladder_collector_selects_closest_grid_point(self):
        rows = [
            {"_step": 4, METRIC: 2.5},
            {"_step": 5, METRIC: 2.4},
            {"_step": 11, METRIC: 2.3},
        ]
        self.assertEqual(_select_grid(rows, 100), [[5, 2.4], [11, 2.3]])

    def test_ladder_collector_rejects_ambiguous_tie(self):
        rows = [
            {"_step": 4, METRIC: 2.5},
            {"_step": 6, METRIC: 2.4},
        ]
        with self.assertRaisesRegex(ValueError, "conflicting rung evals"):
            _select_grid(rows, 100)


if __name__ == "__main__":
    unittest.main()
