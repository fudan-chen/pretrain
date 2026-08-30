#!/usr/bin/env python3
"""Probe the hero run's systemMetrics (NVLink/PCIe/power/temp telemetry)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import marin_wandb as mw

E, P = "marin-community", "marin_moe"
RUN = "hero-12d8b6f0-dee637"
Q = """query($ee:String!,$p:String!,$r:String!){
  project(name:$p, entityName:$ee){ run(name:$r){ systemMetrics } } }"""

d = mw.gql(Q, {"ee": E, "p": P, "r": RUN}, timeout=240, retries=2)
smraw = d["project"]["run"]["systemMetrics"]
sm = json.loads(smraw) if isinstance(smraw, str) else smraw
keys = list(sm.keys()) if isinstance(sm, dict) else []
print("systemMetrics keys:", len(keys))
nv = sorted([k for k in keys if "nvlink" in k.lower()])
print("nvlink keys:", nv[:10])
sample = [k for k in keys if "nvlink" in k.lower()] or keys
if sample:
    k0 = sample[0]
    v = sm[k0]
    print("sample key:", k0, "| type:", type(v).__name__)
    if isinstance(v, dict):
        print("  dict keys:", list(v.keys())[:8])
        for kk in ("x", "y", "data", "points", "timestamps", "values"):
            if kk in v:
                seq = v[kk]
                try:
                    print(f"  {kk}: len={len(seq)} first={seq[0]} last={seq[-1]}")
                except Exception:
                    pass
    elif isinstance(v, list) and v:
        print("  list len:", len(v), "| first:", v[0], "| last:", v[-1])
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "hero", RUN, "system_metrics.json")
out = os.path.abspath(out)
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    json.dump(sm, f)
print("saved:", out, os.path.getsize(out), "bytes")
