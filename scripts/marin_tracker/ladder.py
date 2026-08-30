"""Faithful, dependency-free reproduction of Marin's matched-progress ladder.

The critical distinction is that the official method fits one cross-rung power
law at each 5% training fraction. It does *not* reuse the terminal fit as a
temporal learning curve.
"""

import math
from pathlib import Path

from .config import (
    ASYMPTOTE,
    BASELINE_REQUIREMENTS,
    D2048_CORRECTION,
    HERO_STEPS,
    METHOD_ID,
    OFFICIAL_COMMIT,
    OFFICIAL_SCRIPT_URL,
    RECIPE_REGIME_ID,
    ROOT,
    RUNG_SPECS,
)
from .io import read_json, sha256_file


def linear_fit(xs, ys):
    if len(xs) != len(ys) or len(xs) < 2:
        raise ValueError("linear_fit needs at least two paired points")
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        raise ValueError("cannot fit a line to identical x values")
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    return slope, y_mean - slope * x_mean


def _snap_eval_grid(raw_grid):
    snapped = {}
    for rung, rows in raw_grid.items():
        total_steps = RUNG_SPECS[rung].steps
        points = {}
        for step, loss in rows:
            if not math.isfinite(float(step)) or float(step) < 0:
                raise ValueError(f"{rung} has an invalid eval step: {step!r}")
            if not math.isfinite(float(loss)):
                raise ValueError(f"{rung} has a non-finite loss: {loss!r}")
            fraction = round(round(float(step) / total_steps * 20) / 20, 2)
            target_step = fraction * total_steps
            distance = abs(float(step) - target_step)
            candidate = (distance, int(step), float(loss))
            existing = points.get(fraction)
            if existing is None or distance < existing[0]:
                points[fraction] = candidate
            elif abs(distance - existing[0]) < 1e-9 and abs(float(loss) - existing[2]) > 1e-9:
                raise ValueError(
                    f"{rung} has conflicting evals equally close to {fraction:.0%}"
                )
        snapped[rung] = {fraction: row[2] for fraction, row in points.items()}
    return snapped


def _fit_power_law(computes, losses):
    excess = [loss - ASYMPTOTE for loss in losses]
    if any(value <= 0 for value in excess):
        raise ValueError("all losses must be greater than the fixed asymptote")
    slope, intercept = linear_fit(
        [math.log(value) for value in computes],
        [math.log(value) for value in excess],
    )
    return math.exp(intercept), -slope


def _predict(compute, coefficient, exponent):
    return ASYMPTOTE + coefficient * compute ** (-exponent)


def build_baseline(grid_path):
    """Build the full per-5% baseline and LOO sensitivity envelope."""
    raw_grid = read_json(grid_path)
    missing = set(RUNG_SPECS) - {"d6144"} - set(raw_grid)
    if missing:
        raise ValueError(f"missing ladder rungs: {sorted(missing)}")
    grid = _snap_eval_grid(raw_grid)
    d2048_window = [0.60, 0.65, 0.70, 0.75, 0.80]
    d2048_slope, d2048_intercept = linear_fit(
        d2048_window,
        [grid["d2048"][fraction] for fraction in d2048_window],
    )
    d2048_max = max(grid["d2048"])
    rung_names = ["d768", "d1024", "d1536", "d2048"]

    def loss_at(rung, fraction):
        if rung == "d2048" and fraction > d2048_max:
            return d2048_slope * fraction + d2048_intercept + D2048_CORRECTION
        return grid[rung][fraction]

    fractions = []
    for index in range(1, 21):
        fraction = round(index * 0.05, 2)
        rung_rows = []
        computes = []
        losses = []
        for rung in rung_names:
            compute = RUNG_SPECS[rung].full_compute * fraction
            loss = loss_at(rung, fraction)
            computes.append(compute)
            losses.append(loss)
            rung_rows.append(
                {
                    "rung": rung,
                    "compute_flops_no_lm_head": compute,
                    "loss": loss,
                    "status": (
                        "extrapolated_d2048" if rung == "d2048" and fraction > d2048_max else "observed"
                    ),
                }
            )
        coefficient, exponent = _fit_power_law(computes, losses)
        hero_compute = RUNG_SPECS["d6144"].full_compute * fraction
        prediction = _predict(hero_compute, coefficient, exponent)

        leave_one_out = []
        for omitted in range(len(rung_names)):
            loo_compute = [value for i, value in enumerate(computes) if i != omitted]
            loo_loss = [value for i, value in enumerate(losses) if i != omitted]
            loo_coefficient, loo_exponent = _fit_power_law(loo_compute, loo_loss)
            leave_one_out.append(
                {
                    "omitted_rung": rung_names[omitted],
                    "prediction": _predict(hero_compute, loo_coefficient, loo_exponent),
                }
            )

        loo_values = [row["prediction"] for row in leave_one_out]
        fractions.append(
            {
                "fraction": fraction,
                "progress_pct": round(fraction * 100, 1),
                "rungs": rung_rows,
                "fit": {"coefficient_A": coefficient, "exponent_alpha": exponent},
                "hero": {
                    "compute_flops_no_lm_head": hero_compute,
                    "prediction": prediction,
                    "sensitivity": {
                        "kind": "leave-one-rung-out range; not a confidence interval",
                        "low": min(loo_values),
                        "high": max(loo_values),
                        "fits": leave_one_out,
                    },
                },
            }
        )

    implementation_path = Path(__file__).resolve()
    source = {
        "upstream_commit": OFFICIAL_COMMIT,
        "upstream_script": OFFICIAL_SCRIPT_URL,
        "input_path": str(grid_path.resolve().relative_to(ROOT)),
        "input_sha256": sha256_file(grid_path),
        "implementation_path": str(implementation_path.relative_to(ROOT)),
        "implementation_sha256": sha256_file(implementation_path),
    }
    manifest_path = grid_path.with_name(f"{grid_path.stem}.manifest.json")
    if manifest_path.exists():
        source.update(
            {
                "input_manifest_path": str(manifest_path.resolve().relative_to(ROOT)),
                "input_manifest_sha256": sha256_file(manifest_path),
            }
        )

    baseline = {
        "schema_version": "1.0",
        "method_id": METHOD_ID,
        "description": "One fixed-asymptote cross-rung fit per 5% training fraction.",
        "source": source,
        "applicability": {
            "recipe_regime_id": RECIPE_REGIME_ID,
            "policy": "all requirements must be observed and match",
            "requirements": BASELINE_REQUIREMENTS,
        },
        "constants": {
            "asymptote": ASYMPTOTE,
            "d2048_correction": D2048_CORRECTION,
            "hero_steps": HERO_STEPS,
            "compute_excludes_lm_head": True,
        },
        "d2048_extrapolation": {
            "fit_window": d2048_window,
            "slope": d2048_slope,
            "intercept": d2048_intercept,
            "last_observed_fraction": d2048_max,
        },
        "fractions": fractions,
        "terminal_prediction": fractions[-1]["hero"]["prediction"],
    }
    validate_baseline(baseline)
    return baseline


def validate_baseline(baseline):
    rows = baseline.get("fractions", [])
    expected = [round(index * 0.05, 2) for index in range(1, 21)]
    actual = [row.get("fraction") for row in rows]
    if actual != expected:
        raise ValueError("baseline must contain an ordered 5%-100% grid")
    for row in rows:
        prediction = row.get("hero", {}).get("prediction")
        if prediction is None or not math.isfinite(float(prediction)):
            raise ValueError("baseline contains a non-finite Hero prediction")
    if not baseline.get("applicability", {}).get("requirements"):
        raise ValueError("baseline applicability requirements are missing")
    return True


def interpolate_prediction(baseline, step, total_steps=HERO_STEPS):
    """Interpolate adjacent official 5% point predictions for a Hero step."""
    validate_baseline(baseline)
    if not math.isfinite(float(step)) or float(step) < 0:
        raise ValueError("step must be a finite non-negative number")
    if not math.isfinite(float(total_steps)) or float(total_steps) <= 0:
        raise ValueError("total_steps must be a finite positive number")
    fraction = float(step) / total_steps
    rows = baseline["fractions"]
    first = rows[0]["fraction"]
    last = rows[-1]["fraction"]
    if fraction < first:
        return {
            "available": False,
            "fraction": fraction,
            "reason": "matched-progress baseline starts at 5%",
        }
    if fraction > last:
        return {
            "available": False,
            "fraction": fraction,
            "reason": "step is beyond the registered training budget",
        }

    left = rows[0]
    right = rows[-1]
    for row in rows:
        if row["fraction"] <= fraction + 1e-12:
            left = row
        if row["fraction"] >= fraction - 1e-12:
            right = row
            break
    span = right["fraction"] - left["fraction"]
    weight = 0.0 if abs(span) < 1e-12 else (fraction - left["fraction"]) / span

    def blend(path):
        a = path(left)
        b = path(right)
        return a + (b - a) * weight

    return {
        "available": True,
        "method": "linear interpolation between adjacent per-5% point predictions",
        "method_id": baseline["method_id"],
        "step": int(step),
        "fraction": fraction,
        "progress_pct": fraction * 100,
        "left_fraction": left["fraction"],
        "right_fraction": right["fraction"],
        "interpolation_weight": weight,
        "prediction": blend(lambda row: row["hero"]["prediction"]),
        "sensitivity_low": blend(lambda row: row["hero"]["sensitivity"]["low"]),
        "sensitivity_high": blend(lambda row: row["hero"]["sensitivity"]["high"]),
        "uncertainty_note": "leave-one-rung-out sensitivity range; not a confidence interval",
    }
