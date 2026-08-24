from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import track_marin as tracker


DAY = date(2026, 8, 23)
UTC = timezone.utc
NOW = datetime(2026, 8, 24, 9, 31, 47, tzinfo=UTC)


class DummyClient:
    def __init__(self) -> None:
        self.attempts = 0


def client_factory() -> DummyClient:
    return DummyClient()


def successful_collector(name: str, record_count: int = 1):
    def collect(client: DummyClient, window: tracker.Window) -> tracker.Collection:
        client.attempts += 1
        return tracker.Collection(
            payload={"name": name, "date": window.day.isoformat()},
            record_count=record_count,
            urls=(f"https://example.test/{name}",),
        )

    return collect


def failed_collector(client: DummyClient, window: tracker.Window) -> tracker.Collection:
    del window
    client.attempts += 1
    raise tracker.CollectionError("upstream unavailable")


def source(name: str, collector) -> tracker.SourceSpec:
    return tracker.SourceSpec(
        name=name,
        label=name,
        url=f"https://example.test/{name}",
        evidence_file=f"{name}.json",
        collector=collector,
    )


class TrackingPublicationTests(unittest.TestCase):
    def test_incomplete_utc_day_is_rejected_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "completed UTC day"):
                tracker.run_tracking(
                    window=tracker.make_window(NOW.date()),
                    repo_root=root,
                    source_specs=(source("good", successful_collector("good")),),
                    now=lambda: NOW,
                    client_factory=client_factory,
                )
            self.assertFalse((root / "data").exists())

    def test_partial_failure_publishes_complete_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                source_specs=(
                    source("good", successful_collector("good", 2)),
                    source("bad", failed_collector),
                ),
                now=lambda: NOW,
                client_factory=client_factory,
            )

            self.assertEqual(result, 0)
            snapshot = root / "data" / "snapshots" / DAY.isoformat()
            manifest = json.loads((snapshot / "manifest.json").read_text())
            self.assertEqual(manifest["overall_status"], "partial")
            self.assertEqual(manifest["successful_sources"], 1)
            self.assertEqual(manifest["failed_sources"], 1)
            self.assertEqual(manifest["collected_at"], "2026-08-24T09:31:47Z")
            self.assertTrue((snapshot / "good.json").is_file())
            self.assertFalse((snapshot / "bad.json").exists())
            self.assertTrue((root / "notes" / "daily" / "2026-08-23.md").is_file())
            self.assertFalse(list(snapshot.parent.glob(".2026-08-23-*")))

    def test_total_failure_returns_two_and_publishes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                source_specs=(
                    source("bad-one", failed_collector),
                    source("bad-two", failed_collector),
                ),
                now=lambda: NOW,
                client_factory=client_factory,
            )

            self.assertEqual(result, 2)
            self.assertFalse((root / "data" / "snapshots" / "2026-08-23").exists())
            self.assertFalse((root / "notes" / "daily" / "2026-08-23.md").exists())
            snapshots = root / "data" / "snapshots"
            self.assertFalse(list(snapshots.glob(".2026-08-23-*")))

    def test_total_failure_preserves_existing_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = root / "data" / "snapshots" / DAY.isoformat()
            snapshot.mkdir(parents=True)
            (snapshot / "manifest.json").write_text("old snapshot\n")
            note = (root / "notes" / "daily" / f"{DAY.isoformat()}.md").resolve()
            note.parent.mkdir(parents=True)
            note.write_text("old note\n")

            result = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                source_specs=(source("bad", failed_collector),),
                now=lambda: NOW,
                client_factory=client_factory,
            )

            self.assertEqual(result, 2)
            self.assertEqual((snapshot / "manifest.json").read_text(), "old snapshot\n")
            self.assertEqual(note.read_text(), "old note\n")

    def test_allow_total_failure_writes_diagnostic_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                allow_total_failure=True,
                source_specs=(source("bad", failed_collector),),
                now=lambda: NOW,
                client_factory=client_factory,
            )

            self.assertEqual(result, 0)
            snapshot = root / "data" / "snapshots" / DAY.isoformat()
            manifest = json.loads((snapshot / "manifest.json").read_text())
            self.assertEqual(manifest["overall_status"], "total_failure_allowed")
            self.assertEqual(manifest["successful_sources"], 0)
            self.assertEqual(manifest["sources"][0]["error"], "CollectionError: upstream unavailable")

    def test_partial_rerun_preserves_previous_successful_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            specs = (
                source("source-a", successful_collector("old-a", 3)),
                source("source-b", failed_collector),
            )
            first = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                source_specs=specs,
                now=lambda: NOW,
                client_factory=client_factory,
            )
            self.assertEqual(first, 0)
            snapshot = root / "data" / "snapshots" / DAY.isoformat()
            self.assertFalse((snapshot / "source-b.json").exists())

            second = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                source_specs=(
                    source("source-a", failed_collector),
                    source("source-b", successful_collector("new-b", 1)),
                ),
                now=lambda: datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
                client_factory=client_factory,
            )

            self.assertEqual(second, 0)
            self.assertEqual(json.loads((snapshot / "source-a.json").read_text())["name"], "old-a")
            self.assertEqual(json.loads((snapshot / "source-b.json").read_text())["name"], "new-b")
            manifest = json.loads((snapshot / "manifest.json").read_text())
            source_a = next(item for item in manifest["sources"] if item["name"] == "source-a")
            self.assertEqual(source_a["status"], "preserved")
            self.assertTrue(source_a["preserved_evidence"])
            self.assertEqual(source_a["evidence_file"], "source-a.json")
            self.assertEqual(manifest["preserved_sources"], 1)
            self.assertEqual(manifest["overall_status"], "success")

    def test_allowed_total_failure_does_not_delete_previous_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                source_specs=(source("source-a", successful_collector("old-a")),),
                now=lambda: NOW,
                client_factory=client_factory,
            )
            self.assertEqual(first, 0)

            second = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                allow_total_failure=True,
                refresh_existing=True,
                source_specs=(source("source-a", failed_collector),),
                now=lambda: datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
                client_factory=client_factory,
            )

            self.assertEqual(second, 0)
            snapshot = root / "data" / "snapshots" / DAY.isoformat()
            self.assertTrue((snapshot / "source-a.json").is_file())
            manifest = json.loads((snapshot / "manifest.json").read_text())
            self.assertEqual(manifest["overall_status"], "total_failure_allowed")
            self.assertEqual(manifest["preserved_sources"], 1)

    def test_existing_success_is_immutable_without_explicit_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                source_specs=(source("source-a", successful_collector("old", 5)),),
                now=lambda: NOW,
                client_factory=client_factory,
            )
            self.assertEqual(first, 0)

            second = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                source_specs=(source("source-a", successful_collector("new", 0)),),
                now=lambda: datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
                client_factory=client_factory,
            )

            self.assertEqual(second, 0)
            snapshot = root / "data" / "snapshots" / DAY.isoformat()
            self.assertEqual(json.loads((snapshot / "source-a.json").read_text())["name"], "old")
            manifest = json.loads((snapshot / "manifest.json").read_text())
            self.assertEqual(manifest["collected_at"], "2026-08-24T09:31:47Z")

    def test_preserved_provenance_survives_consecutive_failed_refreshes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                source_specs=(source("source-a", successful_collector("old")),),
                now=lambda: NOW,
                client_factory=client_factory,
            )
            for hour in (10, 11):
                tracker.run_tracking(
                    window=tracker.make_window(DAY),
                    repo_root=root,
                    allow_total_failure=True,
                    refresh_existing=True,
                    source_specs=(source("source-a", failed_collector),),
                    now=lambda hour=hour: datetime(2026, 8, 24, hour, 0, tzinfo=UTC),
                    client_factory=client_factory,
                )

            manifest_path = (
                root / "data" / "snapshots" / DAY.isoformat() / "manifest.json"
            )
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(
                manifest["sources"][0]["preserved_from_collected_at"],
                "2026-08-24T09:31:47Z",
            )

    def test_note_publish_error_rolls_snapshot_and_note_back_together(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = tracker.run_tracking(
                window=tracker.make_window(DAY),
                repo_root=root,
                source_specs=(source("source-a", successful_collector("old")),),
                now=lambda: NOW,
                client_factory=client_factory,
            )
            self.assertEqual(first, 0)
            snapshot = root / "data" / "snapshots" / DAY.isoformat()
            note = (root / "notes" / "daily" / f"{DAY.isoformat()}.md").resolve()
            old_note = note.read_text()
            real_replace = os.replace
            failed_once = False

            def fail_note_install(source_path, destination_path):
                nonlocal failed_once
                source_path = Path(source_path)
                destination_path = Path(destination_path)
                if (
                    not failed_once
                    and destination_path == note
                    and ".backup-" not in source_path.name
                ):
                    failed_once = True
                    raise OSError("simulated note publish failure")
                return real_replace(source_path, destination_path)

            with patch.object(tracker.os, "replace", side_effect=fail_note_install):
                with self.assertRaisesRegex(OSError, "simulated note publish failure"):
                    tracker.run_tracking(
                        window=tracker.make_window(DAY),
                        repo_root=root,
                        refresh_existing=True,
                        source_specs=(source("source-a", successful_collector("new")),),
                        now=lambda: datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
                        client_factory=client_factory,
                    )

            self.assertEqual(json.loads((snapshot / "source-a.json").read_text())["name"], "old")
            self.assertEqual(note.read_text(), old_note)


class StubGitHubClient:
    def __init__(self) -> None:
        self.attempts = 0

    def get_json(self, url: str):
        self.attempts += 1
        if "/issues?" in url:
            payload = [
                {
                    "number": 123,
                    "title": "Recover pretraining run",
                    "state": "closed",
                    "state_reason": "completed",
                    "labels": [{"name": "experiment"}],
                    "user": {"login": "maintainer"},
                    "body": "The run was interrupted.",
                    "created_at": "2026-08-22T10:00:00Z",
                    "updated_at": "2026-08-23T12:00:00Z",
                    "closed_at": "2026-08-23T12:00:00Z",
                    "html_url": "https://github.com/marin-community/marin/issues/123",
                    "comments": 1,
                    "comments_url": "https://api.github.com/repos/marin-community/marin/issues/123/comments",
                },
                {
                    "number": 124,
                    "title": "Future update",
                    "updated_at": "2026-08-25T00:00:00Z",
                    "comments_url": "https://api.github.com/repos/marin-community/marin/issues/124/comments",
                },
            ]
        elif "/comments?" in url:
            payload = [
                {
                    "id": 99,
                    "user": {"login": "operator"},
                    "body": "Restored from checkpoint; loss is stable.",
                    "created_at": "2026-08-23T11:00:00Z",
                    "updated_at": "2026-08-23T11:30:00Z",
                    "html_url": "https://github.com/marin-community/marin/issues/123#issuecomment-99",
                }
            ]
        else:
            raise AssertionError(f"unexpected URL: {url}")
        response = tracker.HttpResponse(b"", {}, url, 200)
        return payload, response


class GitHubEvidenceTests(unittest.TestCase):
    def test_commit_window_is_half_open_and_queries_one_second_early(self) -> None:
        class CommitClient:
            attempts = 0
            requested_url = ""

            def get_json(self, url: str):
                self.attempts += 1
                self.requested_url = url

                def item(sha: str, timestamp: str):
                    return {
                        "sha": sha,
                        "html_url": f"https://github.com/example/{sha}",
                        "author": {"login": "maintainer"},
                        "commit": {
                            "message": sha,
                            "author": {"name": "Maintainer", "date": timestamp},
                            "committer": {"date": timestamp},
                            "verification": {"verified": True, "reason": "valid"},
                        },
                    }

                payload = [
                    item("at-start", "2026-08-23T00:00:00Z"),
                    item("at-end", "2026-08-24T00:00:00Z"),
                ]
                return payload, tracker.HttpResponse(b"", {}, url, 200)

        client = CommitClient()
        collection = tracker.collect_github_commits(client, tracker.make_window(DAY))

        self.assertEqual([item["sha"] for item in collection.payload["commits"]], ["at-start"])
        self.assertIn("since=2026-08-22T23%3A59%3A59Z", client.requested_url)

    def test_issue_comment_body_author_times_and_url_are_preserved(self) -> None:
        collection = tracker.collect_github_issues(
            StubGitHubClient(), tracker.make_window(DAY)
        )

        self.assertEqual(collection.record_count, 2)
        self.assertEqual(collection.payload["issue_count"], 1)
        self.assertEqual(collection.payload["comment_count"], 1)
        comment = collection.payload["issues"][0]["comments"][0]
        self.assertEqual(comment["author"], "operator")
        self.assertEqual(comment["body"], "Restored from checkpoint; loss is stable.")
        self.assertEqual(comment["created_at"], "2026-08-23T11:00:00Z")
        self.assertEqual(comment["updated_at"], "2026-08-23T11:30:00Z")
        self.assertTrue(comment["url"].endswith("#issuecomment-99"))

    def test_mutable_issue_updated_after_midnight_is_included(self) -> None:
        class OverlapClient:
            attempts = 0

            def get_json(self, url: str):
                self.attempts += 1
                payload = [
                    {
                        "number": 200,
                        "title": "Late recovery update",
                        "state": "open",
                        "state_reason": None,
                        "labels": [],
                        "user": {"login": "maintainer"},
                        "body": "Updated shortly after midnight.",
                        "created_at": "2026-08-23T23:50:00Z",
                        "updated_at": "2026-08-24T01:00:00Z",
                        "closed_at": None,
                        "html_url": "https://github.com/marin-community/marin/issues/200",
                        "comments": 0,
                        "comments_url": "https://api.github.com/repos/marin-community/marin/issues/200/comments",
                    }
                ]
                return payload, tracker.HttpResponse(b"", {}, url, 200)

        collection = tracker.collect_github_issues(
            OverlapClient(),
            tracker.make_window(
                DAY, observed_at=datetime(2026, 8, 24, 2, 17, tzinfo=UTC)
            ),
        )

        self.assertEqual(collection.payload["issue_count"], 0)
        self.assertEqual(collection.payload["spillover_issue_count"], 1)
        issue = collection.payload["spillover_issues"][0]
        self.assertFalse(issue["updated_in_target_window"])
        self.assertEqual(collection.payload["observation_end"], "2026-08-24T02:17:00Z")


class FakeUrlResponse:
    def __init__(self, body: bytes = b"{}") -> None:
        self.body = body
        self.headers: dict[str, str] = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.body

    def getcode(self) -> int:
        return 200

    def geturl(self) -> str:
        return "https://example.test/data"


class HttpRetryTests(unittest.TestCase):
    def test_retryable_http_error_uses_exponential_backoff(self) -> None:
        url = "https://example.test/data"
        error = HTTPError(
            url,
            503,
            "Service Unavailable",
            {"Content-Type": "application/json"},
            io.BytesIO(b'{"message":"try later"}'),
        )
        delays: list[float] = []
        client = tracker.HttpClient(max_attempts=3, sleep=delays.append)

        with patch.object(tracker, "urlopen", side_effect=[error, FakeUrlResponse()]):
            response = client.request(url)

        self.assertEqual(response.status, 200)
        self.assertEqual(client.attempts, 2)
        self.assertEqual(delays, [1.0])

    def test_permission_error_is_not_retried(self) -> None:
        url = "https://example.test/data"
        error = HTTPError(
            url,
            403,
            "Forbidden",
            {"Content-Type": "application/json"},
            io.BytesIO(b'{"message":"forbidden"}'),
        )
        delays: list[float] = []
        client = tracker.HttpClient(max_attempts=3, sleep=delays.append)

        with patch.object(tracker, "urlopen", side_effect=error):
            with self.assertRaisesRegex(tracker.CollectionError, "HTTP 403"):
                client.request(url)

        self.assertEqual(client.attempts, 1)
        self.assertEqual(delays, [])

    def test_rejected_github_token_falls_back_to_anonymous_read(self) -> None:
        url = "https://api.github.com/repos/marin-community/marin"
        requests = []

        def respond(request, timeout):
            del timeout
            requests.append(request)
            if len(requests) == 1:
                raise HTTPError(
                    url,
                    403,
                    "Forbidden",
                    {"Content-Type": "application/json"},
                    io.BytesIO(b'{"message":"token not allowed"}'),
                )
            return FakeUrlResponse()

        client = tracker.HttpClient(
            github_token="not-a-real-token", max_attempts=3, sleep=lambda _: None
        )
        with patch.object(tracker, "urlopen", side_effect=respond):
            response = client.request(url)
            second_response = client.request(url)

        self.assertEqual(response.status, 200)
        self.assertEqual(second_response.status, 200)
        self.assertEqual(client.attempts, 3)
        self.assertEqual(requests[0].get_header("Authorization"), "Bearer not-a-real-token")
        self.assertIsNone(requests[1].get_header("Authorization"))
        self.assertIsNone(requests[2].get_header("Authorization"))

    def test_github_rate_limit_403_is_retryable(self) -> None:
        url = "https://api.github.com/repos/marin-community/marin"
        error = HTTPError(
            url,
            403,
            "Forbidden",
            {
                "Content-Type": "application/json",
                "X-RateLimit-Remaining": "0",
                "Retry-After": "0",
            },
            io.BytesIO(b'{"message":"API rate limit exceeded"}'),
        )
        delays: list[float] = []
        client = tracker.HttpClient(max_attempts=2, sleep=delays.append)

        with patch.object(tracker, "urlopen", side_effect=[error, FakeUrlResponse()]):
            response = client.request(url)

        self.assertEqual(response.status, 200)
        self.assertEqual(client.attempts, 2)
        self.assertEqual(delays, [0.0])

    def test_authenticated_rate_limit_retries_without_disabling_token(self) -> None:
        url = "https://api.github.com/repos/marin-community/marin"
        error = HTTPError(
            url,
            403,
            "Forbidden",
            {"X-RateLimit-Remaining": "0", "Retry-After": "0"},
            io.BytesIO(b'{"message":"secondary rate limit"}'),
        )
        requests = []

        def respond(request, timeout):
            del timeout
            requests.append(request)
            if len(requests) == 1:
                raise error
            return FakeUrlResponse()

        client = tracker.HttpClient(
            github_token="token", max_attempts=2, sleep=lambda _: None
        )
        with patch.object(tracker, "urlopen", side_effect=respond):
            response = client.request(url)

        self.assertEqual(response.status, 200)
        self.assertEqual(client.attempts, 2)
        self.assertEqual(requests[0].get_header("Authorization"), "Bearer token")
        self.assertEqual(requests[1].get_header("Authorization"), "Bearer token")
        self.assertFalse(client.github_auth_disabled)


if __name__ == "__main__":
    unittest.main()
