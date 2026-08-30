"""Generate corrected v2 Hero reports from local evidence only."""

import datetime as dt

from .config import BASELINE_PATH, HERO_RUN, HERO_STEPS
from .io import atomic_write_json, atomic_write_text, metric_series, read_jsonl, sha256_file
from .ladder import interpolate_prediction


UTC = dt.timezone.utc
BEIJING = dt.timezone(dt.timedelta(hours=8))


def _utc(timestamp):
    return dt.datetime.fromtimestamp(timestamp, UTC)


def _beijing(timestamp):
    return dt.datetime.fromtimestamp(timestamp, BEIJING)


def complete_windows(start_timestamp, end_timestamp):
    """Return complete UTC 00:00/12:00 windows covered by the evidence."""
    start = _utc(start_timestamp)
    boundary = start.replace(hour=0, minute=0, second=0, microsecond=0)
    if boundary <= start:
        boundary += dt.timedelta(hours=12)
    if boundary <= start:
        boundary += dt.timedelta(hours=12)
    windows = []
    window_start = start_timestamp
    while boundary.timestamp() <= end_timestamp:
        window_end = boundary.timestamp()
        local_end = _beijing(window_end)
        half = "am" if local_end.hour == 8 else "pm"
        name = f"{local_end.date().isoformat()}-{half}"
        windows.append((name, window_start, window_end))
        window_start = window_end
        boundary += dt.timedelta(hours=12)
    return windows


def _in_window(points, start, end):
    return [point for point in points if point[2] is not None and start <= point[2] < end]


def _summary(points):
    if not points:
        return None
    return {
        "step_first": points[0][0],
        "step_last": points[-1][0],
        "value_first": points[0][1],
        "value_last": points[-1][1],
        "observed_at_first": _utc(points[0][2]).isoformat(),
        "observed_at_last": _utc(points[-1][2]).isoformat(),
        "count": len(points),
    }


def _render_report(entry, previous_name, next_name):
    stats = entry["stats"]
    lines = [
        f"# Hero Run v2 日报 · {entry['name']}",
        "",
        "> 本日报由 v2 可审计分析管道生成。旧版 `reports/daily/` 保留用于方法对比。",
        "",
        f"- 数据窗口：{entry['window_beijing'][0]} → {entry['window_beijing'][1]}（北京时间）",
        f"- Run：`{HERO_RUN}`",
        f"- 方法：`{entry['method_id']}`",
        f"- 本窗口证据截止：{entry['window_evidence_as_of']}",
        f"- 整份数据集截止：{entry['dataset_as_of']}",
        f"- Baseline SHA-256：`{entry['baseline_sha256']}`",
        f"- Baseline applicability：`{entry['baseline_applicability']}`",
        "",
        "## 本窗口事实",
        "",
        "| 证据等级 | 指标 | 结果 |",
        "|---|---|---|",
    ]
    train = stats.get("train_ce")
    if train:
        lines.append(
            f"| OBSERVED | `train/cross_entropy_loss` | step {train['step_first']:,} 的 "
            f"{train['value_first']:.4f} → step {train['step_last']:,} 的 {train['value_last']:.4f} |"
        )
    for key, label, unit in [
        ("grad_norm", "`grad/norm/total` 最大值", ""),
        ("throughput", "`throughput/tokens_per_second` 均值", " tok/s"),
        ("mfu", "`throughput/mfu` 均值", "%"),
        ("drop_fraction", "`moe/drop_fraction` 最大值", ""),
    ]:
        value = stats.get(key)
        if value is not None:
            lines.append(f"| DERIVED | {label} | {value:.5g}{unit} |")

    lines.extend(["", "## Matched-progress 比较", ""])
    comparison = entry.get("matched_progress")
    if comparison:
        direction = (
            "低于"
            if comparison["residual"] < 0
            else "高于"
            if comparison["residual"] > 0
            else "等于"
        )
        lines.extend(
            [
                f"- **OBSERVED**：step {comparison['step']:,} 的 "
                f"`eval_dropless/paloma/macro_loss` = **{comparison['actual']:.5f}**。",
                f"- **DERIVED**：同进度点预测 = **{comparison['prediction']:.5f}**；"
                f"residual = actual − prediction = **{comparison['residual']:+.5f}**，即实测{direction}点预测。",
                f"- **LIMIT**：{comparison['uncertainty_note']}，因此不能写成“显著领先”或“确定偏离”。",
            ]
        )
    else:
        if entry["baseline_applicability"] != "supported":
            lines.append(
                f"- Baseline applicability={entry['baseline_applicability']}，比较已由门禁抑制。"
            )
        else:
            lines.append(
                "- 本窗口没有可比较的新 Paloma eval，或进度尚未达到 5%；Train CE 不用于替代 Paloma。"
            )

    progress = stats.get("progress_pct")
    lines.extend(["", "## 里程碑与解释边界", ""])
    if progress is not None:
        lines.append(f"- **DERIVED**：窗口末进度约 **{progress:.2f}%**。")
        lines.append(
            "- 尚未到达约 25% 的 grad-norm 经验参考区。"
            if progress < 25
            else "- 已越过约 25% 的 grad-norm 经验参考区；这仍不是因果阈值。"
        )
        lines.append(
            "- 尚未到达 80% datamix 阶段边界。"
            if progress < 80
            else "- 已越过 80% datamix 阶段边界，必须检查 baseline regime 是否仍可比较。"
        )
    lines.extend(
        [
            "",
            "## 证据与局限",
            "",
            "- W&B history 由公开 GraphQL `sampledHistory` 获得，当前标记为 server-sampled，不声称是完整逐步历史。",
            "- 代码、issue、Hugging Face 与官网证据由 `main` 的不可变 snapshot 管道单独保存；本日报不重复实现简化抓取器。",
            "- 证据优先级：run config > pinned source > issue narrative > secondary summary。",
            "",
        ]
    )
    navigation = []
    if previous_name:
        navigation.append(f"[← {previous_name}]({previous_name}.md)")
    if next_name:
        navigation.append(f"[{next_name} →]({next_name}.md)")
    if navigation:
        lines.extend([" · ".join(navigation), ""])
    lines.append("*自动生成 · v2 输出；旧版日报未被覆盖。*")
    return "\n".join(lines) + "\n"


def build_reports(root, baseline, data_as_of, applicability):
    data_dir = root / "data" / "hero" / HERO_RUN
    dense = read_jsonl(data_dir / "dense.jsonl")
    eval_rows = read_jsonl(data_dir / "eval.jsonl")
    if not dense:
        raise ValueError("Hero dense history is empty")

    dense_series = {
        "train_ce": metric_series(dense, "train/cross_entropy_loss"),
        "grad_norm": metric_series(dense, "grad/norm/total"),
        "throughput": metric_series(dense, "throughput/tokens_per_second"),
        "mfu": metric_series(dense, "throughput/mfu"),
        "drop_fraction": metric_series(dense, "moe/drop_fraction"),
    }
    eval_series = metric_series(eval_rows, "eval_dropless/paloma/macro_loss")
    timestamps = [point[2] for point in dense_series["train_ce"] if point[2] is not None]
    windows = complete_windows(min(timestamps), max(timestamps))
    baseline_sha256 = sha256_file(BASELINE_PATH)
    entries = []
    for name, start, end in windows:
        train = _in_window(dense_series["train_ce"], start, end)
        window_eval = [point for point in _in_window(eval_series, start, end) if point[0] > 0]
        train_summary = _summary(train)
        stats = {"train_ce": train_summary}
        for key, reducer in [
            ("grad_norm", max),
            ("throughput", lambda values: sum(values) / len(values)),
            ("mfu", lambda values: sum(values) / len(values)),
            ("drop_fraction", max),
        ]:
            points = _in_window(dense_series[key], start, end)
            values = [point[1] for point in points]
            stats[key] = reducer(values) if values else None
        if train_summary:
            stats["progress_pct"] = train_summary["step_last"] / HERO_STEPS * 100

        comparison = None
        if window_eval and applicability["status"] == "supported":
            step, actual, observed_at = window_eval[-1]
            prediction = interpolate_prediction(baseline, step, HERO_STEPS)
            if prediction["available"]:
                comparison = dict(prediction)
                comparison.update(
                    {
                        "actual": actual,
                        "residual": actual - prediction["prediction"],
                        "observed_at": _utc(observed_at).isoformat(),
                    }
                )
        entries.append(
            {
                "name": name,
                "window_utc": [_utc(start).isoformat(), _utc(end).isoformat()],
                "window_beijing": [
                    _beijing(start).strftime("%Y-%m-%d %H:%M"),
                    _beijing(end).strftime("%Y-%m-%d %H:%M"),
                ],
                "window_evidence_as_of": (
                    train_summary["observed_at_last"] if train_summary else None
                ),
                "dataset_as_of": data_as_of,
                "method_id": baseline["method_id"],
                "report_revision": "hero-window-v2",
                "baseline_sha256": baseline_sha256,
                "baseline_applicability": applicability["status"],
                "stats": stats,
                "matched_progress": comparison,
            }
        )

    report_dir = root / "reports" / "generated" / "hero"
    report_dir.mkdir(parents=True, exist_ok=True)
    for index, entry in enumerate(entries):
        previous_name = entries[index - 1]["name"] if index else None
        next_name = entries[index + 1]["name"] if index + 1 < len(entries) else None
        atomic_write_text(
            report_dir / f"{entry['name']}.md",
            _render_report(entry, previous_name, next_name),
        )
    index_payload = {
        "schema_version": "1.0",
        "method_id": baseline["method_id"],
        "generated_from_data_as_of": data_as_of,
        "baseline_sha256": baseline_sha256,
        "baseline_applicability": applicability["status"],
        "reports": entries,
    }
    atomic_write_json(report_dir / "index.json", index_payload)
    return index_payload
