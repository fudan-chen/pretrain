"""Turn local Hero evidence into a deterministic current-status model."""

import datetime as dt
import math

from .config import (
    BASELINE_PATH,
    HERO_ISSUE_URL,
    HERO_RUN,
    HERO_STEPS,
    HERO_TOKENS,
    ISSUE_SNAPSHOT_PATH,
    METHOD_ID,
)
from .io import (
    compact_series,
    metric_series,
    nested_value,
    read_json,
    read_jsonl,
    sha256_file,
)
from .ladder import interpolate_prediction


METRIC_KEYS = {
    "train_ce": "train/cross_entropy_loss",
    "grad_norm": "grad/norm/total",
    "learning_rate": "optim/learning_rate",
    "throughput": "throughput/tokens_per_second",
    "mfu": "throughput/mfu",
    "drop_fraction": "moe/drop_fraction",
    "paloma_macro": "eval_dropless/paloma/macro_loss",
    "router_bias_max": "train/router/bias_max",
    "router_overflow": "train/router/capacity_overflow_rate_mean",
}


def _iso_timestamp(timestamp):
    if timestamp is None:
        return None
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat()


def _latest(points, trained_only=False):
    usable = [point for point in points if not trained_only or point[0] > 0]
    if not usable:
        return None
    step, value, timestamp = usable[-1]
    return {"step": step, "value": value, "observed_at": _iso_timestamp(timestamp)}


def _series_payload(points):
    return [[step, value] for step, value, _timestamp in compact_series(points)]


def _config_fact(meta, section, key, default=None):
    return nested_value(meta, "config", section, key, default=default)


def _artifact(path, provider, sampling=None, root=None):
    display_path = path
    if root is not None:
        display_path = path.resolve().relative_to(root.resolve())
    return {
        "path": str(display_path),
        "sha256": sha256_file(path),
        "provider": provider,
        "sampling": sampling,
    }


def assess_baseline_applicability(meta, baseline):
    """Evaluate the baseline's registered recipe predicate against run meta."""
    policy = baseline.get("applicability", {})
    checks = []
    for requirement in policy.get("requirements", []):
        observed = nested_value(meta, *requirement["selector"])
        operator = requirement["operator"]
        expected = requirement["expected"]
        if observed is None:
            result = "unverified"
        elif operator == "equals":
            result = "match" if observed == expected else "mismatch"
        elif operator == "contains":
            if isinstance(observed, (str, list, tuple, set)):
                result = "match" if expected in observed else "mismatch"
            else:
                result = "unverified"
        else:
            raise ValueError(f"unknown applicability operator: {operator}")
        checks.append(
            {
                "id": requirement["id"],
                "selector": requirement["selector"],
                "operator": operator,
                "expected": expected,
                "observed": observed,
                "result": result,
            }
        )
    results = {check["result"] for check in checks}
    if "mismatch" in results:
        status = "mismatch"
    elif "unverified" in results or not checks:
        status = "unverified"
    else:
        status = "supported"
    return {
        "status": status,
        "recipe_regime_id": policy.get("recipe_regime_id"),
        "policy": policy.get("policy"),
        "checks": checks,
    }


def build_status(root, baseline):
    data_dir = root / "data" / "hero" / HERO_RUN
    dense_path = data_dir / "dense.jsonl"
    eval_path = data_dir / "eval.jsonl"
    router_path = data_dir / "router.jsonl"
    mixture_path = data_dir / "mixture.jsonl"
    meta_path = data_dir / "meta.json"

    dense = read_jsonl(dense_path)
    eval_rows = read_jsonl(eval_path)
    router = read_jsonl(router_path)
    mixture = read_jsonl(mixture_path)
    meta = read_json(meta_path)
    if not dense:
        raise ValueError("Hero dense history is empty")

    series = {
        "train_ce": metric_series(dense, METRIC_KEYS["train_ce"]),
        "grad_norm": metric_series(dense, METRIC_KEYS["grad_norm"]),
        "learning_rate": metric_series(dense, METRIC_KEYS["learning_rate"]),
        "throughput": metric_series(dense, METRIC_KEYS["throughput"]),
        "mfu": metric_series(dense, METRIC_KEYS["mfu"]),
        "drop_fraction": metric_series(dense, METRIC_KEYS["drop_fraction"]),
        "paloma_macro": metric_series(eval_rows, METRIC_KEYS["paloma_macro"]),
        "router_bias_max": metric_series(router, METRIC_KEYS["router_bias_max"]),
        "router_overflow": metric_series(router, METRIC_KEYS["router_overflow"]),
    }
    latest = {name: _latest(points) for name, points in series.items()}
    latest["paloma_macro"] = _latest(series["paloma_macro"], trained_only=True)
    current_step = latest["train_ce"]["step"]
    progress = current_step / HERO_STEPS
    applicability = assess_baseline_applicability(meta, baseline)

    comparison = None
    if latest["paloma_macro"] and applicability["status"] == "supported":
        prediction = interpolate_prediction(
            baseline, latest["paloma_macro"]["step"], HERO_STEPS
        )
        if prediction["available"]:
            comparison = dict(prediction)
            comparison["actual"] = latest["paloma_macro"]["value"]
            comparison["residual"] = comparison["actual"] - comparison["prediction"]
            if math.isclose(comparison["residual"], 0.0, abs_tol=1e-12):
                comparison["direction"] = "equal_to_point_prediction"
            elif comparison["residual"] < 0:
                comparison["direction"] = "better_than_point_prediction"
            else:
                comparison["direction"] = "worse_than_point_prediction"
            comparison["significance"] = "not_assessed"
            comparison["caveat"] = (
                "The sensitivity envelope is not a confidence interval; statistical "
                "significance is not established."
            )

    residual_series = []
    if applicability["status"] == "supported":
        for step, value, _timestamp in series["paloma_macro"]:
            if step <= 0:
                continue
            prediction = interpolate_prediction(baseline, step, HERO_STEPS)
            if prediction["available"]:
                residual_series.append([step, value - prediction["prediction"]])

    baseline_series = []
    if applicability["status"] == "supported":
        for row in baseline["fractions"]:
            step = round(row["fraction"] * HERO_STEPS)
            if step > current_step and row["fraction"] > progress + 0.05:
                break
            baseline_series.append(
                [
                    step,
                    row["hero"]["prediction"],
                    row["hero"]["sensitivity"]["low"],
                    row["hero"]["sensitivity"]["high"],
                ]
            )

    device = _config_fact(meta, "resources", "device", {}) or {}
    replicas = int(_config_fact(meta, "resources", "replicas", 0) or 0)
    devices_per_replica = int(device.get("count", 0) or 0)
    latest_mixture = mixture[-1] if mixture else {}
    data_timestamp = max(
        point[2]
        for point in series["train_ce"]
        if point[2] is not None
    )
    artifacts = {
        "dense": _artifact(
            dense_path,
            "wandb sampledHistory",
            "server sampled; complete_history=false",
            root,
        ),
        "eval": _artifact(
            eval_path,
            "wandb sampledHistory",
            "server sampled; complete_history=false",
            root,
        ),
        "router": _artifact(
            router_path,
            "wandb sampledHistory",
            "selected aggregate and edge-layer metrics",
            root,
        ),
        "meta": _artifact(meta_path, "wandb run metadata", root=root),
        "baseline": _artifact(
            BASELINE_PATH,
            "generated matched-progress baseline",
            "deterministic output from pinned grid and method",
            root,
        ),
        "baseline_grid": {
            "path": baseline["source"]["input_path"],
            "sha256": baseline["source"]["input_sha256"],
            "provider": "normalized Marin ladder grid input",
        },
        "hero_issue_snapshot": _artifact(
            ISSUE_SNAPSHOT_PATH,
            f"GitHub issue snapshot; upstream {HERO_ISSUE_URL}",
            "daily immutable snapshot; select issue number 8435",
            root,
        ),
    }
    manifest_relative = baseline["source"].get("input_manifest_path")
    if manifest_relative:
        manifest_path = root / manifest_relative
        artifacts["baseline_grid_manifest"] = _artifact(
            manifest_path, "ladder evidence collection manifest", root=root
        )
        manifest = read_json(manifest_path)
        for run in manifest.get("runs", []):
            source_path = root / run["source_path"]
            artifacts[f"ladder_source_{run['rung']}"] = _artifact(
                source_path,
                f"wandb sampledHistory for {run['display_name']}",
                "server sampled; complete_history=false",
                root,
            )

    return {
        "schema_version": "1.0",
        "method_id": METHOD_ID,
        "data_as_of": _iso_timestamp(data_timestamp),
        "run": {
            "id": HERO_RUN,
            "state": meta.get("state", "unknown"),
            "created_at": meta.get("createdAt"),
            "heartbeat_at": meta.get("heartbeatAt"),
            "freshness_threshold_hours": 18,
            "step": current_step,
            "total_steps": HERO_STEPS,
            "progress_pct": progress * 100,
            "tokens_trained": current_step / HERO_STEPS * HERO_TOKENS,
            "recipe_regime_id": (
                applicability["recipe_regime_id"]
                if applicability["status"] == "supported"
                else None
            ),
            "mixture_stage": latest_mixture.get("mixture/stage"),
        },
        "recipe": {
            "learning_rate_schedule": _config_fact(meta, "optimizer", "lr_schedule"),
            "warmup_fraction": _config_fact(meta, "optimizer", "warmup"),
            "decay": _config_fact(meta, "optimizer", "decay"),
            "device_kind": device.get("kind"),
            "device_variant": device.get("variant"),
            "replicas": replicas,
            "devices_per_replica": devices_per_replica,
            "configured_device_slots": replicas * devices_per_replica,
            "topology_note": (
                f"Run config declares {replicas} replicas × {devices_per_replica} "
                f"{device.get('variant')} devices. This is {replicas * devices_per_replica} "
                "configured device slots, not evidence of instantaneous utilization."
            ),
        },
        "latest": latest,
        "baseline_applicability": applicability,
        "matched_progress": comparison,
        "milestones": {
            "grad_norm_reference_25pct": {
                "status": "not_reached" if progress < 0.25 else "reached",
                "reference_only": True,
            },
            "mixture_phase_boundary_80pct": {
                "status": "not_reached" if progress < 0.80 else "reached"
            },
        },
        "series": {
            name: _series_payload(points) for name, points in series.items()
        }
        | {
            "matched_progress": baseline_series,
            "paloma_residual": residual_series,
        },
        "source_health": {
            "wandb_dense": "available",
            "wandb_eval": "available" if eval_rows else "missing",
            "wandb_router": "available" if router else "missing",
            "run_meta": "available",
            "baseline_applicability": applicability["status"],
            "ecosystem_evidence": "separate main snapshot pipeline",
        },
        "artifacts": artifacts,
    }
