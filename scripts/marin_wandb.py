"""marin_wandb.py - Anonymous read-only Weights & Biases GraphQL client (stdlib only).

Works with PUBLIC W&B projects (e.g. marin-community/marin_moe) without an API key.
Used by the Marin 535B hero-run tracker to harvest training telemetry.
"""
import json, time, urllib.request

GQL_URL = "https://api.wandb.ai/graphql"

class WandbError(RuntimeError):
    pass

def gql(query, variables=None, retries=4, timeout=120):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(GQL_URL, data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode())
            if payload.get("errors"):
                raise WandbError(json.dumps(payload["errors"])[:500])
            return payload.get("data", {})
        except WandbError:
            raise
        except Exception as e:
            last = e
            time.sleep(min(2 ** attempt * 2, 20))
    raise WandbError(f"request failed after {retries} attempts: {last}")

_Q_RUN = """query($e:String!,$p:String!,$r:String!){
  project(name:$p, entityName:$e){
    run(name:$r){ name displayName state createdAt heartbeatAt tags notes
                  config summaryMetrics historyKeys } } }"""

_Q_SAMPLED = """query($e:String!,$p:String!,$r:String!,$specs:[JSONString!]!){
  project(name:$p, entityName:$e){ run(name:$r){ sampledHistory(specs:$specs) } } }"""

_Q_RUNS = """query($e:String!,$p:String!,$f:JSONString){
  project(name:$p, entityName:$e){ runs(first:60, filters:$f){
    edges{ node{ name displayName state createdAt heartbeatAt tags } } } } }"""

def run_meta(entity, project, run):
    d = gql(_Q_RUN, {"e": entity, "p": project, "r": run})
    node = d["project"]["run"]
    if node is None:
        raise WandbError(f"run not found: {run}")
    for k in ("config", "summaryMetrics"):
        if node.get(k):
            node[k] = json.loads(node[k])
    return node

def history_keys(entity, project, run):
    meta = run_meta(entity, project, run)
    hk = meta.get("historyKeys") or {}
    keys = hk.get("keys", hk)
    return sorted(keys.keys()) if isinstance(keys, dict) else sorted(keys)

def list_runs(entity, project, display_name_regex=None):
    f = json.dumps({"display_name": {"$regex": display_name_regex}}) if display_name_regex else None
    d = gql(_Q_RUNS, {"e": entity, "p": project, "f": f})
    return [e_["node"] for e_ in d["project"]["runs"]["edges"]]

def sampled(entity, project, run, specs):
    """specs: list of {"keys": [...], "samples": N}. Returns list (per spec) of row dicts."""
    d = gql(_Q_SAMPLED, {"e": entity, "p": project, "r": run,
                         "specs": [json.dumps(s) for s in specs]})
    out = []
    for spec_rows in d["project"]["run"]["sampledHistory"]:
        rows = [json.loads(x) if isinstance(x, str) else x for x in spec_rows]
        out.append(rows)
    return out
