"""Machine-readable claims with explicit epistemic boundaries."""


KINDS = {"OBSERVED", "DERIVED", "INFERRED"}
SUPPORT_STATES = {"supported", "contradicted", "insufficient_evidence", "conflicted"}
CONFIDENCE_STATES = {"high", "medium", "low", "unassessed"}


def _evidence(status, artifact, metric_key=None, step=None, record_selector=None):
    row = {
        "artifact": status["artifacts"][artifact]["path"],
        "sha256": status["artifacts"][artifact]["sha256"],
    }
    if metric_key:
        row["metric_key"] = metric_key
    if step is not None:
        row["step"] = step
    if record_selector is not None:
        row["record_selector"] = record_selector
    return row


def build_claim_ledger(status):
    run = status["run"]
    latest = status["latest"]
    recipe = status["recipe"]
    claims = [
        {
            "id": "hero.run.progress",
            "kind": "DERIVED",
            "support": "supported",
            "statement": (
                f"Hero 当前证据截止 step {run['step']:,}，约为计划训练的 "
                f"{run['progress_pct']:.2f}%。"
            ),
            "as_of": status["data_as_of"],
            "value": run["progress_pct"],
            "unit": "percent",
            "evidence": [_evidence(status, "dense", "_step", run["step"])],
            "derivation": {
                "method_id": "step-divided-by-registered-total-v1",
                "equation": "progress_pct = step / total_steps * 100",
                "parameters": {"total_steps": run["total_steps"]},
            },
            "caveats": ["这是数据截止进度，不等于当前墙钟时刻的实时进度。"],
        },
        {
            "id": "hero.recipe.runtime",
            "kind": "OBSERVED",
            "support": "supported",
            "statement": (
                f"Run config 记录 LR schedule={recipe['learning_rate_schedule']}，"
                f"设备={recipe['device_variant']}，replicas={recipe['replicas']}，"
                f"每 replica 设备数={recipe['devices_per_replica']}。"
            ),
            "as_of": run["heartbeat_at"],
            "evidence": [_evidence(status, "meta")],
            "facts": {
                "learning_rate_schedule": recipe["learning_rate_schedule"],
                "device_variant": recipe["device_variant"],
                "replicas": recipe["replicas"],
                "devices_per_replica": recipe["devices_per_replica"],
            },
            "caveats": ["这是 run config 声明，不等于某一时刻的实际利用率。"],
        },
        {
            "id": "hero.recipe.configured-device-slots",
            "kind": "DERIVED",
            "support": "supported",
            "statement": (
                f"Run config 对应 {recipe['configured_device_slots']} 个 configured "
                "GB200 device slots。"
            ),
            "as_of": run["heartbeat_at"],
            "value": recipe["configured_device_slots"],
            "unit": "configured device slots",
            "evidence": [_evidence(status, "meta")],
            "derivation": {
                "method_id": "replicas-times-devices-per-replica-v1",
                "equation": "configured_device_slots = replicas * devices_per_replica",
                "parameters": {
                    "replicas": recipe["replicas"],
                    "devices_per_replica": recipe["devices_per_replica"],
                },
            },
            "caveats": [recipe["topology_note"]],
        },
    ]

    applicability = status["baseline_applicability"]
    applicability_support = {
        "supported": "supported",
        "mismatch": "contradicted",
        "unverified": "insufficient_evidence",
    }[applicability["status"]]
    claims.append(
        {
            "id": "hero.baseline.applicability",
            "kind": "DERIVED",
            "support": applicability_support,
            "statement": (
                f"Matched-progress baseline 适用性检查结果为 "
                f"{applicability['status']}；只有 supported 时才生成 residual。"
            ),
            "as_of": run["heartbeat_at"],
            "value": applicability["status"],
            "unit": "applicability status",
            "evidence": [_evidence(status, "meta"), _evidence(status, "baseline")],
            "derivation": {
                "method_id": "baseline-applicability-gate-v1",
                "recipe_regime_id": applicability["recipe_regime_id"],
                "checks": applicability["checks"],
            },
            "caveats": [
                "Missing required config is unverified, not an assumed match.",
                "A mismatch suppresses the matched-progress comparison.",
            ],
        }
    )

    paloma = latest.get("paloma_macro")
    comparison = status.get("matched_progress")
    if paloma:
        claims.append(
            {
                "id": f"hero.paloma.observed.step-{paloma['step']}",
                "kind": "OBSERVED",
                "support": "supported",
                "statement": (
                    f"step {paloma['step']:,} 的 dropless Paloma macro loss "
                    f"为 {paloma['value']:.5f}。"
                ),
                "as_of": paloma["observed_at"],
                "value": paloma["value"],
                "unit": "loss",
                "evidence": [
                    _evidence(
                        status,
                        "eval",
                        "eval_dropless/paloma/macro_loss",
                        paloma["step"],
                    )
                ],
                "caveats": ["这是 held-out eval，不是 train cross-entropy。"],
            }
        )
    if comparison:
        residual = comparison["residual"]
        if comparison["direction"] == "better_than_point_prediction":
            direction = "低"
            interpretation = (
                "当前点估计显示 Hero 实测低于 matched-progress 参考；"
                "但尚不能声称显著领先或保证终点达标。"
            )
        elif comparison["direction"] == "worse_than_point_prediction":
            direction = "高"
            interpretation = (
                "当前点估计显示 Hero 实测高于 matched-progress 参考；"
                "但尚不能断言已偏离轨道或预测终点结果。"
            )
        else:
            direction = "等于"
            interpretation = (
                "当前点估计与 matched-progress 参考相同；"
                "但这不构成终点保证或统计显著性结论。"
            )
        claims.extend(
            [
                {
                    "id": f"hero.paloma.matched-progress.step-{comparison['step']}",
                    "kind": "DERIVED",
                    "support": "supported",
                    "statement": (
                        f"step {comparison['step']:,} 的 Paloma 实测比 matched-progress "
                        + (
                            f"点预测{direction} {abs(residual):.5f}。"
                            if direction != "等于"
                            else "点预测相同。"
                        )
                    ),
                    "as_of": paloma["observed_at"],
                    "value": residual,
                    "unit": "loss residual (actual - prediction)",
                    "evidence": [
                        _evidence(
                            status,
                            "eval",
                            "eval_dropless/paloma/macro_loss",
                            comparison["step"],
                        ),
                        status["artifacts"]["baseline"],
                    ],
                    "derivation": {
                        "method_id": comparison["method_id"],
                        "method": comparison["method"],
                        "inputs": {
                            "actual": comparison["actual"],
                            "point_prediction": comparison["prediction"],
                            "left_fraction": comparison["left_fraction"],
                            "right_fraction": comparison["right_fraction"],
                        },
                    },
                    "uncertainty": {
                        "kind": "sensitivity_only",
                        "prediction_sensitivity_range": {
                            "low": comparison["sensitivity_low"],
                            "high": comparison["sensitivity_high"],
                        },
                        "residual_sensitivity_range": {
                            "low": comparison["actual"] - comparison["sensitivity_high"],
                            "high": comparison["actual"] - comparison["sensitivity_low"],
                        },
                        "significance": "not_assessed",
                    },
                    "caveats": [comparison["caveat"]],
                },
                {
                    "id": "hero.paloma.on-track-interpretation",
                    "kind": "INFERRED",
                    "support": "insufficient_evidence",
                    "statement": interpretation,
                    "as_of": paloma["observed_at"],
                    "evidence": [
                        {
                            "claim_id": f"hero.paloma.matched-progress.step-{comparison['step']}"
                        }
                    ],
                    "confidence": "low",
                    "alternative_explanations": [
                        "四个 rung 很少，外推对固定渐近线和 d2048 处理敏感。",
                        "未来 recipe、context length 或 datamix 变化会破坏当前 baseline 可比性。",
                    ],
                    "falsifiers": [
                        "后续同 recipe eval 持续高于敏感性范围。",
                        "发现当前 run 与 ladder 的 recipe regime 不一致。",
                    ],
                    "caveats": ["没有统计置信区间；不得渲染为“显著领先”。"],
                },
            ]
        )

    milestone = status["milestones"]["grad_norm_reference_25pct"]
    claims.append(
        {
            "id": "hero.grad-norm.25pct-reference",
            "kind": "DERIVED",
            "support": "supported",
            "statement": (
                "当前尚未到达 ladder 叙述中的约 25% grad-norm 参考区。"
                if milestone["status"] == "not_reached"
                else "当前已经越过 ladder 叙述中的约 25% grad-norm 参考区。"
            ),
            "as_of": status["data_as_of"],
            "evidence": [
                _evidence(status, "dense", "_step", run["step"]),
                _evidence(
                    status,
                    "hero_issue_snapshot",
                    record_selector={"number": 8435},
                ),
            ],
            "derivation": {
                "method_id": "progress-milestone-comparison-v1",
                "parameters": {"reference_progress_pct": 25},
            },
            "caveats": [
                "25% 是官方 issue 中的经验性观察，不是异常检测阈值或因果规律。"
            ],
        }
    )

    ledger = {
        "schema_version": "1.0",
        "generated_from_data_as_of": status["data_as_of"],
        "run_id": run["id"],
        "claims": claims,
    }
    validate_claim_ledger(ledger)
    return ledger


def validate_claim_ledger(ledger):
    errors = []
    seen = set()
    for claim in ledger.get("claims", []):
        claim_id = claim.get("id")
        if not claim_id or claim_id in seen:
            errors.append(f"missing or duplicate claim id: {claim_id!r}")
        seen.add(claim_id)
        kind = claim.get("kind")
        if kind not in KINDS:
            errors.append(f"{claim_id}: invalid kind {kind!r}")
        if claim.get("support") not in SUPPORT_STATES:
            errors.append(f"{claim_id}: invalid support {claim.get('support')!r}")
        if not claim.get("statement") or not claim.get("as_of"):
            errors.append(f"{claim_id}: statement and as_of are required")
        if not claim.get("evidence"):
            errors.append(f"{claim_id}: evidence is required")
        if kind == "DERIVED" and not claim.get("derivation"):
            errors.append(f"{claim_id}: DERIVED claim needs derivation")
        if kind == "INFERRED":
            for field in ("confidence", "alternative_explanations", "falsifiers", "caveats"):
                if not claim.get(field):
                    errors.append(f"{claim_id}: INFERRED claim needs {field}")
            if claim.get("confidence") not in CONFIDENCE_STATES:
                errors.append(f"{claim_id}: invalid confidence {claim.get('confidence')!r}")
    if errors:
        raise ValueError("invalid claim ledger:\n- " + "\n- ".join(errors))
    return True
