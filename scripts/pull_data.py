#!/usr/bin/env python3
"""pull_data.py - Harvest W&B telemetry for Marin ladder / hero runs into JSONL + CSV.

Usage: python3 pull_data.py <outdir> <mode> <run1> [run2 ...]
  mode: ladder | hero
Each run gets: <outdir>/<run>/meta.json, dense.jsonl, eval.jsonl, mixture.jsonl,
               system.jsonl (hero only), router.jsonl (hero only)
"""
import csv, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import marin_wandb as mw

ENTITY, PROJECT = "marin-community", "marin_moe"

DENSE_PAT = [
    r"^train/loss$", r"^train/cross_entropy_loss$",
    r"^grad/norm/total$", r"^optim/learning_rate$", r"^optim/adam_lr$",
    r"^moe/drop_fraction$", r"^moe/sender_drop_fraction$", r"^moe/receiver_drop_fraction$",
    r"^throughput/(duration|examples_per_second|gflops_per_second|mfu|tokens_per_second|total_gflops|total_tokens)$",
    r"^memory/(in_use_gib|limit_gib|peak_gib)$",
    r"^run_progress$",
]
EVAL_PAT = [
    r"^eval_dropless/paloma/(macro_loss|micro_loss|macro_bpb)$",
    r"^eval_dropless/paloma/[^/]+/(loss|bpb)$",
    r"^eval/paloma/(macro_loss|micro_loss|macro_bpb)$",
]
SYSTEM_PAT = [
    r"^system/gpu\.[0-3]\.(nvlinkRxBytes|nvlinkTxBytes|pcieRxBytes|pcieTxBytes|smActive|powerWatts|temp|memory|memoryAllocatedBytes|gpu)$",
    r"^system/(network\.recv|network\.sent|memory_percent|cpu)$",
]
ROUTER_PAT = [
    # keep layer 0/1/2/46/47 (edges) full + aggregate stats for all layers
    r"^train/router/layer_(0|1|2|46|47)/[^/]+$",
    r"^train/router/[^l][^/]*$",  # non-layer router aggregates
]

def select(keys, pats):
    rx = [re.compile(p) for p in pats]
    return sorted({k for k in keys for r_ in rx if r_.match(k)})

def save_jsonl(path, rows):
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

def jsonl_to_csv(jpath, cpath):
    rows = [json.loads(l) for l in open(jpath)]
    if not rows:
        return 0
    cols = sorted({k for r_ in rows for k in r_}, key=lambda c: (c != "_step", c))
    with open(cpath, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(rows)

def pull_run(run, outdir, mode):
    os.makedirs(outdir, exist_ok=True)
    meta = mw.run_meta(ENTITY, PROJECT, run)
    with open(os.path.join(outdir, "meta.json"), "w") as f:
        json.dump({k: v for k, v in meta.items() if k != "historyKeys"}, f)
    hk = meta.get("historyKeys") or {}
    keys = hk.get("keys", hk)
    keys = sorted(keys.keys()) if isinstance(keys, dict) else sorted(keys)

    dense = select(keys, DENSE_PAT)
    evalk = select(keys, EVAL_PAT)
    mixw = sorted(k for k in keys if k.startswith("mixture/weight/"))
    specs = []
    names = []
    BASE = ["_step", "_timestamp"]
    if dense:
        specs.append({"keys": BASE + dense, "samples": 8000}); names.append("dense")
    if evalk:
        specs.append({"keys": BASE + evalk, "samples": 2000}); names.append("eval")
    if mixw:
        specs.append({"keys": BASE + ["mixture/stage"] + mixw, "samples": 600}); names.append("mixture")
    if mode == "hero":
        sysk = select(keys, SYSTEM_PAT)
        router = select(keys, ROUTER_PAT)
        if sysk:
            specs.append({"keys": BASE + sysk, "samples": 3000}); names.append("system")
        if router:
            specs.append({"keys": BASE + router, "samples": 2000}); names.append("router")

    results = mw.sampled(ENTITY, PROJECT, run, specs)
    summary = {"run": run, "state": meta["state"], "createdAt": meta["createdAt"],
               "heartbeatAt": meta.get("heartbeatAt"),
               "n_keys": len(keys), "dense_keys": len(dense), "eval_keys": len(evalk),
               "mixture_keys": len(mixw)}
    for name, rows in zip(names, results):
        jp = os.path.join(outdir, f"{name}.jsonl")
        save_jsonl(jp, rows)
        n = jsonl_to_csv(jp, os.path.join(outdir, f"{name}.csv"))
        summary[f"rows_{name}"] = n
        steps = [r.get("_step") for r in rows if r.get("_step") is not None]
        if steps:
            summary[f"step_range_{name}"] = [min(steps), max(steps)]
    return summary

def main():
    outdir, mode = sys.argv[1], sys.argv[2]
    runs = sys.argv[3:]
    summaries = []
    for run in runs:
        try:
            s = pull_run(run, os.path.join(outdir, run), mode)
            summaries.append(s)
            print(f"[OK] {run}: " + json.dumps({k: v for k, v in s.items() if k.startswith(('rows', 'step_range'))}, ensure_ascii=False))
        except Exception as e:
            print(f"[FAIL] {run}: {type(e).__name__} {str(e)[:200]}")
            summaries.append({"run": run, "error": str(e)[:200]})
    with open(os.path.join(outdir, "_summary.json"), "w") as f:
        json.dump(summaries, f, indent=1)

if __name__ == "__main__":
    main()
