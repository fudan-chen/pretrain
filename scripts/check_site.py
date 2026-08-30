#!/usr/bin/env python3
"""Validate generated local links, anchors and required accessible chart text."""

import argparse
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.svg_titles = 0
        self.svg_descs = 0
        self._svg_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag in {"a", "link"} and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in {"script", "img"} and attrs.get("src"):
            self.links.append(attrs["src"])
        if tag == "svg":
            self._svg_depth += 1
        elif tag == "title" and self._svg_depth:
            self.svg_titles += 1
        elif tag == "desc" and self._svg_depth:
            self.svg_descs += 1

    def handle_endtag(self, tag):
        if tag == "svg" and self._svg_depth:
            self._svg_depth -= 1


def parse_page(path):
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def target_path(page, href):
    parts = urlsplit(href)
    if parts.scheme or parts.netloc or href.startswith("mailto:"):
        return None, None
    raw_path = unquote(parts.path)
    target = page if not raw_path else (page.parent / raw_path).resolve()
    if target.is_dir() or raw_path.endswith("/"):
        target = target / "index.html"
    return target, parts.fragment


def check(root):
    root = root.resolve()
    site = root / "site"
    errors = []
    pages = sorted(site.rglob("*.html"))
    parsed = {page.resolve(): parse_page(page) for page in pages}
    for page in pages:
        parser = parsed[page.resolve()]
        text = page.read_text(encoding="utf-8")
        if "{{" in text or "}}" in text:
            errors.append(f"{page.relative_to(root)}: unresolved template token")
        chart_count = text.count('<svg class="chart"')
        if chart_count and (parser.svg_titles < chart_count or parser.svg_descs < chart_count):
            errors.append(
                f"{page.relative_to(root)}: {chart_count} charts but "
                f"{parser.svg_titles} titles/{parser.svg_descs} descriptions"
            )
        for href in parser.links:
            target, fragment = target_path(page.resolve(), href)
            if target is None:
                continue
            try:
                target.resolve().relative_to(site.resolve())
            except ValueError:
                errors.append(
                    f"{page.relative_to(root)} -> internal link escapes site root: {href}"
                )
                continue
            if not target.exists():
                errors.append(f"{page.relative_to(root)} -> missing {href}")
                continue
            if fragment and target.suffix.lower() == ".html":
                target_parser = parsed.get(target.resolve()) or parse_page(target)
                if fragment not in target_parser.ids:
                    errors.append(
                        f"{page.relative_to(root)} -> missing anchor {href}"
                    )
    return pages, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args(argv)
    pages, errors = check(args.root)
    if errors:
        print("site validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"site validation passed: {len(pages)} HTML pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
