import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_site import check  # noqa: E402
from marin_tracker.claims import validate_claim_ledger  # noqa: E402
from marin_tracker.ladder import validate_baseline  # noqa: E402


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _check_required(instance, schema, schema_path, root_schema=None, location="$"):
    """Validate the contract subset used here without adding a test dependency."""
    root_schema = schema if root_schema is None else root_schema
    if schema is True:
        return
    if schema is False:
        raise AssertionError(f"{location}: schema forbids this value")
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/"):
            target = root_schema
            for part in ref[2:].split("/"):
                target = target[part]
            _check_required(instance, target, schema_path, root_schema, location)
        else:
            target_path = schema_path.parent / ref
            target = _load(target_path)
            _check_required(instance, target, target_path, target, location)
        return

    expected_type = schema.get("type")
    if expected_type:
        names = [expected_type] if isinstance(expected_type, str) else expected_type
        matches = {
            "object": lambda value: isinstance(value, dict),
            "array": lambda value: isinstance(value, list),
            "string": lambda value: isinstance(value, str),
            "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
            "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": lambda value: isinstance(value, bool),
            "null": lambda value: value is None,
        }
        if not any(matches[name](instance) for name in names):
            raise AssertionError(f"{location}: expected type {names}, got {type(instance).__name__}")
    if "const" in schema and instance != schema["const"]:
        raise AssertionError(f"{location}: expected {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise AssertionError(f"{location}: {instance!r} is not in {schema['enum']!r}")
    if "oneOf" in schema:
        successes = 0
        for branch in schema["oneOf"]:
            try:
                _check_required(instance, branch, schema_path, root_schema, location)
                successes += 1
            except AssertionError:
                pass
        if successes != 1:
            raise AssertionError(f"{location}: expected exactly one matching schema, got {successes}")
        return
    if isinstance(instance, dict):
        missing = [key for key in schema.get("required", []) if key not in instance]
        if missing:
            raise AssertionError(f"{location}: missing required fields {missing}")
        for key, child_schema in schema.get("properties", {}).items():
            if key in instance:
                _check_required(
                    instance[key], child_schema, schema_path, root_schema, f"{location}.{key}"
                )
    if isinstance(instance, list) and isinstance(schema.get("items"), dict):
        for index, value in enumerate(instance):
            _check_required(value, schema["items"], schema_path, root_schema, f"{location}[{index}]")
    for condition in schema.get("allOf", []):
        if "if" not in condition:
            _check_required(instance, condition, schema_path, root_schema, location)
            continue
        try:
            _check_required(instance, condition["if"], schema_path, root_schema, location)
        except AssertionError:
            continue
        _check_required(instance, condition.get("then", True), schema_path, root_schema, location)


class ContentContractTests(unittest.TestCase):
    def test_registries_are_structured_and_linked(self):
        registries = {
            "sources": _load(ROOT / "registry" / "sources.json"),
            "runs": _load(ROOT / "registry" / "runs.json"),
            "metrics": _load(ROOT / "registry" / "metrics.json"),
        }
        for name, payload in registries.items():
            schema_path = ROOT / "schemas" / f"{name}_registry.schema.json"
            _check_required(payload, _load(schema_path), schema_path)

        source_ids = {source["id"] for source in registries["sources"]["sources"]}
        runs = registries["runs"]["runs"]
        metrics = registries["metrics"]["metrics"]
        ids = [metric["id"] for metric in metrics]
        keys = [metric["key"] for metric in metrics]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(metric["source_id"] in source_ids for metric in metrics))
        self.assertTrue(all(run["source_id"] in source_ids for run in runs))

        baseline = _load(ROOT / "data" / "baselines" / "matched_progress_v1.json")
        required_ids = {item["id"] for item in baseline["applicability"]["requirements"]}
        self.assertEqual(set(runs[0]["baseline_applicability"]["required_requirement_ids"]), required_ids)

    def test_registry_schema_rejects_missing_audit_field(self):
        payload = _load(ROOT / "registry" / "sources.json")
        del payload["sources"][0]["canonical_url"]
        schema_path = ROOT / "schemas" / "sources_registry.schema.json"
        with self.assertRaises(AssertionError):
            _check_required(payload, _load(schema_path), schema_path)

    def test_generated_products_pass_python_and_schema_contracts(self):
        baseline = _load(ROOT / "data" / "baselines" / "matched_progress_v1.json")
        status = _load(ROOT / "data" / "derived" / "current_status.json")
        ledger = _load(ROOT / "data" / "derived" / "claim_ledger.json")
        self.assertTrue(validate_baseline(baseline))
        self.assertTrue(validate_claim_ledger(ledger))

        for filename, payload in (
            ("matched_progress.schema.json", baseline),
            ("current_status.schema.json", status),
            ("claim_ledger.schema.json", ledger),
        ):
            schema_path = ROOT / "schemas" / filename
            _check_required(payload, _load(schema_path), schema_path)

        self.assertIn("hero_issue_snapshot", status["artifacts"])
        selectors = [
            evidence.get("record_selector")
            for claim in ledger["claims"]
            for evidence in claim["evidence"]
            if "record_selector" in evidence
        ]
        self.assertIn({"number": 8435}, selectors)

    def test_contracts_reject_intentionally_deleted_fields(self):
        baseline = _load(ROOT / "data" / "baselines" / "matched_progress_v1.json")
        broken_baseline = copy.deepcopy(baseline)
        del broken_baseline["applicability"]["requirements"]
        with self.assertRaises(ValueError):
            validate_baseline(broken_baseline)

        ledger = _load(ROOT / "data" / "derived" / "claim_ledger.json")
        broken_ledger = copy.deepcopy(ledger)
        derived = next(claim for claim in broken_ledger["claims"] if claim["kind"] == "DERIVED")
        del derived["derivation"]
        with self.assertRaises(ValueError):
            validate_claim_ledger(broken_ledger)

        status = _load(ROOT / "data" / "derived" / "current_status.json")
        del status["baseline_applicability"]["checks"][0]["result"]
        schema_path = ROOT / "schemas" / "current_status.schema.json"
        with self.assertRaises(AssertionError):
            _check_required(status, _load(schema_path), schema_path)

    def test_schema_files_are_valid_json(self):
        for path in (ROOT / "schemas").glob("*.json"):
            with self.subTest(path=path.name):
                schema = json.loads(path.read_text())
                self.assertIn("$schema", schema)

    def test_generated_site_links_and_charts(self):
        pages, errors = check(ROOT)
        self.assertGreaterEqual(len(pages), 6)
        self.assertEqual(errors, [])

    def test_v2_source_has_no_legacy_prediction_symbols(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "scripts" / "marin_tracker").glob("*.py")
        )
        self.assertNotIn("A_FIT", source)
        self.assertNotIn("ALPHA_FIT", source)
        self.assertNotIn("C_FULL_HERO *", source)

    def test_new_site_does_not_use_canvas(self):
        html = "\n".join(
            path.read_text(encoding="utf-8") for path in (ROOT / "site").rglob("*.html")
        )
        self.assertNotIn("<canvas", html)

    def test_issue_evidence_page_exposes_the_claim_selector(self):
        page = (
            ROOT
            / "site"
            / "evidence"
            / "data-snapshots-2026-08-28-github-issues-json"
            / "index.html"
        ).read_text(encoding="utf-8")
        self.assertIn("&quot;number&quot;: 8435", page)
        self.assertIn("25%", page)
        self.assertIn("/artifacts/data/snapshots/2026-08-28/github_issues.json", page)


if __name__ == "__main__":
    unittest.main()
