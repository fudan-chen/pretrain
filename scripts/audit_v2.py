#!/usr/bin/env python3
"""Read-only audit lab for baseline applicability, sensitivity and claim direction."""

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from marin_tracker.claims import build_claim_ledger  # noqa: E402
from marin_tracker.config import HERO_RUN, LADDER_GRID_PATH  # noqa: E402
from marin_tracker.hero import assess_baseline_applicability, build_status  # noqa: E402
from marin_tracker.io import read_json  # noqa: E402
from marin_tracker.ladder import build_baseline  # noqa: E402


def audit(context_length=None, simulated_residual=None):
    baseline = build_baseline(LADDER_GRID_PATH)
    meta = read_json(ROOT / "data" / "hero" / HERO_RUN / "meta.json")
    if context_length is not None:
        meta["config"]["model"]["value"]["max_seq_len"] = context_length
    applicability = assess_baseline_applicability(meta, baseline)
    status = build_status(ROOT, baseline)
    comparison = status["matched_progress"]
    interpretation = None
    if simulated_residual is not None and comparison:
        status = copy.deepcopy(status)
        status["matched_progress"]["residual"] = simulated_residual
        status["matched_progress"]["direction"] = (
            "better_than_point_prediction"
            if simulated_residual < 0
            else "worse_than_point_prediction"
            if simulated_residual > 0
            else "equal_to_point_prediction"
        )
        ledger = build_claim_ledger(status)
        interpretation = next(
            claim["statement"]
            for claim in ledger["claims"]
            if claim["id"] == "hero.paloma.on-track-interpretation"
        )
    residual_range = None
    if comparison:
        residual_range = {
            "low": comparison["actual"] - comparison["sensitivity_high"],
            "high": comparison["actual"] - comparison["sensitivity_low"],
            "kind": "leave-one-rung-out sensitivity; not a confidence interval",
        }
    return {
        "baseline_fixtures": {
            str(row["progress_pct"]): row["hero"]["prediction"]
            for row in baseline["fractions"]
            if row["progress_pct"] in {5.0, 10.0, 100.0}
        },
        "applicability": applicability,
        "comparison_allowed_under_audited_context": applicability["status"] == "supported",
        "audited_context_comparison": (
            comparison if applicability["status"] == "supported" else None
        ),
        "current_comparison": comparison,
        "residual_sensitivity_range": residual_range,
        "simulated_residual": simulated_residual,
        "simulated_interpretation": interpretation,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-length", type=int)
    parser.add_argument("--simulated-residual", type=float)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            audit(args.context_length, args.simulated_residual),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
