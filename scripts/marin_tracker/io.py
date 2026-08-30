"""Small, deterministic file and metric helpers."""

import hashlib
import json
import os
import tempfile
from pathlib import Path


def read_json(path):
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temp_name = handle.name
    os.replace(temp_name, path)


def atomic_write_json(path, value):
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
    )


def metric_series(rows, key):
    """Return sorted ``[step, value, timestamp]`` points for one metric."""
    points = []
    for row in rows:
        value = row.get(key)
        step = row.get("_step")
        if value is None or step is None:
            continue
        points.append([int(step), float(value), row.get("_timestamp")])
    points.sort(key=lambda point: point[0])
    return points


def compact_series(points, limit=1_200):
    """Deterministic stride sampling that always preserves the final point."""
    if len(points) <= limit:
        return points
    stride = max(1, (len(points) + limit - 1) // limit)
    compact = points[::stride]
    if compact[-1] != points[-1]:
        compact.append(points[-1])
    return compact


def nested_value(mapping, *keys, default=None):
    current = mapping
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
        if isinstance(current, dict) and set(current) == {"value"}:
            current = current["value"]
    return current
