"""Static, accessible site rendering. No analysis is performed here."""

import html
import json
import math
import posixpath
import re
import shutil
from pathlib import Path

from .io import atomic_write_json, atomic_write_text


COLORS = ["#63b3ff", "#67e8c2", "#f6bd60", "#f28482", "#b8a1ff"]


def _artifact_slug(path):
    """Return a stable URL-safe slug for one repository-relative artifact."""
    return re.sub(r"[^0-9A-Za-z]+", "-", str(path)).strip("-").lower()


def _rewrite_markdown_link(href, source_path, output_path, link_map):
    if "://" in href or href.startswith(("#", "mailto:")):
        return href
    path, marker, fragment = href.partition("#")
    target_source = (source_path.parent / path).resolve()
    target_output = link_map.get(target_source)
    if target_output is None:
        return href
    relative = posixpath.relpath(target_output, output_path.parent)
    if relative.endswith("/index.html"):
        relative = relative[: -len("index.html")]
    return relative + (marker + fragment if marker else "")


def _inline_markdown(text, source_path, output_path, link_map):
    rendered = html.escape(text)

    def link(match):
        label = match.group(1)
        href = html.unescape(match.group(2))
        href = _rewrite_markdown_link(href, source_path, output_path, link_map)
        return f'<a href="{html.escape(href, quote=True)}">{label}</a>'

    rendered = re.sub(r"\[([^]]+)\]\(([^)]+)\)", link, rendered)
    rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
    rendered = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", rendered)
    return rendered


def markdown_to_html(markdown, source_path, output_path, link_map):
    """Render the deliberately small Markdown subset used by the learning corpus."""
    lines = markdown.splitlines()
    parts = []
    index = 0
    heading_ids = set()

    def heading_id(text):
        base = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text).strip("-").lower() or "section"
        candidate = base
        suffix = 2
        while candidate in heading_ids:
            candidate = f"{base}-{suffix}"
            suffix += 1
        heading_ids.add(candidate)
        return candidate

    def is_block_start(line, next_line=None):
        stripped = line.strip()
        return (
            not stripped
            or stripped.startswith(("#", "```", ">", "- ", "* "))
            or bool(re.match(r"^\d+\.\s+", stripped))
            or ("|" in stripped and next_line is not None and re.match(r"^\s*\|?\s*:?-+", next_line))
        )

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("```"):
            language = stripped[3:].strip()
            index += 1
            code = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index])
                index += 1
            index += 1 if index < len(lines) else 0
            cls = f' class="language-{html.escape(language)}"' if language else ""
            parts.append(f"<pre><code{cls}>{html.escape(chr(10).join(code))}</code></pre>")
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2)
            parts.append(
                f'<h{level} id="{heading_id(text)}">'
                f'{_inline_markdown(text, source_path, output_path, link_map)}</h{level}>'
            )
            index += 1
            continue
        if index + 1 < len(lines) and "|" in line and re.match(
            r"^\s*\|?\s*:?-+", lines[index + 1]
        ):
            headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
            index += 2
            rows = []
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            head = "".join(
                f'<th scope="col">{_inline_markdown(cell, source_path, output_path, link_map)}</th>'
                for cell in headers
            )
            body = "".join(
                "<tr>"
                + "".join(
                    f"<td>{_inline_markdown(cell, source_path, output_path, link_map)}</td>"
                    for cell in row
                )
                + "</tr>"
                for row in rows
            )
            parts.append(f'<div class="table-scroll" tabindex="0"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
            continue
        if stripped.startswith(("- ", "* ")) or re.match(r"^\d+\.\s+", stripped):
            ordered = bool(re.match(r"^\d+\.\s+", stripped))
            tag = "ol" if ordered else "ul"
            items = []
            pattern = r"^\d+\.\s+" if ordered else r"^[-*]\s+"
            while index < len(lines) and re.match(pattern, lines[index].strip()):
                item = re.sub(pattern, "", lines[index].strip())
                items.append(
                    f"<li>{_inline_markdown(item, source_path, output_path, link_map)}</li>"
                )
                index += 1
            parts.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        if stripped.startswith(">"):
            quote = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip(">").strip())
                index += 1
            parts.append(
                "<blockquote><p>"
                + _inline_markdown(" ".join(quote), source_path, output_path, link_map)
                + "</p></blockquote>"
            )
            continue
        if re.match(r"^[-*_]{3,}$", stripped):
            parts.append("<hr>")
            index += 1
            continue
        paragraph = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index]
            after = lines[index + 1] if index + 1 < len(lines) else None
            if is_block_start(next_line, after):
                break
            paragraph.append(next_line.strip())
            index += 1
        parts.append(
            "<p>"
            + _inline_markdown(" ".join(paragraph), source_path, output_path, link_map)
            + "</p>"
        )
    return "\n".join(parts)


def _fmt(value, digits=3):
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _tick(value):
    magnitude = abs(value)
    if magnitude >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if magnitude >= 1_000:
        return f"{value / 1_000:.0f}k"
    if magnitude >= 10:
        return f"{value:.0f}"
    if magnitude >= 1:
        return f"{value:.2f}"
    return f"{value:.3f}"


def svg_line_chart(chart_id, title, description, series, y_label, band=None, zero_line=False):
    """Render a single-unit static SVG with title, description and direct legend."""
    all_points = [point for item in series for point in item["points"]]
    if band:
        all_points.extend([[point[0], point[1]] for point in band])
        all_points.extend([[point[0], point[2]] for point in band])
    if not all_points:
        return '<p class="empty-state">暂无可绘制数据。</p>'
    xs = [float(point[0]) for point in all_points]
    ys = [float(point[1]) for point in all_points]
    if zero_line:
        ys.append(0.0)
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if math.isclose(x_min, x_max):
        x_max = x_min + 1
    if math.isclose(y_min, y_max):
        y_max = y_min + 1
    y_pad = (y_max - y_min) * 0.09
    y_min -= y_pad
    y_max += y_pad
    width, height = 960, 390
    left, right, top, bottom = 78, 26, 46, 58
    inner_width = width - left - right
    inner_height = height - top - bottom

    def x_pos(value):
        return left + (float(value) - x_min) / (x_max - x_min) * inner_width

    def y_pos(value):
        return top + (y_max - float(value)) / (y_max - y_min) * inner_height

    title_id = f"{chart_id}-title"
    desc_id = f"{chart_id}-desc"
    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{html.escape(title)}</title>',
        f'<desc id="{desc_id}">{html.escape(description)}</desc>',
        '<g class="chart-grid">',
    ]
    for index in range(5):
        value = y_min + (y_max - y_min) * index / 4
        y = y_pos(value)
        parts.append(
            f'<line x1="{left}" x2="{width-right}" y1="{y:.2f}" y2="{y:.2f}" />'
            f'<text x="{left-10}" y="{y+4:.2f}" text-anchor="end">{html.escape(_tick(value))}</text>'
        )
    for index in range(6):
        value = x_min + (x_max - x_min) * index / 5
        x = x_pos(value)
        parts.append(
            f'<text x="{x:.2f}" y="{height-25}" text-anchor="middle">{html.escape(_tick(value))}</text>'
        )
    parts.extend(
        [
            "</g>",
            f'<text class="axis-label" x="{left + inner_width/2:.2f}" y="{height-5}" text-anchor="middle">training step</text>',
            f'<text class="axis-label" transform="translate(18 {top + inner_height/2:.2f}) rotate(-90)" text-anchor="middle">{html.escape(y_label)}</text>',
        ]
    )
    if zero_line and y_min <= 0 <= y_max:
        y = y_pos(0)
        parts.append(
            f'<line class="zero-line" x1="{left}" x2="{width-right}" y1="{y:.2f}" y2="{y:.2f}" />'
        )
    if band:
        upper = " ".join(f"{x_pos(x):.2f},{y_pos(high):.2f}" for x, _low, high in band)
        lower = " ".join(
            f"{x_pos(x):.2f},{y_pos(low):.2f}" for x, low, _high in reversed(band)
        )
        parts.append(
            f'<polygon class="sensitivity-band" points="{upper} {lower}"><title>Leave-one-rung-out sensitivity range; not a confidence interval</title></polygon>'
        )
    for index, item in enumerate(series):
        color = item.get("color", COLORS[index % len(COLORS)])
        points = item["points"]
        coords = " ".join(f"{x_pos(x):.2f},{y_pos(y):.2f}" for x, y in points)
        dash = ' stroke-dasharray="10 7"' if item.get("dashed") else ""
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="3"{dash} points="{coords}" />'
        )
        marker = "square" if item.get("marker") == "square" else "circle"
        for x_value, y_value in points:
            x, y = x_pos(x_value), y_pos(y_value)
            if marker == "square":
                parts.append(
                    f'<rect x="{x-4:.2f}" y="{y-4:.2f}" width="8" height="8" fill="{color}" />'
                )
            else:
                parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}" />')
    legend_x = left
    for index, item in enumerate(series):
        color = item.get("color", COLORS[index % len(COLORS)])
        parts.append(
            f'<line x1="{legend_x}" x2="{legend_x+28}" y1="20" y2="20" stroke="{color}" stroke-width="3" />'
            f'<text class="legend-label" x="{legend_x+36}" y="24">{html.escape(item["name"])}</text>'
        )
        legend_x += max(150, len(item["name"]) * 10 + 65)
    parts.append("</svg>")
    return "".join(parts)


def _claim_cards(ledger):
    cards = []
    for claim in ledger["claims"]:
        kind = claim["kind"]
        details = []
        if claim.get("value") is not None:
            value = claim["value"]
            rendered_value = f"{value:.6g}" if isinstance(value, (int, float)) else str(value)
            details.append(f"值：{rendered_value} {claim.get('unit', '')}".strip())
        if claim.get("confidence"):
            details.append(f"置信度：{claim['confidence']}")
        if claim.get("caveats"):
            details.append("限制：" + "；".join(claim["caveats"]))
        evidence_rows = []
        for row in claim["evidence"]:
            artifact = row.get("artifact") or row.get("path")
            claim_id = row.get("claim_id")
            selector = " · ".join(
                part
                for part in (
                    f"metric={row['metric_key']}" if row.get("metric_key") else None,
                    f"step={row['step']}" if row.get("step") is not None else None,
                    (
                        "selector=" + json.dumps(row["record_selector"], ensure_ascii=False)
                        if row.get("record_selector") is not None
                        else None
                    ),
                )
                if part
            )
            if artifact:
                label = html.escape(artifact)
                href = "{{ROOT}}/evidence/" + _artifact_slug(artifact) + "/"
                evidence_rows.append(
                    f'<a href="{href}">{label}</a>'
                    + (f" <small>{html.escape(selector)}</small>" if selector else "")
                )
            elif claim_id:
                evidence_rows.append(
                    f'<a href="{{{{ROOT}}}}/live/#{html.escape(claim_id, quote=True)}">'
                    f'{html.escape(claim_id)}</a>'
                )
            else:
                evidence_rows.append("evidence")
        derivation = claim.get("derivation") or {}
        method = derivation.get("method_id") or derivation.get("method")
        cards.append(
            f'<article class="claim-card claim-{kind.lower()}" id="{html.escape(claim["id"])}">'
            f'<div class="claim-meta"><span class="claim-badge">{kind}</span>'
            f'<span>{html.escape(claim["support"])}</span></div>'
            f'<p>{html.escape(claim["statement"])}</p>'
            f'<details><summary>证据、数值与限制</summary>'
            f'<p>{html.escape(" · ".join(details))}</p><p>证据：{"；".join(evidence_rows)}</p>'
            + (f'<p>方法：<code>{html.escape(str(method))}</code></p>' if method else "")
            + f'<p>as of {html.escape(claim["as_of"])}</p></details></article>'
        )
    return "".join(cards)


def _data_table(headers, rows, caption):
    head = "".join(f"<th scope=\"col\">{html.escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return (
        '<div class="table-scroll" tabindex="0" aria-label="可横向滚动的数据表">'
        f'<table><caption>{html.escape(caption)}</caption><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def _replace_tokens(text, values):
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", str(value))
    unresolved = [part.split("}}", 1)[0] for part in text.split("{{")[1:] if "}}" in part]
    if unresolved:
        raise ValueError(f"unresolved template tokens: {sorted(set(unresolved))}")
    return text


def _page_values(status, ledger, baseline, report_index):
    run = status["run"]
    recipe = status["recipe"]
    paloma = status["latest"]["paloma_macro"]
    comparison = status["matched_progress"]
    terminal = baseline["terminal_prediction"]
    fractions = {row["progress_pct"]: row for row in baseline["fractions"]}
    residual = comparison["residual"] if comparison else None
    residual_low = comparison["actual"] - comparison["sensitivity_high"] if comparison else None
    residual_high = comparison["actual"] - comparison["sensitivity_low"] if comparison else None

    train_points = [point for point in status["series"]["train_ce"] if point[0] >= 200]
    paloma_points = [point for point in status["series"]["paloma_macro"] if point[0] > 0]
    baseline_points = [
        [point[0], point[1]]
        for point in status["series"]["matched_progress"]
        if point[0] <= run["step"] * 1.15
    ]
    band = [
        [point[0], point[2], point[3]]
        for point in status["series"]["matched_progress"]
        if point[0] <= run["step"] * 1.15
    ]
    residual_points = status["series"]["paloma_residual"]

    paloma_chart = svg_line_chart(
        "paloma-matched",
        "Paloma 实测与 matched-progress 点预测",
        "同一 held-out Paloma macro loss 口径。阴影是 leave-one-rung-out 敏感性范围，不是置信区间。",
        [
            {"name": "Paloma observed", "points": paloma_points, "color": "#67e8c2"},
            {
                "name": "Matched-progress point prediction",
                "points": baseline_points,
                "color": "#b8a1ff",
                "dashed": True,
                "marker": "square",
            },
        ],
        "dropless Paloma macro loss",
        band=band,
    )
    residual_chart = svg_line_chart(
        "paloma-residual",
        "Paloma residual（actual − prediction）",
        "零线以下表示实测低于 matched-progress 点预测；这不自动等于统计显著。",
        [{"name": "Residual", "points": residual_points, "color": "#f6bd60"}],
        "loss residual",
        zero_line=True,
    )
    train_chart = svg_line_chart(
        "train-ce",
        "训练交叉熵",
        "单独展示 train/cross_entropy_loss；从 step 200 开始以排除冷启动，不与 Paloma 绝对值比较。",
        [{"name": "Train CE", "points": train_points, "color": "#63b3ff"}],
        "train cross-entropy loss",
    )

    report_rows = []
    for entry in reversed(report_index["reports"]):
        train = entry["stats"].get("train_ce") or {}
        comparison_row = entry.get("matched_progress")
        report_rows.append(
            "<tr>"
            f'<td><a href="{{{{ROOT}}}}/daily/{html.escape(entry["name"])}/">{html.escape(entry["name"])}</a></td>'
            f'<td>{html.escape(str(train.get("step_last", "—")))}</td>'
            f'<td>{_fmt(entry["stats"].get("progress_pct"), 2)}%</td>'
            f'<td>{_fmt(comparison_row.get("residual") if comparison_row else None, 5)}</td>'
            "</tr>"
        )

    values = {
        "RUN_ID": html.escape(run["id"]),
        "RUN_STATE": html.escape(run["state"]),
        "STEP": f"{run['step']:,}",
        "TOTAL_STEPS": f"{run['total_steps']:,}",
        "PROGRESS": f"{run['progress_pct']:.2f}",
        "TOKENS_T": f"{run['tokens_trained'] / 1e12:.3f}",
        "DATA_AS_OF": html.escape(status["data_as_of"]),
        "HEARTBEAT_AT": html.escape(run["heartbeat_at"] or "unknown"),
        "FRESHNESS_HOURS": run["freshness_threshold_hours"],
        "LR_SCHEDULE": html.escape(str(recipe["learning_rate_schedule"])),
        "DEVICE": html.escape(str(recipe["device_variant"])),
        "CONFIGURED_SLOTS": f"{recipe['configured_device_slots']:,}",
        "BASELINE_APPLICABILITY": html.escape(status["baseline_applicability"]["status"]),
        "MIXTURE_STAGE": html.escape(str(run["mixture_stage"])),
        "PALOMA": _fmt(paloma["value"] if paloma else None, 5),
        "PALOMA_STEP": f"{paloma['step']:,}" if paloma else "—",
        "PREDICTION": _fmt(comparison["prediction"] if comparison else None, 5),
        "RESIDUAL": (f"{residual:+.5f}" if residual is not None else "—"),
        "RESIDUAL_ABS": _fmt(abs(residual) if residual is not None else None, 5),
        "RESIDUAL_DIRECTION": (
            "低于" if residual is not None and residual < 0
            else "高于" if residual is not None and residual > 0
            else "等于" if residual is not None
            else "不可比较于"
        ),
        "RESIDUAL_RANGE": (
            f"[{residual_low:+.5f}, {residual_high:+.5f}]"
            if residual_low is not None
            else "—"
        ),
        "TERMINAL": _fmt(terminal, 5),
        "PRED_5": _fmt(fractions[5.0]["hero"]["prediction"], 5),
        "PRED_10": _fmt(fractions[10.0]["hero"]["prediction"], 5),
        "PRED_100": _fmt(fractions[100.0]["hero"]["prediction"], 5),
        "D2048_100": _fmt(fractions[100.0]["rungs"][-1]["loss"], 5),
        "METHOD_ID": html.escape(baseline["method_id"]),
        "OFFICIAL_COMMIT": html.escape(baseline["source"]["upstream_commit"][:8]),
        "OFFICIAL_SCRIPT": html.escape(baseline["source"]["upstream_script"]),
        "CLAIM_CARDS": _claim_cards(ledger),
        "PALOMA_CHART": paloma_chart,
        "RESIDUAL_CHART": residual_chart,
        "TRAIN_CHART": train_chart,
        "PALOMA_TABLE": _data_table(
            ["step", "Paloma observed"],
            [[step, f"{value:.5f}"] for step, value in paloma_points],
            "Paloma observed data used in the chart",
        ),
        "RESIDUAL_TABLE": _data_table(
            ["step", "actual − prediction"],
            [[step, f"{value:+.5f}"] for step, value in residual_points],
            "Matched-progress residual data",
        ),
        "TRAIN_TABLE": _data_table(
            ["step", "train CE"],
            [[step, f"{value:.5f}"] for step, value in train_points[-40:]],
            "Last 40 displayed train CE points; chart starts at step 200",
        ),
        "DAILY_ROWS": "".join(report_rows),
        "REPORT_COUNT": len(report_index["reports"]),
    }
    return values


def _render_markdown_pages(root, site_dir, base, common, status):
    docs_root = root / "docs"
    document_sources = sorted(docs_root.rglob("*.md"))
    report_sources = sorted((root / "reports" / "generated" / "hero").glob("*.md"))
    mappings = {}
    page_kinds = {}
    for source in document_sources:
        relative = source.relative_to(docs_root)
        if relative.parent == Path("learning"):
            output = site_dir / "learn" / source.stem / "index.html"
            page_kind = "learn"
        else:
            output = site_dir / "docs" / relative.with_suffix("") / "index.html"
            page_kind = "docs"
        mappings[source.resolve()] = output.resolve()
        page_kinds[source.resolve()] = page_kind
    for source in report_sources:
        mappings[source.resolve()] = (site_dir / "daily" / source.stem / "index.html").resolve()
        page_kinds[source.resolve()] = "daily"

    outputs = []
    for source, output in mappings.items():
        markdown = source.read_text(encoding="utf-8")
        first_heading = next(
            (line.lstrip("# ").strip() for line in markdown.splitlines() if line.startswith("#")),
            source.stem,
        )
        page = page_kinds[source]
        is_report = page == "daily"
        back_label = "返回日报索引" if is_report else "返回学习中心"
        back_target = "daily" if is_report else "learn"
        markdown_html = markdown_to_html(markdown, source, output, mappings)
        # Documentation may intentionally teach template syntax such as
        # ``{{TOKEN}}``. Encode braces so it remains visible without being
        # mistaken for an unresolved site-template token.
        markdown_html = markdown_html.replace("{{", "&#123;&#123;").replace(
            "}}", "&#125;&#125;"
        )
        body = (
            '<section class="section-shell document-shell">'
            f'<p class="document-back"><a href="{{{{ROOT}}}}/{back_target}/">← {back_label}</a></p>'
            f'<article class="markdown-doc">{markdown_html}</article>'
            "</section>"
        )
        active_page = "daily" if is_report else "learn"
        values = dict(common)
        values.update(
            {
                "TITLE": html.escape(first_heading + " · Marin 学习系统"),
                "DESCRIPTION": html.escape("Marin 训练学习系统的可复现学习材料。"),
                "ROOT": posixpath.relpath(site_dir.resolve(), output.parent.resolve()),
                "PAGE": active_page,
                "UPDATED": html.escape(status["data_as_of"]),
            }
        )
        for nav_page in ("home", "live", "learn", "methodology", "daily", "legacy"):
            values[f"CURRENT_{nav_page.upper()}"] = (
                'aria-current="page"' if nav_page == active_page else ""
            )
        rendered = _replace_tokens(base.replace("{{BODY}}", body), values)
        atomic_write_text(output, rendered)
        outputs.append(str(output.relative_to(site_dir)))
    return outputs


def _find_json_record(value, key, expected):
    if isinstance(value, dict):
        if value.get(key) == expected:
            return value
        for child in value.values():
            match = _find_json_record(child, key, expected)
            if match is not None:
                return match
    elif isinstance(value, list):
        for child in value:
            match = _find_json_record(child, key, expected)
            if match is not None:
                return match
    return None


def _json_text_matches(value, pattern, path="", limit=10):
    matches = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            matches.extend(_json_text_matches(child, pattern, child_path, limit))
            if len(matches) >= limit:
                break
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(_json_text_matches(child, pattern, f"{path}[{index}]", limit))
            if len(matches) >= limit:
                break
    elif isinstance(value, str):
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            start = max(0, match.start() - 220)
            end = min(len(value), match.end() + 420)
            matches.append({"path": path, "excerpt": value[start:end]})
    return matches[:limit]


def _artifact_preview(source, artifact_id, limit=18_000):
    """Create a bounded, human-readable preview; the raw copy remains canonical."""
    if source.suffix == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if artifact_id == "hero_issue_snapshot":
            selected = _find_json_record(payload, "number", 8435)
            if selected is not None:
                payload = {
                    "record_selector": {"number": 8435},
                    "number": selected.get("number"),
                    "title": selected.get("title"),
                    "url": selected.get("url"),
                    "state": selected.get("state"),
                    "updated_at": selected.get("updated_at"),
                    "relevant_excerpts": _json_text_matches(
                        selected, r"25\s*%|30\s*%|grad[-_ ]?norm|gradient"
                    ),
                    "preview_note": (
                        "Excerpts locate the milestone narrative; the raw artifact "
                        "and checksum above remain authoritative."
                    ),
                }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    elif source.suffix == ".jsonl":
        lines = source.read_text(encoding="utf-8").splitlines()
        selected_lines = lines if len(lines) <= 6 else lines[:3] + ["…"] + lines[-3:]
        text = "\n".join(line[:4_000] for line in selected_lines)
    else:
        text = source.read_text(encoding="utf-8", errors="replace")
    if len(text) > limit:
        return text[:limit] + "\n\n… PREVIEW TRUNCATED …"
    return text


def _render_evidence_pages(root, site_dir, base, common, status):
    outputs = []
    for artifact_id, artifact in sorted(status["artifacts"].items()):
        source = root / artifact["path"]
        slug = _artifact_slug(artifact["path"])
        output = site_dir / "evidence" / slug / "index.html"
        relative_root = posixpath.relpath(site_dir.resolve(), output.parent.resolve())
        preview = _artifact_preview(source, artifact_id)
        sampling = artifact.get("sampling") or "未声明额外采样规则"
        body = (
            '<section class="section-shell document-shell">'
            '<p class="document-back"><a href="{{ROOT}}/live/">← 返回 Claim 账本</a></p>'
            '<article class="markdown-doc evidence-doc">'
            '<p class="eyebrow evidence-eyebrow">EVIDENCE ARTIFACT</p>'
            f'<h1>{html.escape(artifact_id)}</h1>'
            '<dl class="evidence-meta">'
            f'<div><dt>仓库路径</dt><dd><code>{html.escape(artifact["path"])}</code></dd></div>'
            f'<div><dt>来源</dt><dd>{html.escape(artifact["provider"])}</dd></div>'
            f'<div><dt>采样</dt><dd>{html.escape(sampling)}</dd></div>'
            f'<div><dt>SHA-256</dt><dd><code>{html.escape(artifact["sha256"])}</code></dd></div>'
            '</dl>'
            '<p><strong>预览不是第二份事实源。</strong>它只帮助定位记录；校验与复算使用上面的完整文件 checksum。</p>'
            f'<p><a href="{{{{ROOT}}}}/artifacts/{html.escape(artifact["path"], quote=True)}">打开或下载完整原始文件 →</a></p>'
            '<h2>可读预览</h2>'
            f'<pre><code>{html.escape(preview)}</code></pre>'
            '</article></section>'
        )
        values = dict(common)
        values.update(
            {
                "TITLE": html.escape(f"{artifact_id} · Evidence · Marin 学习系统"),
                "DESCRIPTION": html.escape("Claim 所引用证据的来源、checksum 与可读预览。"),
                "ROOT": relative_root,
                "PAGE": "live",
                "UPDATED": html.escape(status["data_as_of"]),
            }
        )
        for nav_page in ("home", "live", "learn", "methodology", "daily", "legacy"):
            values[f"CURRENT_{nav_page.upper()}"] = (
                'aria-current="page"' if nav_page == "live" else ""
            )
        rendered = _replace_tokens(base.replace("{{BODY}}", body), values)
        atomic_write_text(output, rendered)
        outputs.append(str(output.relative_to(site_dir)))
    return outputs


def build_site(root, status, ledger, baseline, report_index):
    web_dir = root / "web"
    site_dir = root / "site"
    base = (web_dir / "templates" / "base.html").read_text(encoding="utf-8")
    common = _page_values(status, ledger, baseline, report_index)
    pages = [
        ("home", "Marin 训练学习系统", "先看状态，再学方法。", "index.html", "."),
        ("live", "实时状态 · Marin 学习系统", "同口径指标与可审计结论。", "live/index.html", ".."),
        ("learn", "学习路径 · Marin 学习系统", "从证据到推断的课程路线。", "learn/index.html", ".."),
        ("methodology", "方法与复现 · Marin 学习系统", "matched-progress 的公式、输入与限制。", "methodology/index.html", ".."),
        ("daily", "v2 日报 · Marin 学习系统", "可连续浏览的纠正版日报。", "daily/index.html", ".."),
        ("legacy", "版本对比 · Marin 学习系统", "旧分支与 v2 的透明对照。", "legacy/index.html", ".."),
    ]
    for page, title, description, output, relative_root in pages:
        body = (web_dir / "pages" / f"{page}.html").read_text(encoding="utf-8")
        values = dict(common)
        values.update(
            {
                "TITLE": html.escape(title),
                "DESCRIPTION": html.escape(description),
                "ROOT": relative_root,
                "PAGE": page,
                "UPDATED": html.escape(status["data_as_of"]),
            }
        )
        for nav_page in ("home", "live", "learn", "methodology", "daily", "legacy"):
            values[f"CURRENT_{nav_page.upper()}"] = (
                'aria-current="page"' if nav_page == page else ""
            )
        rendered = _replace_tokens(base.replace("{{BODY}}", body), values)
        atomic_write_text(site_dir / output, rendered)

    generated_content = _render_markdown_pages(root, site_dir, base, common, status)
    generated_content.extend(
        _render_evidence_pages(root, site_dir, base, common, status)
    )

    assets_out = site_dir / "assets"
    assets_out.mkdir(parents=True, exist_ok=True)
    for filename in ("styles.css", "site.js"):
        shutil.copyfile(web_dir / "assets" / filename, assets_out / filename)
    data_dir = site_dir / "data"
    atomic_write_json(data_dir / "current_status.json", status)
    atomic_write_json(data_dir / "claim_ledger.json", ledger)
    atomic_write_json(data_dir / "matched_progress_v1.json", baseline)
    atomic_write_json(data_dir / "daily_index.json", report_index)
    artifact_catalog = []
    for artifact_id, artifact in status["artifacts"].items():
        source = root / artifact["path"]
        destination = site_dir / "artifacts" / artifact["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        artifact_catalog.append(
            {
                "id": artifact_id,
                "path": f"../artifacts/{artifact['path']}",
                "sha256": artifact["sha256"],
                "provider": artifact["provider"],
                "sampling": artifact.get("sampling"),
            }
        )
    atomic_write_json(
        data_dir / "catalog.json",
        {
            "schema_version": "1.0",
            "data_as_of": status["data_as_of"],
            "method_id": baseline["method_id"],
            "derived_artifacts": [
                "current_status.json", "claim_ledger.json",
                "matched_progress_v1.json", "daily_index.json"
            ],
            "evidence_artifacts": artifact_catalog,
        },
    )
    all_outputs = [output for _page, _title, _description, output, _root in pages]
    all_outputs.extend(generated_content)
    atomic_write_text(
        site_dir / "sitemap.xml",
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(
            f"  <url><loc>https://fudan-chen.github.io/pretrain/site/{'' if output == 'index.html' else output}</loc></url>\n"
            for output in all_outputs
        )
        + "</urlset>\n",
    )
    return all_outputs
