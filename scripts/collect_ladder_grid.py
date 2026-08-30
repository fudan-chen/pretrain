#!/usr/bin/env python3
"""Collect auditable rung evidence and rebuild ``ladder_eval_grid.json``.

This is an explicit network command. The ordinary v2 ``build`` remains fully
offline and deterministic.
"""

import datetime as dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import marin_wandb as wandb  # noqa: E402
from marin_tracker.config import (  # noqa: E402
    LADDER_GRID_PATH,
    OFFICIAL_COMMIT,
    OFFICIAL_SCRIPT_URL,
    ROOT,
)
from marin_tracker.io import (  # noqa: E402
    atomic_write_json,
    atomic_write_text,
    nested_value,
    sha256_file,
)


ENTITY = "marin-community"
PROJECT = "marin_moe"
METRIC = "eval_dropless/paloma/macro_loss"
RUN_DISPLAY_NAMES = {
    "d768": "rav-ladder-d768-v2",
    "d1024": "rav-ladder-d1024",
    "d1536": "rav-ladder-d1536",
    "d2048": "rav-ladder-d2048-v3",
}


def _resolve_run(display_name):
    rows = wandb.list_runs(ENTITY, PROJECT, f"^{re.escape(display_name)}$")
    exact = [row for row in rows if row.get("displayName") == display_name]
    if len(exact) != 1:
        raise RuntimeError(
            f"expected exactly one W&B run named {display_name!r}; found {len(exact)}"
        )
    return exact[0]["name"]


def _select_grid(rows, total_steps):
    selected = {}
    for row in rows:
        if row.get("_step") is None or row.get(METRIC) is None:
            continue
        step = int(row["_step"])
        loss = float(row[METRIC])
        if step < 0 or not math.isfinite(loss):
            raise ValueError(f"invalid rung evidence row: step={step!r}, loss={loss!r}")
        fraction = round(round(step / total_steps * 20) / 20, 2)
        if not 0.05 <= fraction <= 1.0:
            continue
        distance = abs(step - fraction * total_steps)
        candidate = (distance, step, loss)
        existing = selected.get(fraction)
        if existing is None or distance < existing[0]:
            selected[fraction] = candidate
        elif distance == existing[0] and (
            step != existing[1]
            or not math.isclose(loss, existing[2], rel_tol=0.0, abs_tol=1e-12)
        ):
            raise ValueError(
                f"conflicting rung evals equally close to {fraction:.0%}: "
                f"{existing[1:]} and {(step, loss)}"
            )
    return [[row[1], row[2]] for _fraction, row in sorted(selected.items())]


def collect():
    source_dir = ROOT / "data" / "ladder" / "source"
    grid = {}
    run_manifest = []
    source_payloads = {}
    for rung, display_name in RUN_DISPLAY_NAMES.items():
        run_id = _resolve_run(display_name)
        meta = wandb.run_meta(ENTITY, PROJECT, run_id)
        total_steps = int(nested_value(meta, "config", "stop_after_steps"))
        if total_steps <= 0:
            raise ValueError(f"{display_name} has invalid stop_after_steps={total_steps}")
        rows = wandb.sampled(
            ENTITY,
            PROJECT,
            run_id,
            [{"keys": ["_step", "_timestamp", METRIC], "samples": 100000}],
        )[0]
        rows = sorted(
            (row for row in rows if row.get("_step") is not None),
            key=lambda row: row["_step"],
        )
        source_path = source_dir / f"{rung}.jsonl"
        source_text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        source_payloads[source_path] = source_text
        grid[rung] = _select_grid(rows, total_steps)
        expected_rows = 16 if rung == "d2048" else 20
        if len(grid[rung]) != expected_rows:
            raise RuntimeError(
                f"{display_name} produced {len(grid[rung])} grid rows; "
                f"expected {expected_rows}"
            )
        run_manifest.append(
            {
                "rung": rung,
                "display_name": display_name,
                "run_id": run_id,
                "state": meta.get("state"),
                "heartbeat_at": meta.get("heartbeatAt"),
                "stop_after_steps": total_steps,
                "source_path": str(source_path.relative_to(ROOT)),
                "source_sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                "sampled_rows": len(rows),
                "selected_grid_rows": len(grid[rung]),
            }
        )

    # Publication begins only after all four network reads and grid validations
    # have succeeded. A mid-collection network failure therefore leaves the
    # previously committed evidence set untouched.
    for source_path, source_text in source_payloads.items():
        atomic_write_text(source_path, source_text)
    atomic_write_json(LADDER_GRID_PATH, grid)
    manifest_path = LADDER_GRID_PATH.with_name(f"{LADDER_GRID_PATH.stem}.manifest.json")
    atomic_write_json(
        manifest_path,
        {
            "schema_version": "1.0",
            "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "provider": "W&B public GraphQL sampledHistory",
            "entity_project": f"{ENTITY}/{PROJECT}",
            "metric": METRIC,
            "sampling": {"samples": 100000, "complete_history": False},
            "normalization": (
                "snap step/stop_after_steps to nearest 5%; choose the closest "
                "sample to each target step"
            ),
            "upstream_commit": OFFICIAL_COMMIT,
            "upstream_script": OFFICIAL_SCRIPT_URL,
            "grid_path": str(LADDER_GRID_PATH.relative_to(ROOT)),
            "grid_sha256": sha256_file(LADDER_GRID_PATH),
            "runs": run_manifest,
            "limitations": [
                "sampledHistory is server-sampled and is not claimed to be full history.",
                "The pinned upstream script is the authority for run selection and method constants.",
            ],
        },
    )
    return {"grid": str(LADDER_GRID_PATH), "runs": len(run_manifest)}


if __name__ == "__main__":
    print(collect())
