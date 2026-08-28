#!/usr/bin/env python3
"""track_hero.py - Marin 535B hero-run tracker (backfill + scheduled update).

Windows are 12h aligned to Beijing 08:00 / 20:00 (= UTC 00:00 / 12:00).
  am report (Beijing 08:00, UTC 00:00) covers UTC 12:00(prev day) -> 00:00
  pm report (Beijing 20:00, UTC 12:00) covers UTC 00:00 -> 12:00

Usage:
  python3 track_hero.py backfill            # generate all complete-window reports since run start
  python3 track_hero.py update              # pull latest + report the most recent complete window
  python3 track_hero.py dashboard           # rebuild dashboard data only
"""
import datetime as dt
import json, math, os, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import marin_wandb as mw

E, P = "marin-community", "marin_moe"
HERO = "hero-12d8b6f0-dee637"
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DATA = os.path.join(ROOT, "data", "hero")
REPORTS = os.path.join(ROOT, "reports", "daily")
DASH = os.path.join(ROOT, "dashboard")

# Ladder-derived scaling law (refit in Task-1): L = 1.5 + A * C^-alpha
A_FIT, ALPHA_FIT = 87.1, 0.0894
C_FULL_HERO, HERO_STEPS = 2.70e24, 390251
HERO_TOKENS_PER_STEP = 18.0e12 / HERO_STEPS          # ~46.1M tokens/step
TEAM_PREDICTION_FINAL = 2.04                          # pre-registered (issue #8435)
GRAD_PEAK_PROGRESS = 0.25                             # ladder signature
PHASE2_PROGRESS = 0.80                                # data-mix switch

def utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc)

def bj(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone(dt.timedelta(hours=8)))

def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

def predicted_loss(step):
    c = C_FULL_HERO * max(step, 1) / HERO_STEPS   # step 0 -> 1 to avoid 0^-alpha
    return 1.5 + A_FIT * c ** (-ALPHA_FIT)

def window_bounds(date, half):
    """Return (start_ts, end_ts) UTC for a report named <date>-{am|pm}."""
    d = dt.datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    if half == "am":     # covers prev day 12:00 UTC -> this day 00:00 UTC
        end = d
        start = d - dt.timedelta(hours=12)
    else:                # covers this day 00:00 UTC -> 12:00 UTC
        start = d
        end = d + dt.timedelta(hours=12)
    return start.timestamp(), end.timestamp()

def window_name(ts):
    """Name the report that would be produced AT time ts (i.e., the just-finished window)."""
    u = utc(ts)
    if u.hour < 12:
        d = u.date()
        return f"{d.isoformat()}-am", *window_bounds(d.isoformat(), "am")
    else:
        d = u.date()
        return f"{d.isoformat()}-pm", *window_bounds(d.isoformat(), "pm")

def all_complete_windows(run_start_ts, now_ts):
    """List of (name, start, end) for every complete 12h window since run start."""
    out = []
    # first window: the one containing run_start, reported at its end
    # align to the next UTC 00:00 / 12:00 boundary after run start
    u = utc(run_start_ts)
    base = u.replace(hour=0, minute=0, second=0, microsecond=0)
    boundary = base + dt.timedelta(hours=12)
    if boundary.timestamp() <= run_start_ts:
        boundary = base + dt.timedelta(days=1)
    start = run_start_ts
    while boundary.timestamp() < now_ts:
        end = boundary.timestamp()
        # name by the BJ date + half at which the report is produced (window end)
        bjend = bj(end)
        nm = f"{bjend.date().isoformat()}-{'am' if bjend.hour == 8 else 'pm'}"
        out.append((nm, start, end))
        start = end
        boundary += dt.timedelta(hours=12)
    return out

# ---------------- data ----------------

def pull_latest():
    """Pull hero dense/eval/router with timestamps into DATA dir."""
    import pull_data  # sibling module
    os.makedirs(DATA, exist_ok=True)
    summary = pull_data.pull_run(HERO, os.path.join(DATA, HERO), "hero")
    return summary

def github_commits_since(since_iso, path="experiments/grug/moe_hero_ep", limit=20):
    url = (f"https://api.github.com/repos/marin-community/marin/commits?"
           f"path={path}&since={since_iso}&per_page={limit}")
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "marin-deep-track"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            cs = json.loads(r.read().decode())
        return [{"sha": c["sha"][:8],
                 "date": c["commit"]["author"]["date"],
                 "msg": c["commit"]["message"].splitlines()[0][:110]} for c in cs]
    except Exception as e:
        return [{"error": str(e)[:120]}]

def issue_comments_since(since_ts, limit=10):
    url = ("https://api.github.com/repos/marin-community/marin/issues/8435/comments"
           f"?since={utc(since_ts).strftime('%Y-%m-%dT%H:%M:%SZ')}&per_page={limit}")
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "marin-deep-track"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            cs = json.loads(r.read().decode())
        return [{"user": c["user"]["login"], "date": c["created_at"],
                 "body": (c.get("body") or "")[:400]} for c in cs]
    except Exception as e:
        return [{"error": str(e)[:120]}]

# ---------------- analysis ----------------

def series(rows, key):
    pts = [(r.get("_timestamp"), r.get("_step"), r[key]) for r in rows if r.get(key) is not None]
    return [(t, s, v) for t, s, v in pts if t is not None]

def in_window(pts, ws, we):
    return [(t, s, v) for t, s, v in pts if ws <= t < we]

def detect_events(dense_rows, ws, we):
    """Rule-based anomaly detection within a window."""
    ev = []
    ce = in_window(series(dense_rows, "train/cross_entropy_loss"), ws, we)
    gn = in_window(series(dense_rows, "grad/norm/total"), ws, we)
    tp = in_window(series(dense_rows, "throughput/tokens_per_second"), ws, we)
    dr = in_window(series(dense_rows, "moe/drop_fraction"), ws, we)
    if len(ce) >= 10:
        # ignore the cold-start transient (first ~200 steps of the whole run)
        ce2 = [x for x in ce if x[1] > 200]
        vs = [v for _, _, v in ce2]
        if vs:
            base = sorted(vs)[len(vs) // 4]
            for t, s, v in ce2:
                if v > base * 1.5:
                    ev.append({"type": "loss_spike", "step": s, "value": round(v, 3),
                               "note": f"CE {v:.3f} vs 窗口基线 {base:.3f} (>1.5x)"})
                    break
    if gn:
        mx = max(gn, key=lambda x: x[2])
        if mx[2] > 2.0:
            ev.append({"type": "grad_spike", "step": mx[1], "value": round(mx[2], 3),
                       "note": f"grad norm 峰值 {mx[2]:.2f} 超阈值 2.0"})
    if len(tp) >= 10:
        tp2 = [x for x in tp if x[1] > 200]     # ignore cold-start
        vs = sorted(v for _, _, v in tp2)
        if vs:
            med = vs[len(vs) // 2]
            dips = [x for x in tp2 if x[2] < med * 0.5]
            if dips:
                ev.append({"type": "throughput_drop", "step": dips[0][1],
                           "value": round(dips[0][2] / 1e6, 2),
                           "note": f"吞吐降至 {dips[0][2]/1e6:.1f}M tok/s (中位 {med/1e6:.1f}M)，疑似重启/慢节点"})
    if dr:
        mx = max(dr, key=lambda x: x[2])
        if mx[2] > 0.15:
            ev.append({"type": "moe_drop_high", "step": mx[1], "value": round(mx[2], 3),
                       "note": f"MoE drop fraction {mx[2]*100:.1f}% 偏高，关注路由均衡"})
    return ev

def window_stats(dense_rows, eval_rows, ws, we):
    def agg(key, fn):
        pts = in_window(series(dense_rows, key), ws, we)
        vs = [v for _, _, v in pts]
        return fn(vs) if vs else None
    steps = in_window(series(dense_rows, "train/cross_entropy_loss"), ws, we)
    st = {
        "step_first": steps[0][1] if steps else None,
        "step_last": steps[-1][1] if steps else None,
        "ce_first": round(steps[0][2], 4) if steps else None,
        "ce_last": round(steps[-1][2], 4) if steps else None,
        "grad_max": (lambda v: round(v, 3) if v is not None else None)(agg("grad/norm/total", max)),
        "throughput_mean": (lambda v: round(v / 1e6, 2) if v is not None else None)(agg("throughput/tokens_per_second", lambda x: sum(x) / len(x))),
        "mfu_mean": (lambda v: round(v, 1) if v is not None else None)(agg("throughput/mfu", lambda x: sum(x) / len(x))),  # mfu already in percent
        "drop_max": (lambda v: round(v, 4) if v is not None else None)(agg("moe/drop_fraction", max)),
        "mem_peak": (lambda v: round(v, 1) if v is not None else None)(agg("memory/peak_gib", max)),
    }
    # latest eval in window (skip step-0 random-init baseline when judging gap)
    ev = in_window(series(eval_rows, "eval_dropless/paloma/macro_loss"), ws, we)
    if ev:
        st["eval_step"] = ev[-1][1]
        st["eval_paloma"] = round(ev[-1][2], 4)
        st["eval_pred"] = round(predicted_loss(ev[-1][1]), 4)
        ev_trained = [x for x in ev if x[1] > 0]
        if ev_trained:
            s2, v2 = ev_trained[-1][1], ev_trained[-1][2]
            st["eval_gap"] = round(v2 - predicted_loss(s2), 4)
            st["eval_gap_step"] = s2
    if st["step_last"] is not None:
        st["progress_pct"] = round(st["step_last"] / HERO_STEPS * 100, 2)
        st["tokens_T"] = round(st["step_last"] * HERO_TOKENS_PER_STEP / 1e12, 3)
    return st

# ---------------- report ----------------

def render_report(name, ws, we, dense, evalr, commits, comments):
    st = window_stats(dense, evalr, ws, we)
    events = detect_events(dense, ws, we)
    bs, be = bj(ws), bj(we)
    L = []
    L.append(f"# Hero Run 追踪日报 · {name}")
    L.append("")
    L.append(f"**窗口**: {bs.strftime('%Y-%m-%d %H:%M')} → {be.strftime('%H:%M')}（北京时间）  ")
    L.append(f"**Run**: `{HERO}` · W&B `marin-community/marin_moe`  ")
    if st.get("step_last"):
        L.append(f"**进度**: step {st['step_first']} → **{st['step_last']}** / {HERO_STEPS:,}"
                 f"（{st['progress_pct']}%，累计 ~{st['tokens_T']}T / 18T tokens）  ")
    L.append("")
    L.append("## 核心指标")
    L.append("")
    L.append("| 指标 | 本窗口 |")
    L.append("|---|---|")
    if st.get("ce_last") is not None:
        L.append(f"| train CE | {st['ce_first']} → **{st['ce_last']}** |")
    if st.get("grad_max") is not None:
        L.append(f"| grad norm 峰值 | {st['grad_max']} |")
    if st.get("throughput_mean") is not None:
        L.append(f"| 吞吐均值 | {st['throughput_mean']}M tok/s |")
    if st.get("mfu_mean") is not None:
        L.append(f"| MFU 均值 | {st['mfu_mean']} |")
    if st.get("drop_max") is not None:
        L.append(f"| MoE drop 峰值 | {st['drop_max']} |")
    if st.get("mem_peak") is not None:
        L.append(f"| 显存峰值 | {st['mem_peak']} GiB |")
    L.append("")
    L.append("## vs Ladder 预测")
    L.append("")
    if st.get("eval_paloma") is not None:
        L.append(f"- 最新 eval（step {st['eval_step']}）dropless Paloma macro = **{st['eval_paloma']}**")
        if st.get("eval_gap") is not None:
            L.append(f"- 训练态 eval（step {st['eval_gap_step']}）vs 该进度 Ladder 预测 {predicted_loss(st['eval_gap_step']):.4f}"
                     f" → 偏差 **{st['eval_gap']:+.4f}**（{'优于预测' if st['eval_gap'] < 0 else '高于预测'}）")
        else:
            L.append("- 本窗口仅含 step-0 随机初始化基线（CE≈11.79），不作为预测偏差")
        L.append(f"- 终点团队预注册预测 ≈ **{TEAM_PREDICTION_FINAL}**（本文复算 2.070）")
    else:
        L.append("- 本窗口无新 eval 点（hero 每 3000 步评测一次）")
        if st.get("step_last"):
            L.append(f"- 当前进度缩放定律参考值 L = {predicted_loss(st['step_last']):.4f}")
    prog = (st.get("progress_pct") or 0) / 100
    flags = []
    if prog < GRAD_PEAK_PROGRESS:
        flags.append(f"- ⏳ 尚未到达 grad-norm 峰值区（Ladder 签名在 ~25%，约 step {int(HERO_STEPS*GRAD_PEAK_PROGRESS):,}）")
    else:
        flags.append(f"- ✅ 已过 grad-norm 峰值区（25%），峰值见上表，与 Ladder 签名对照")
    if prog < PHASE2_PROGRESS:
        flags.append(f"- ⏳ 数据配比 phase-2 切换点在 80%（约 step {int(HERO_STEPS*PHASE2_PROGRESS):,}），尚远")
    L.append("\n".join(flags))
    L.append("")
    L.append("## 事件")
    L.append("")
    if events:
        for e in events:
            L.append(f"- ⚠️ **{e['type']}** @ step {e.get('step')}: {e['note']}")
    else:
        L.append("- 本窗口未检测到异常（loss/grad/吞吐/MoE 规则检测全通过）")
    L.append("")
    L.append("## marin 代码变更（moe_hero_ep）")
    L.append("")
    if commits and "error" not in commits[0]:
        for c in commits:
            L.append(f"- `{c['sha']}` {c['date'][:16]} {c['msg']}")
    else:
        L.append("- 本窗口无相关提交（或查询失败）")
    if comments and "error" not in comments[0]:
        L.append("")
        L.append("## issue #8435 新动态")
        L.append("")
        for c in comments:
            body = c["body"].replace("\n", " ")[:200]
            L.append(f"- **{c['user']}** {c['date'][:16]}: {body}")
    L.append("")
    L.append("---")
    L.append("*自动生成 · marin-deep-track · 数据源: 公开 W&B + GitHub*")
    return "\n".join(L), st, events

def cmd_backfill(now_ts=None):
    dense = load_jsonl(os.path.join(DATA, HERO, "dense.jsonl"))
    evalr = load_jsonl(os.path.join(DATA, HERO, "eval.jsonl"))
    if not dense:
        print("no dense data; run `track_hero.py update` first")
        return
    ts0 = min(r["_timestamp"] for r in dense if r.get("_timestamp"))
    now_ts = now_ts or max(r["_timestamp"] for r in dense if r.get("_timestamp"))
    os.makedirs(REPORTS, exist_ok=True)
    wins = all_complete_windows(ts0, now_ts)
    print(f"run start {utc(ts0).isoformat()} | data to {utc(now_ts).isoformat()} | {len(wins)} complete windows")
    index = []
    for name, ws, we in wins:
        since_iso = utc(ws).strftime("%Y-%m-%dT%H:%M:%SZ")
        commits = github_commits_since(since_iso) if ws else []
        # only include commits within window
        commits = [c for c in commits if "error" in c or (ws <= dt.datetime.strptime(c["date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp() < we)]
        comments = issue_comments_since(ws)
        comments = [c for c in comments if "error" in c or (ws <= dt.datetime.strptime(c["date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp() < we)]
        md, st, events = render_report(name, ws, we, dense, evalr, commits, comments)
        with open(os.path.join(REPORTS, f"{name}.md"), "w") as f:
            f.write(md)
        index.append({"name": name, "window": [ws, we], "stats": st, "events": events})
        print(f"  {name}: step {st.get('step_first')}→{st.get('step_last')} events={len(events)}")
    with open(os.path.join(REPORTS, "_index.json"), "w") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print(f"wrote {len(wins)} reports + _index.json")

def cmd_update():
    print("pulling latest hero data ...")
    s = pull_latest()
    print("pull:", {k: v for k, v in s.items() if k.startswith("rows")})
    dense = load_jsonl(os.path.join(DATA, HERO, "dense.jsonl"))
    now_ts = max(r["_timestamp"] for r in dense if r.get("_timestamp"))
    name, ws, we = window_name(now_ts)
    print("latest complete window:", name)
    cmd_backfill(now_ts=now_ts)   # regenerate all (cheap) so index stays complete

def cmd_dashboard():
    dense = load_jsonl(os.path.join(DATA, HERO, "dense.jsonl"))
    evalr = load_jsonl(os.path.join(DATA, HERO, "eval.jsonl"))
    router = load_jsonl(os.path.join(DATA, HERO, "router.jsonl"))
    os.makedirs(DASH, exist_ok=True)
    def ds(rows, key, limit=2000):
        pts = series(rows, key)
        if len(pts) > limit:
            step = len(pts) // limit
            pts = pts[::step]
        return [[s, round(v, 5)] for _, s, v in pts]
    payload = {
        "run": HERO,
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hero_steps": HERO_STEPS,
        "team_prediction_final": TEAM_PREDICTION_FINAL,
        "fit": {"A": A_FIT, "alpha": ALPHA_FIT, "asymptote": 1.5},
        "train_ce": ds(dense, "train/cross_entropy_loss"),
        "grad_norm": ds(dense, "grad/norm/total"),
        "throughput": ds(dense, "throughput/tokens_per_second"),
        "mfu": ds(dense, "throughput/mfu"),
        "drop_fraction": ds(dense, "moe/drop_fraction"),
        "lr": ds(dense, "optim/learning_rate"),
        "eval_paloma": ds(evalr, "eval_dropless/paloma/macro_loss"),
        "prediction": [[s, round(predicted_loss(s), 5)] for s in range(0, HERO_STEPS + 1, 5000)],
    }
    with open(os.path.join(DASH, "hero_data.json"), "w") as f:
        json.dump(payload, f)
    print("dashboard data ->", os.path.join(DASH, "hero_data.json"))

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    {"backfill": cmd_backfill, "update": cmd_update, "dashboard": cmd_dashboard}[cmd]()
