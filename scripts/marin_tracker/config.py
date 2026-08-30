"""Pinned run and methodology configuration.

Numbers in this module are facts from a pinned upstream revision. They are kept
separate from rendering code so a page cannot silently invent a training fact.
"""

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HERO_RUN = "hero-12d8b6f0-dee637"
HERO_STEPS = 390_251
HERO_TOKENS = 18.0e12
TEAM_TERMINAL_PREDICTION = 2.04

METHOD_ID = "marin-matched-progress-v1"
RECIPE_REGIME_ID = "hero-4k-harrier-18t-v1"
ASYMPTOTE = 1.5
D2048_CORRECTION = 0.005
OFFICIAL_COMMIT = "d23e6e9c3673435fb82d83aa6c51a607d0da6009"
OFFICIAL_SCRIPT_URL = (
    "https://github.com/marin-community/marin/blob/"
    f"{OFFICIAL_COMMIT}/experiments/grug/moe_hero_ep/plot_scaling_ladder.py"
)
HERO_ISSUE_URL = "https://github.com/marin-community/marin/issues/8435"


@dataclass(frozen=True)
class RungSpec:
    name: str
    steps: int
    compute_per_step: float

    @property
    def full_compute(self):
        return self.steps * self.compute_per_step


# lm_head-excluded FLOPs copied from the pinned official analysis script.
RUNG_SPECS = {
    "d768": RungSpec("d768", 11_420, 2.320210052775936e15),
    "d1024": RungSpec("d1024", 15_276, 1.129954355970048e16),
    "d1536": RungSpec("d1536", 15_128, 9.130921800656486e16),
    "d2048": RungSpec("d2048", 20_072, 3.857022193930076e17),
    "d6144": RungSpec("d6144", HERO_STEPS, 6.690294608796058e18),
}

# A matched-progress comparison is only meaningful while the run still matches
# the registered Hero/Ladder regime. These checks are intentionally small and
# auditable: missing evidence yields ``unverified``; a changed value yields
# ``mismatch``. Rendering code never decides applicability on its own.
BASELINE_REQUIREMENTS = [
    {
        "id": "run_id",
        "selector": ["name"],
        "operator": "equals",
        "expected": HERO_RUN,
    },
    {
        "id": "context_length",
        "selector": ["config", "model", "max_seq_len"],
        "operator": "equals",
        "expected": 4096,
    },
    {
        "id": "registered_steps",
        "selector": ["config", "trainer", "trainer", "num_train_steps"],
        "operator": "equals",
        "expected": HERO_STEPS,
    },
    {
        "id": "tracker_group",
        "selector": ["config", "trainer", "trainer", "tracker", "group"],
        "operator": "equals",
        "expected": "moe-hero-ep-scaling-ladder",
    },
    {
        "id": "datamix_revision",
        "selector": ["tags"],
        "operator": "contains",
        "expected": "harrier-mix-2026.08.18",
    },
]

LADDER_GRID_PATH = ROOT / "data" / "ladder_eval_grid.json"
BASELINE_PATH = ROOT / "data" / "baselines" / "matched_progress_v1.json"
DERIVED_DIR = ROOT / "data" / "derived"
HERO_DATA_DIR = ROOT / "data" / "hero" / HERO_RUN
V2_REPORT_DIR = ROOT / "reports" / "generated" / "hero"
SITE_DIR = ROOT / "site"
WEB_DIR = ROOT / "web"
ISSUE_SNAPSHOT_PATH = ROOT / "data" / "snapshots" / "2026-08-28" / "github_issues.json"
