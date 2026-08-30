import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from marin_tracker.claims import build_claim_ledger, validate_claim_ledger  # noqa: E402
from marin_tracker.config import HERO_RUN, LADDER_GRID_PATH  # noqa: E402
from marin_tracker.hero import assess_baseline_applicability, build_status  # noqa: E402
from marin_tracker.io import read_json  # noqa: E402
from marin_tracker.ladder import build_baseline  # noqa: E402


class HeroAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = build_baseline(LADDER_GRID_PATH)
        cls.status = build_status(ROOT, cls.baseline)

    def test_runtime_facts_come_from_meta(self):
        recipe = self.status["recipe"]
        self.assertEqual(recipe["learning_rate_schedule"], "linear")
        self.assertEqual(recipe["device_variant"], "GB200")
        self.assertEqual(recipe["configured_device_slots"], 704)

    def test_baseline_applicability_is_executable(self):
        self.assertEqual(self.status["baseline_applicability"]["status"], "supported")
        meta = read_json(ROOT / "data" / "hero" / HERO_RUN / "meta.json")
        changed = copy.deepcopy(meta)
        changed["config"]["model"]["value"]["max_seq_len"] = 8192
        self.assertEqual(
            assess_baseline_applicability(changed, self.baseline)["status"], "mismatch"
        )
        missing = copy.deepcopy(meta)
        del missing["config"]["model"]["value"]["max_seq_len"]
        self.assertEqual(
            assess_baseline_applicability(missing, self.baseline)["status"], "unverified"
        )
        incompatible = copy.deepcopy(self.baseline)
        context_requirement = next(
            row
            for row in incompatible["applicability"]["requirements"]
            if row["id"] == "context_length"
        )
        context_requirement["expected"] = 8192
        gated_status = build_status(ROOT, incompatible)
        self.assertEqual(gated_status["baseline_applicability"]["status"], "mismatch")
        self.assertIsNone(gated_status["matched_progress"])

    def test_current_milestone_is_not_reached(self):
        self.assertLess(self.status["run"]["progress_pct"], 25)
        milestone = self.status["milestones"]["grad_norm_reference_25pct"]
        self.assertEqual(milestone["status"], "not_reached")

    def test_paloma_comparison_is_same_metric_and_negative(self):
        comparison = self.status["matched_progress"]
        self.assertEqual(comparison["step"], 32_999)
        self.assertLess(comparison["residual"], 0)
        self.assertEqual(comparison["direction"], "better_than_point_prediction")
        self.assertEqual(comparison["significance"], "not_assessed")
        self.assertAlmostEqual(comparison["prediction"], 2.3465101574845844, places=12)
        self.assertAlmostEqual(comparison["residual"], -0.06838582505660584, places=12)

    def test_claim_contract(self):
        ledger = build_claim_ledger(self.status)
        self.assertTrue(validate_claim_ledger(ledger))
        applicability = next(
            claim
            for claim in ledger["claims"]
            if claim["id"] == "hero.baseline.applicability"
        )
        self.assertEqual(applicability["value"], "supported")
        inferred = next(
            claim
            for claim in ledger["claims"]
            if claim["id"] == "hero.paloma.on-track-interpretation"
        )
        self.assertEqual(inferred["support"], "insufficient_evidence")
        self.assertEqual(inferred["confidence"], "low")

    def test_interpretation_changes_with_residual_direction(self):
        cases = [
            (-0.1, "better_than_point_prediction", "实测低于"),
            (0.1, "worse_than_point_prediction", "实测高于"),
            (0.0, "equal_to_point_prediction", "参考相同"),
        ]
        for residual, direction, phrase in cases:
            with self.subTest(direction=direction):
                status = copy.deepcopy(self.status)
                status["matched_progress"]["residual"] = residual
                status["matched_progress"]["direction"] = direction
                ledger = build_claim_ledger(status)
                inferred = next(
                    claim
                    for claim in ledger["claims"]
                    if claim["id"] == "hero.paloma.on-track-interpretation"
                )
                self.assertIn(phrase, inferred["statement"])

    def test_claim_validator_rejects_unknown_support(self):
        ledger = build_claim_ledger(self.status)
        ledger["claims"][0]["support"] = "banana"
        with self.assertRaisesRegex(ValueError, "invalid support"):
            validate_claim_ledger(ledger)

    def test_artifact_paths_are_repository_relative(self):
        for artifact in self.status["artifacts"].values():
            self.assertFalse(Path(artifact["path"]).is_absolute())


if __name__ == "__main__":
    unittest.main()
