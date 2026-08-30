"""Thin command-line orchestration for the v2 Hero tracker."""

import argparse

from .claims import build_claim_ledger
from .config import (
    BASELINE_PATH,
    DERIVED_DIR,
    HERO_DATA_DIR,
    HERO_RUN,
    LADDER_GRID_PATH,
    ROOT,
)
from .hero import build_status
from .io import atomic_write_json
from .ladder import build_baseline
from .render import build_site
from .reports import build_reports


def generate_baseline():
    baseline = build_baseline(LADDER_GRID_PATH)
    atomic_write_json(BASELINE_PATH, baseline)
    return baseline


def analyze(baseline=None):
    baseline = baseline or generate_baseline()
    status = build_status(ROOT, baseline)
    ledger = build_claim_ledger(status)
    atomic_write_json(DERIVED_DIR / "current_status.json", status)
    atomic_write_json(DERIVED_DIR / "claim_ledger.json", ledger)
    return status, ledger


def build_all():
    baseline = generate_baseline()
    status, ledger = analyze(baseline)
    report_index = build_reports(
        ROOT, baseline, status["data_as_of"], status["baseline_applicability"]
    )
    pages = build_site(ROOT, status, ledger, baseline, report_index)
    return {
        "baseline": str(BASELINE_PATH.relative_to(ROOT)),
        "status": str((DERIVED_DIR / "current_status.json").relative_to(ROOT)),
        "claims": str((DERIVED_DIR / "claim_ledger.json").relative_to(ROOT)),
        "reports": len(report_index["reports"]),
        "pages": pages,
    }


def collect():
    import pull_data

    return pull_data.pull_run(HERO_RUN, str(HERO_DATA_DIR), "hero")


def _parser():
    parser = argparse.ArgumentParser(
        description=(
            "Collect Marin Hero evidence and build audited matched-progress v2 outputs. "
            "The local `build` command performs no network requests."
        )
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True
    subparsers.add_parser("baseline", help="rebuild the five-percent matched-progress baseline")
    subparsers.add_parser("analyze", help="rebuild current status and the claim ledger")
    subparsers.add_parser("reports", help="rebuild corrected v2 Hero reports")
    subparsers.add_parser("site", help="rebuild the static learning site")
    subparsers.add_parser("build", help="rebuild all deterministic derived outputs")
    subparsers.add_parser("collect", help="refresh public W&B evidence only")
    subparsers.add_parser("update", help="refresh W&B evidence, then rebuild all v2 outputs")
    subparsers.add_parser("backfill", help="compatibility alias for deterministic v2 build")
    subparsers.add_parser("dashboard", help="compatibility alias for deterministic v2 build")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    if args.command == "baseline":
        baseline = generate_baseline()
        print(f"terminal prediction: {baseline['terminal_prediction']:.8f}")
        return 0
    if args.command == "analyze":
        status, ledger = analyze()
        comparison = status["matched_progress"]
        residual = (
            f"{comparison['residual']:+.8f}"
            if comparison is not None
            else "unavailable"
        )
        print(
            f"status step={status['run']['step']} claims={len(ledger['claims'])} "
            f"residual={residual}"
        )
        return 0
    if args.command in {"reports", "site", "build", "backfill", "dashboard"}:
        result = build_all()
        print(
            f"built {result['reports']} reports, {len(result['pages'])} pages, "
            f"and {result['claims']}"
        )
        return 0
    if args.command == "collect":
        summary = collect()
        print(summary)
        return 0
    if args.command == "update":
        summary = collect()
        result = build_all()
        print(f"collect={summary} build={result}")
        return 0
    raise AssertionError(f"unhandled command: {args.command}")
