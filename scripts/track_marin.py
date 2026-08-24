#!/usr/bin/env python3
"""Collect a daily, auditable snapshot of public Marin project activity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GITHUB_REPOSITORY = "marin-community/marin"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
HUGGING_FACE_ORG = "marin-community"
MARIN_SITE = "https://marin.community/"

RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 60.0
MAX_PAGES = 100
MUTABLE_SOURCE_OVERLAP = timedelta(days=1)
UTC = timezone.utc


class CollectionError(RuntimeError):
    """Raised when an upstream response cannot be used as evidence."""


@dataclass(frozen=True)
class Window:
    day: date
    start: datetime
    end: datetime
    observed_at: datetime | None = None

    @property
    def observation_end(self) -> datetime:
        """Upper bound for mutable records that can cross the UTC boundary."""
        cap = self.end + MUTABLE_SOURCE_OVERLAP
        if self.observed_at is None:
            return self.end
        return min(cap, self.observed_at.astimezone(UTC))


@dataclass(frozen=True)
class HttpResponse:
    body: bytes
    headers: Mapping[str, str]
    url: str
    status: int


@dataclass(frozen=True)
class Collection:
    payload: Any
    record_count: int
    urls: tuple[str, ...]


Collector = Callable[["HttpClient", Window], Collection]


@dataclass(frozen=True)
class SourceSpec:
    name: str
    label: str
    url: str
    evidence_file: str
    collector: Collector


@dataclass
class SourceRun:
    spec: SourceSpec
    status: str
    attempts: int
    record_count: int = 0
    urls: tuple[str, ...] = ()
    error: str | None = None
    collection: Collection | None = None
    preserved_evidence: bool = False
    preserved_from_collected_at: str | None = None


@dataclass(frozen=True)
class PreviousEvidence:
    payload: Any
    record_count: int
    urls: tuple[str, ...]
    collected_at: str


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_z(value: datetime) -> str:
    value = value.astimezone(UTC).replace(microsecond=0)
    return value.isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise CollectionError(f"invalid timestamp: {value!r}")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CollectionError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise CollectionError(f"timestamp has no timezone: {value!r}")
    return parsed.astimezone(UTC)


def make_window(day: date, *, observed_at: datetime | None = None) -> Window:
    if observed_at is not None and observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return Window(
        day=day,
        start=start,
        end=start + timedelta(days=1),
        observed_at=observed_at,
    )


def _compact_error_body(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace")
    try:
        decoded = json.loads(text)
        if isinstance(decoded, dict) and decoded.get("message"):
            text = str(decoded["message"])
    except (json.JSONDecodeError, TypeError):
        pass
    return re.sub(r"\s+", " ", text).strip()[:500]


class HttpClient:
    """Small stdlib HTTP client with bounded retry and request accounting."""

    def __init__(
        self,
        *,
        github_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        self.github_token = github_token
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.sleep = sleep
        self.attempts = 0
        self.github_auth_disabled = False

    def _headers(
        self,
        url: str,
        headers: Mapping[str, str] | None,
        *,
        use_github_token: bool,
    ) -> dict[str, str]:
        merged = {
            "Accept": "application/json",
            "User-Agent": "fudan-chen-pretrain-marin-tracker/1.0",
        }
        if headers:
            merged.update(headers)
        if (
            use_github_token
            and not self.github_auth_disabled
            and self.github_token
            and url.startswith("https://api.github.com/")
        ):
            merged["Authorization"] = f"Bearer {self.github_token}"
            merged["X-GitHub-Api-Version"] = "2022-11-28"
        return merged

    def _retry_delay(self, attempt: int, headers: Mapping[str, str]) -> float:
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after:
            try:
                return min(MAX_RETRY_DELAY_SECONDS, max(0.0, float(retry_after)))
            except ValueError:
                pass
        reset_at = headers.get("X-RateLimit-Reset") or headers.get("x-ratelimit-reset")
        if reset_at:
            try:
                reset_delay = max(0.0, float(reset_at) - time.time())
                return min(MAX_RETRY_DELAY_SECONDS, reset_delay)
            except ValueError:
                pass
        return min(MAX_RETRY_DELAY_SECONDS, float(2 ** (attempt - 1)))

    def request(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        last_error: BaseException | None = None
        retry_number = 0
        use_github_token = bool(
            self.github_token
            and not self.github_auth_disabled
            and url.startswith("https://api.github.com/")
        )
        used_anonymous_fallback = False
        while True:
            self.attempts += 1
            request = Request(
                url,
                headers=self._headers(
                    url, headers, use_github_token=use_github_token
                ),
                method="GET",
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
                    status = int(response.getcode())
                    if not 200 <= status < 300:
                        raise CollectionError(f"unexpected HTTP status {status} from {url}")
                    return HttpResponse(
                        body=body,
                        headers=dict(response.headers.items()),
                        url=response.geturl(),
                        status=status,
                    )
            except HTTPError as exc:
                body = exc.read()
                response_headers = dict(exc.headers.items()) if exc.headers else {}
                detail = _compact_error_body(body)
                message = f"HTTP {exc.code} from {url}"
                if detail:
                    message += f": {detail}"
                last_error = CollectionError(message)
                remaining = response_headers.get(
                    "X-RateLimit-Remaining",
                    response_headers.get("x-ratelimit-remaining"),
                )
                is_rate_limit = exc.code == 429 or (
                    exc.code == 403
                    and (
                        remaining == "0"
                        or bool(
                            response_headers.get("Retry-After")
                            or response_headers.get("retry-after")
                        )
                        or "rate limit" in detail.lower()
                    )
                )
                if (
                    exc.code in {401, 403}
                    and use_github_token
                    and not used_anonymous_fallback
                    and not is_rate_limit
                ):
                    # Installation tokens are scoped. Public cross-repository reads
                    # may still work anonymously even when the token is rejected.
                    use_github_token = False
                    self.github_auth_disabled = True
                    used_anonymous_fallback = True
                    continue
                retry_number += 1
                if (
                    (
                        exc.code not in RETRYABLE_HTTP_STATUSES
                        and not is_rate_limit
                    )
                    or retry_number >= self.max_attempts
                ):
                    raise last_error from exc
                self.sleep(self._retry_delay(retry_number, response_headers))
            except (URLError, TimeoutError, socket.timeout, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                last_error = CollectionError(f"network error from {url}: {reason}")
                retry_number += 1
                if retry_number >= self.max_attempts:
                    raise last_error from exc
                self.sleep(self._retry_delay(retry_number, {}))

    def get_json(self, url: str) -> tuple[Any, HttpResponse]:
        response = self.request(url)
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CollectionError(f"invalid JSON from {url}: {exc}") from exc
        return payload, response

    def get_text(self, url: str) -> tuple[str, HttpResponse]:
        response = self.request(url, headers={"Accept": "text/html,application/xhtml+xml"})
        try:
            return response.body.decode("utf-8"), response
        except UnicodeDecodeError as exc:
            raise CollectionError(f"invalid UTF-8 HTML from {url}: {exc}") from exc


def _next_link(headers: Mapping[str, str]) -> str | None:
    link_value = headers.get("Link") or headers.get("link")
    if not link_value:
        return None
    for part in link_value.split(","):
        match = re.match(r'\s*<([^>]+)>\s*;\s*rel="?([^";]+)"?', part)
        if match and match.group(2) == "next":
            return match.group(1)
    return None


def _expect_list(payload: Any, url: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise CollectionError(f"expected a JSON list from {url}, got {type(payload).__name__}")
    records: list[dict[str, Any]] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise CollectionError(f"invalid item {index} from {url}: expected an object")
        records.append(item)
    return records


def _required_text(record: Mapping[str, Any], key: str, source: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise CollectionError(f"missing {key!r} in response from {source}")
    return value


def _user_login(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("login"), str):
        return value["login"]
    return None


def _collect_issue_comments(client: HttpClient, comments_url: str) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    url: str | None = f"{comments_url}?{urlencode({'per_page': 100})}"
    seen: set[str] = set()
    pages = 0
    while url:
        if url in seen or pages >= MAX_PAGES:
            raise CollectionError(f"invalid or excessive pagination from {comments_url}")
        seen.add(url)
        pages += 1
        payload, response = client.get_json(url)
        for comment in _expect_list(payload, url):
            comments.append(
                {
                    "id": comment.get("id"),
                    "author": _user_login(comment.get("user")),
                    "body": comment.get("body") or "",
                    "created_at": comment.get("created_at"),
                    "updated_at": comment.get("updated_at"),
                    "url": comment.get("html_url"),
                }
            )
        url = _next_link(response.headers)
    return comments


def collect_github_issues(client: HttpClient, window: Window) -> Collection:
    query = urlencode(
        {
            "state": "all",
            # Query one second early, then filter locally, so an upstream
            # exclusive `since` interpretation cannot drop a midnight event.
            "since": iso_z(window.start - timedelta(seconds=1)),
            "sort": "updated",
            "direction": "asc",
            "per_page": 100,
        }
    )
    first_url = f"{GITHUB_API}/issues?{query}"
    url: str | None = first_url
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    pages = 0
    reached_end = False
    while url and not reached_end:
        if url in seen or pages >= MAX_PAGES:
            raise CollectionError(f"invalid or excessive pagination from {first_url}")
        seen.add(url)
        pages += 1
        payload, response = client.get_json(url)
        for issue in _expect_list(payload, url):
            updated_at = parse_timestamp(_required_text(issue, "updated_at", url))
            if updated_at >= window.observation_end:
                reached_end = True
                break
            if updated_at < window.start:
                continue
            if "pull_request" in issue:
                continue
            comments_url = _required_text(issue, "comments_url", url)
            comments = (
                _collect_issue_comments(client, comments_url)
                if int(issue.get("comments") or 0) > 0
                else []
            )
            labels = []
            for label in issue.get("labels") or []:
                if isinstance(label, dict) and isinstance(label.get("name"), str):
                    labels.append(label["name"])
            issues.append(
                {
                    "number": issue.get("number"),
                    "title": issue.get("title"),
                    "state": issue.get("state"),
                    "state_reason": issue.get("state_reason"),
                    "labels": labels,
                    "author": _user_login(issue.get("user")),
                    "body": issue.get("body") or "",
                    "created_at": issue.get("created_at"),
                    "updated_at": issue.get("updated_at"),
                    "updated_in_target_window": updated_at < window.end,
                    "closed_at": issue.get("closed_at"),
                    "url": issue.get("html_url"),
                    "comments": comments,
                }
            )
        if not reached_end:
            url = _next_link(response.headers)
    target_issues = [issue for issue in issues if issue["updated_in_target_window"]]
    spillover_issues = [issue for issue in issues if not issue["updated_in_target_window"]]
    comment_count = sum(len(issue["comments"]) for issue in target_issues)
    spillover_comment_count = sum(len(issue["comments"]) for issue in spillover_issues)
    payload = {
        "source": GITHUB_REPOSITORY,
        "window": {"start": iso_z(window.start), "end": iso_z(window.end)},
        "observation_end": iso_z(window.observation_end),
        "issue_count": len(target_issues),
        "comment_count": comment_count,
        "spillover_issue_count": len(spillover_issues),
        "spillover_comment_count": spillover_comment_count,
        "issues": target_issues,
        "spillover_issues": spillover_issues,
    }
    return Collection(
        payload,
        len(issues) + comment_count + spillover_comment_count,
        (first_url,),
    )


def collect_github_commits(client: HttpClient, window: Window) -> Collection:
    query = urlencode(
        {
            "since": iso_z(window.start - timedelta(seconds=1)),
            "until": iso_z(window.end),
            "per_page": 100,
        }
    )
    first_url = f"{GITHUB_API}/commits?{query}"
    url: str | None = first_url
    commits: list[dict[str, Any]] = []
    seen: set[str] = set()
    pages = 0
    while url:
        if url in seen or pages >= MAX_PAGES:
            raise CollectionError(f"invalid or excessive pagination from {first_url}")
        seen.add(url)
        pages += 1
        payload, response = client.get_json(url)
        for item in _expect_list(payload, url):
            commit = item.get("commit")
            if not isinstance(commit, dict):
                raise CollectionError(f"missing commit metadata in response from {url}")
            committed_at_raw = None
            committer = commit.get("committer")
            if isinstance(committer, dict):
                committed_at_raw = committer.get("date")
            if not isinstance(committed_at_raw, str):
                raise CollectionError(f"missing commit timestamp in response from {url}")
            committed_at = parse_timestamp(committed_at_raw)
            if not window.start <= committed_at < window.end:
                continue
            author_metadata = commit.get("author") if isinstance(commit.get("author"), dict) else {}
            verification = commit.get("verification") if isinstance(commit.get("verification"), dict) else {}
            commits.append(
                {
                    "sha": item.get("sha"),
                    "message": commit.get("message") or "",
                    "author": _user_login(item.get("author")),
                    "author_name": author_metadata.get("name"),
                    "authored_at": author_metadata.get("date"),
                    "committed_at": committed_at_raw,
                    "verified": verification.get("verified"),
                    "verification_reason": verification.get("reason"),
                    "url": item.get("html_url"),
                }
            )
        url = _next_link(response.headers)
    payload = {
        "source": GITHUB_REPOSITORY,
        "window": {"start": iso_z(window.start), "end": iso_z(window.end)},
        "commit_count": len(commits),
        "commits": commits,
    }
    return Collection(payload, len(commits), (first_url,))


def _normalize_hugging_face_item(item: Mapping[str, Any], kind: str) -> dict[str, Any]:
    identifier = item.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise CollectionError(f"missing Hugging Face {kind} id")
    prefix = "datasets/" if kind == "dataset" else ""
    return {
        "id": identifier,
        "kind": kind,
        "last_modified": item.get("lastModified"),
        "created_at": item.get("createdAt"),
        "sha": item.get("sha"),
        "private": item.get("private"),
        "gated": item.get("gated"),
        "downloads": item.get("downloads"),
        "likes": item.get("likes"),
        "pipeline_tag": item.get("pipeline_tag"),
        "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
        "url": f"https://huggingface.co/{prefix}{identifier}",
    }


def _collect_hugging_face_kind(
    client: HttpClient,
    window: Window,
    *,
    endpoint: str,
    kind: str,
) -> tuple[list[dict[str, Any]], str]:
    query = urlencode(
        {
            "author": HUGGING_FACE_ORG,
            "sort": "lastModified",
            "direction": "-1",
            "limit": 100,
            "full": "true",
        }
    )
    first_url = f"https://huggingface.co/api/{endpoint}?{query}"
    url: str | None = first_url
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    pages = 0
    reached_older_items = False
    while url and not reached_older_items:
        if url in seen or pages >= MAX_PAGES:
            raise CollectionError(f"invalid or excessive pagination from {first_url}")
        seen.add(url)
        pages += 1
        payload, response = client.get_json(url)
        for item in _expect_list(payload, url):
            modified_raw = _required_text(item, "lastModified", url)
            modified = parse_timestamp(modified_raw)
            if modified < window.start:
                reached_older_items = True
                break
            if modified >= window.observation_end:
                continue
            normalized = _normalize_hugging_face_item(item, kind)
            normalized["updated_in_target_window"] = modified < window.end
            results.append(normalized)
        if not reached_older_items:
            url = _next_link(response.headers)
    return results, first_url


def collect_hugging_face(client: HttpClient, window: Window) -> Collection:
    all_models, models_url = _collect_hugging_face_kind(
        client, window, endpoint="models", kind="model"
    )
    all_datasets, datasets_url = _collect_hugging_face_kind(
        client, window, endpoint="datasets", kind="dataset"
    )
    models = [item for item in all_models if item["updated_in_target_window"]]
    datasets = [item for item in all_datasets if item["updated_in_target_window"]]
    spillover_models = [
        item for item in all_models if not item["updated_in_target_window"]
    ]
    spillover_datasets = [
        item for item in all_datasets if not item["updated_in_target_window"]
    ]
    payload = {
        "source": HUGGING_FACE_ORG,
        "window": {"start": iso_z(window.start), "end": iso_z(window.end)},
        "observation_end": iso_z(window.observation_end),
        "model_count": len(models),
        "dataset_count": len(datasets),
        "spillover_model_count": len(spillover_models),
        "spillover_dataset_count": len(spillover_datasets),
        "models": models,
        "datasets": datasets,
        "spillover_models": spillover_models,
        "spillover_datasets": spillover_datasets,
    }
    return Collection(
        payload,
        len(all_models) + len(all_datasets),
        (models_url, datasets_url),
    )


class _SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title_parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href and href not in self.links:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)


def collect_marin_site(client: HttpClient, window: Window) -> Collection:
    html, response = client.get_text(MARIN_SITE)
    if "<html" not in html[:2000].lower() or len(html.strip()) < 200:
        raise CollectionError(f"invalid HTML payload from {MARIN_SITE}")
    parser = _SiteParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise CollectionError(f"could not parse HTML from {MARIN_SITE}: {exc}") from exc
    title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip()
    if not title:
        raise CollectionError(f"missing HTML title from {MARIN_SITE}")
    payload = {
        "source": response.url,
        "target_date": window.day.isoformat(),
        "observed_at": iso_z(window.observed_at) if window.observed_at else None,
        "title": title,
        "sha256": hashlib.sha256(response.body).hexdigest(),
        "bytes": len(response.body),
        "links": parser.links,
        "html": html,
    }
    return Collection(payload, 1, (MARIN_SITE,))


SOURCE_SPECS: tuple[SourceSpec, ...] = (
    SourceSpec(
        name="github_issues",
        label="GitHub Issues 与评论",
        url=f"https://github.com/{GITHUB_REPOSITORY}/issues",
        evidence_file="github_issues.json",
        collector=collect_github_issues,
    ),
    SourceSpec(
        name="github_commits",
        label="GitHub commits",
        url=f"https://github.com/{GITHUB_REPOSITORY}/commits/main",
        evidence_file="github_commits.json",
        collector=collect_github_commits,
    ),
    SourceSpec(
        name="hugging_face",
        label="Hugging Face 模型与数据集",
        url=f"https://huggingface.co/{HUGGING_FACE_ORG}",
        evidence_file="hugging_face.json",
        collector=collect_hugging_face,
    ),
    SourceSpec(
        name="marin_site",
        label="Marin 官网",
        url=MARIN_SITE,
        evidence_file="marin_site.json",
        collector=collect_marin_site,
    ),
)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_markdown(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).replace("|", "\\|").strip()


def _source_manifest(run: SourceRun) -> dict[str, Any]:
    return {
        "name": run.spec.name,
        "label": run.spec.label,
        "status": run.status,
        "source_url": run.spec.url,
        "requested_urls": list(run.urls),
        "attempts": run.attempts,
        "record_count": run.record_count,
        "evidence_file": (
            run.spec.evidence_file
            if run.status == "success" or run.preserved_evidence
            else None
        ),
        "preserved_evidence": run.preserved_evidence,
        "preserved_from_collected_at": run.preserved_from_collected_at,
        "error": run.error,
    }


def _render_daily_note(
    *,
    window: Window,
    collected_at: str,
    overall_status: str,
    runs: Sequence[SourceRun],
) -> str:
    lines = [
        f"# Marin 每日追踪 · {window.day.isoformat()}",
        "",
        f"- UTC 窗口：`{iso_z(window.start)}` 至 `{iso_z(window.end)}`（结束时间不含）",
        f"- 可变来源防漏观察至：`{iso_z(window.observation_end)}`（可能与次日重叠）",
        f"- 实际采集时间：`{collected_at}`",
        f"- 总体状态：`{overall_status}`",
        "",
        "## 来源状态",
        "",
        "| 来源 | 状态 | 证据条目 | HTTP 尝试 |",
        "| --- | --- | ---: | ---: |",
    ]
    for run in runs:
        lines.append(
            f"| [{_safe_markdown(run.spec.label)}]({run.spec.url}) | "
            f"{run.status} | {run.record_count} | {run.attempts} |"
        )

    failed = [run for run in runs if run.status == "failed"]
    if failed:
        lines.extend(["", "## 采集失败", ""])
        for run in failed:
            preserved = "；已保留上次成功证据" if run.preserved_evidence else ""
            lines.append(
                f"- **{run.spec.label}**：{_safe_markdown(run.error)}{preserved}"
            )

    by_name = {run.spec.name: run for run in runs if run.collection is not None}

    issue_run = by_name.get("github_issues")
    if issue_run:
        issues = issue_run.collection.payload.get("issues", [])
        spillover_issues = issue_run.collection.payload.get("spillover_issues", [])
        comment_count = issue_run.collection.payload.get("comment_count", 0)
        spillover_comment_count = issue_run.collection.payload.get(
            "spillover_comment_count", 0
        )
        lines.extend(["", "## GitHub 工程记录", ""])
        lines.append(f"共 {len(issues)} 个更新 issue、{comment_count} 条评论证据。")
        if spillover_issues:
            lines.append(
                f"另有 {len(spillover_issues)} 个跨午夜补充观察、"
                f"{spillover_comment_count} 条评论上下文（不计入目标日数量）。"
            )
        issue_rows = [(issue, "") for issue in issues] + [
            (issue, " · 跨午夜补充") for issue in spillover_issues
        ]
        for issue, suffix in issue_rows[:20]:
            lines.append(
                f"- [#{issue.get('number')} {_safe_markdown(issue.get('title'))}]"
                f"({issue.get('url')}) · {issue.get('state')} · "
                f"{len(issue.get('comments') or [])} 条评论{suffix}"
            )
        if len(issue_rows) > 20:
            lines.append(f"- 其余 {len(issue_rows) - 20} 个 issue 见原始证据文件。")

    commit_run = by_name.get("github_commits")
    if commit_run:
        commits = commit_run.collection.payload.get("commits", [])
        lines.extend(["", "## 代码变化", ""])
        lines.append(f"共 {len(commits)} 个 commit。")
        for commit in commits[:20]:
            subject = str(commit.get("message") or "").splitlines()[0]
            short_sha = str(commit.get("sha") or "")[:7]
            lines.append(
                f"- [`{short_sha}`]({commit.get('url')}) {_safe_markdown(subject)}"
            )
        if len(commits) > 20:
            lines.append(f"- 其余 {len(commits) - 20} 个 commit 见原始证据文件。")

    hf_run = by_name.get("hugging_face")
    if hf_run:
        models = hf_run.collection.payload.get("models", [])
        datasets = hf_run.collection.payload.get("datasets", [])
        spillover_models = hf_run.collection.payload.get("spillover_models", [])
        spillover_datasets = hf_run.collection.payload.get("spillover_datasets", [])
        lines.extend(["", "## Hugging Face 产物", ""])
        lines.append(f"更新模型 {len(models)} 个，更新数据集 {len(datasets)} 个。")
        spillover_count = len(spillover_models) + len(spillover_datasets)
        if spillover_count:
            lines.append(f"另有 {spillover_count} 个跨午夜补充观察（不计入目标日数量）。")
        artifact_rows = [(item, "") for item in models + datasets] + [
            (item, " · 跨午夜补充")
            for item in spillover_models + spillover_datasets
        ]
        for item, suffix in artifact_rows[:20]:
            lines.append(
                f"- [{_safe_markdown(item.get('id'))}]({item.get('url')}) · "
                f"{item.get('kind')} · `{item.get('last_modified')}`{suffix}"
            )
        if len(artifact_rows) > 20:
            lines.append(f"- 其余 {len(artifact_rows) - 20} 个产物见原始证据文件。")

    site_run = by_name.get("marin_site")
    if site_run:
        site = site_run.collection.payload
        lines.extend(["", "## 官网快照", ""])
        lines.append(
            f"- [{_safe_markdown(site.get('title'))}]({site.get('source')}) · "
            f"SHA-256 `{site.get('sha256')}` · {site.get('bytes')} bytes"
        )

    lines.extend(
        [
            "",
            "---",
            "本页由确定性脚本生成；完整正文、评论、元数据和错误见同日 `data/snapshots`。",
            "",
        ]
    )
    return "\n".join(lines)


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _publish_outputs(
    *,
    snapshot_staging: Path,
    snapshot_target: Path,
    note_content: str,
    note_target: Path,
) -> None:
    """Publish the snapshot and note together, rolling both back on an error."""
    snapshot_target.parent.mkdir(parents=True, exist_ok=True)
    note_target.parent.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex
    snapshot_backup = snapshot_target.with_name(
        f".{snapshot_target.name}.backup-{identifier}"
    )
    note_backup = note_target.with_name(f".{note_target.name}.backup-{identifier}")
    fd, note_staging_name = tempfile.mkstemp(
        prefix=f".{note_target.name}.", dir=note_target.parent
    )
    note_staging = Path(note_staging_name)
    snapshot_installed = False
    note_installed = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(note_content)
            handle.flush()
            os.fsync(handle.fileno())
        if snapshot_target.exists():
            os.replace(snapshot_target, snapshot_backup)
        if note_target.exists():
            os.replace(note_target, note_backup)
        os.replace(snapshot_staging, snapshot_target)
        snapshot_installed = True
        os.replace(note_staging, note_target)
        note_installed = True
    except BaseException:
        if snapshot_installed and snapshot_target.exists():
            _remove_path(snapshot_target)
        if note_installed and note_target.exists():
            _remove_path(note_target)
        if snapshot_backup.exists():
            os.replace(snapshot_backup, snapshot_target)
        if note_backup.exists():
            os.replace(note_backup, note_target)
        raise
    finally:
        if note_staging.exists():
            note_staging.unlink()
    if snapshot_backup.exists():
        _remove_path(snapshot_backup)
    if note_backup.exists():
        _remove_path(note_backup)


def _load_previous_manifest(snapshot: Path) -> dict[str, Any] | None:
    manifest_path = snapshot / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        return None
    return payload


def _preserve_previous_evidence(
    *,
    previous_snapshot: Path,
    previous_manifest: Mapping[str, Any] | None,
    spec: SourceSpec,
    destination: Path,
) -> PreviousEvidence | None:
    """Copy a previously published, manifest-backed evidence file into staging."""
    if not previous_manifest:
        return None
    source_entry = next(
        (
            item
            for item in previous_manifest.get("sources", [])
            if isinstance(item, dict) and item.get("name") == spec.name
        ),
        None,
    )
    if not source_entry or source_entry.get("evidence_file") != spec.evidence_file:
        return None
    previous_file = previous_snapshot / spec.evidence_file
    if not previous_file.is_file():
        return None
    try:
        # Do not carry forward an incomplete or corrupt JSON artifact.
        payload = json.loads(previous_file.read_text(encoding="utf-8"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(previous_file, destination)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    collected_at = (
        source_entry.get("preserved_from_collected_at")
        if source_entry.get("preserved_evidence")
        else previous_manifest.get("collected_at")
    )
    if not isinstance(collected_at, str):
        collected_at = "unknown"
    record_count = source_entry.get("record_count")
    if not isinstance(record_count, int) or record_count < 0:
        record_count = 0
    requested_urls = source_entry.get("requested_urls")
    urls = (
        tuple(item for item in requested_urls if isinstance(item, str))
        if isinstance(requested_urls, list)
        else ()
    )
    return PreviousEvidence(
        payload=payload,
        record_count=record_count,
        urls=urls,
        collected_at=collected_at,
    )


def run_tracking(
    *,
    window: Window,
    repo_root: Path,
    allow_total_failure: bool = False,
    refresh_existing: bool = False,
    source_specs: Sequence[SourceSpec] = SOURCE_SPECS,
    now: Callable[[], datetime] = utc_now,
    client_factory: Callable[[], HttpClient] | None = None,
) -> int:
    if not source_specs:
        raise ValueError("at least one source is required")
    repo_root = repo_root.resolve()
    observed_at = now()
    if observed_at.tzinfo is None:
        raise ValueError("now() must return a timezone-aware datetime")
    observed_at = observed_at.astimezone(UTC)
    if window.day >= observed_at.date():
        raise ValueError("target date must be a completed UTC day")
    window = replace(window, observed_at=observed_at)
    snapshots_parent = repo_root / "data" / "snapshots"
    snapshots_parent.mkdir(parents=True, exist_ok=True)
    final_snapshot = snapshots_parent / window.day.isoformat()
    final_note = repo_root / "notes" / "daily" / f"{window.day.isoformat()}.md"
    collected_at = iso_z(observed_at)
    previous_manifest = _load_previous_manifest(final_snapshot)

    if client_factory is None:
        github_token = (
            os.environ.get("MARIN_GITHUB_TOKEN")
            or os.environ.get("GITHUB_TOKEN")
            or os.environ.get("GH_TOKEN")
        )

        def client_factory() -> HttpClient:
            return HttpClient(github_token=github_token)

    runs: list[SourceRun] = []
    with tempfile.TemporaryDirectory(
        prefix=f".{window.day.isoformat()}-", dir=snapshots_parent
    ) as staging_name:
        staging = Path(staging_name)
        for spec in source_specs:
            client = client_factory()
            evidence_path = staging / spec.evidence_file
            if not refresh_existing:
                previous = _preserve_previous_evidence(
                    previous_snapshot=final_snapshot,
                    previous_manifest=previous_manifest,
                    spec=spec,
                    destination=evidence_path,
                )
                if previous is not None:
                    runs.append(
                        SourceRun(
                            spec=spec,
                            status="preserved",
                            attempts=0,
                            record_count=previous.record_count,
                            urls=previous.urls,
                            collection=Collection(
                                payload=previous.payload,
                                record_count=previous.record_count,
                                urls=previous.urls,
                            ),
                            preserved_evidence=True,
                            preserved_from_collected_at=previous.collected_at,
                        )
                    )
                    continue
            try:
                collection = spec.collector(client, window)
                if collection.record_count < 0:
                    raise CollectionError("record_count cannot be negative")
                _write_json(evidence_path, collection.payload)
            except Exception as exc:
                previous = _preserve_previous_evidence(
                    previous_snapshot=final_snapshot,
                    previous_manifest=previous_manifest,
                    spec=spec,
                    destination=evidence_path,
                )
                runs.append(
                    SourceRun(
                        spec=spec,
                        status="failed",
                        attempts=client.attempts,
                        error=f"{type(exc).__name__}: {exc}",
                        record_count=previous.record_count if previous else 0,
                        urls=previous.urls if previous else (),
                        collection=(
                            Collection(
                                payload=previous.payload,
                                record_count=previous.record_count,
                                urls=previous.urls,
                            )
                            if previous
                            else None
                        ),
                        preserved_evidence=previous is not None,
                        preserved_from_collected_at=(
                            previous.collected_at if previous else None
                        ),
                    )
                )
            else:
                runs.append(
                    SourceRun(
                        spec=spec,
                        status="success",
                        attempts=client.attempts,
                        record_count=collection.record_count,
                        urls=collection.urls,
                        collection=collection,
                    )
                )

        successes = sum(run.status == "success" for run in runs)
        preserved = sum(run.status == "preserved" for run in runs)
        failures = sum(run.status == "failed" for run in runs)
        if successes == 0 and failures == 0 and preserved == len(runs):
            print(f"snapshot for {window.day} is already complete; nothing to refresh")
            return 0
        if successes == 0 and not allow_total_failure:
            errors = "; ".join(f"{run.spec.name}: {run.error}" for run in runs)
            print(
                f"no new Marin source succeeded; refusing to publish {window.day}: {errors}",
                file=sys.stderr,
            )
            return 2

        if successes == 0:
            overall_status = "total_failure_allowed"
        elif failures:
            overall_status = "partial"
        else:
            overall_status = "success"

        manifest = {
            "schema_version": 1,
            "date": window.day.isoformat(),
            "window": {"start": iso_z(window.start), "end": iso_z(window.end)},
            "mutable_observation_end": iso_z(window.observation_end),
            "collected_at": collected_at,
            "overall_status": overall_status,
            "successful_sources": successes,
            "failed_sources": failures,
            "preserved_sources": sum(run.preserved_evidence for run in runs),
            "available_sources": sum(
                run.status == "success" or run.preserved_evidence for run in runs
            ),
            "sources": [_source_manifest(run) for run in runs],
        }
        _write_json(staging / "manifest.json", manifest)
        note = _render_daily_note(
            window=window,
            collected_at=collected_at,
            overall_status=overall_status,
            runs=runs,
        )
        _publish_outputs(
            snapshot_staging=staging,
            snapshot_target=final_snapshot,
            note_content=note,
            note_target=final_note,
        )

    print(
        f"published Marin snapshot for {window.day}: "
        f"{successes} source(s) succeeded, {failures} failed"
    )
    return 0


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        type=_parse_day,
        help="UTC day to collect (default: previous UTC day)",
    )
    parser.add_argument(
        "--allow-total-failure",
        action="store_true",
        help="publish a diagnostic manifest even when every source fails",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help="explicitly recollect and replace evidence already saved for this date",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=PROJECT_ROOT,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=DEFAULT_MAX_ATTEMPTS,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.max_attempts <= 0:
        parser.error("--max-attempts must be positive")
    current = utc_now()
    selected_day = args.date or (current.date() - timedelta(days=1))
    if selected_day >= current.date():
        parser.error("--date must be before the current UTC date")
    token = (
        os.environ.get("MARIN_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
    )
    return run_tracking(
        window=make_window(selected_day),
        repo_root=args.repo_root,
        allow_total_failure=args.allow_total_failure,
        refresh_existing=args.refresh_existing,
        now=lambda: current,
        client_factory=lambda: HttpClient(
            github_token=token,
            timeout=args.timeout,
            max_attempts=args.max_attempts,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
