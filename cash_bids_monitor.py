#!/usr/bin/env python3
"""Terminal program to monitor corn and soybean cash bids.

Targets:
- Cargill - Blair
- Central Valley Ag - East Hub

The script pulls each site on a timer and attempts to extract bid prices for
Corn and Soybeans near the requested location name.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable

USER_AGENT = "Mozilla/5.0 (BidPuller/1.0; +https://example.local)"
PRICE_PATTERN = re.compile(r"\$?\d{1,2}\.\d{2,4}")
TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class SourceConfig:
    name: str
    location_aliases: tuple[str, ...]
    url: str


@dataclass
class BidSnapshot:
    source: str
    url: str
    corn: str | None
    soybeans: str | None
    fetched_at: dt.datetime
    error: str | None = None


SHARED_BIDS_URL = "https://www.cvacoop.com/cash-bids"

DEFAULT_SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig(
        name="Cargill - Blair",
        location_aliases=("cargill blair", "blair", "blair, ne", "blair nebraska"),
        url=SHARED_BIDS_URL,
    ),
    SourceConfig(
        name="Central Valley Ag - East Hub",
        location_aliases=("central valley ag east hub", "east hub", "easthub", "east-hub"),
        url=SHARED_BIDS_URL,
    ),
)


def fetch_text(url: str, timeout: int) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        encoding = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(encoding, errors="replace")


def html_to_text(html: str) -> str:
    without_tags = TAG_PATTERN.sub(" ", html)
    return WHITESPACE_PATTERN.sub(" ", without_tags).lower()


def location_window(text: str, aliases: Iterable[str], radius: int = 3000) -> str:
    for alias in aliases:
        index = text.find(alias.lower())
        if index >= 0:
            start = max(0, index - radius)
            end = min(len(text), index + radius)
            return text[start:end]
    return text


def extract_price(segment: str, commodity_labels: Iterable[str]) -> str | None:
    for label in commodity_labels:
        pattern = re.compile(rf"{re.escape(label)}(.{{0,80}})")
        for match in pattern.finditer(segment):
            near_text = match.group(1)
            price_match = PRICE_PATTERN.search(near_text)
            if price_match:
                return price_match.group(0).lstrip("$")
    return None


def extract_bid_prices(html: str, aliases: Iterable[str]) -> tuple[str | None, str | None]:
    text = html_to_text(html)
    segment = location_window(text, aliases)

    corn = extract_price(segment, ("corn", "yellow corn"))
    soybeans = extract_price(segment, ("soybeans", "soybean"))

    # Fallback: some sites serialize structured data in script tags.
    if not (corn and soybeans):
        corn_json, soy_json = extract_from_json_blocks(html, aliases)
        corn = corn or corn_json
        soybeans = soybeans or soy_json

    return corn, soybeans


def extract_from_json_blocks(html: str, aliases: Iterable[str]) -> tuple[str | None, str | None]:
    script_bodies = re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.DOTALL | re.IGNORECASE)
    alias_set = {a.lower() for a in aliases}

    for raw_script in script_bodies:
        candidate = raw_script.strip()
        if "{" not in candidate and "[" not in candidate:
            continue
        for snippet in iter_json_snippets(candidate):
            try:
                payload = json.loads(snippet)
            except Exception:
                continue
            corn, soy = hunt_json_payload(payload, alias_set)
            if corn or soy:
                return corn, soy
    return None, None


def iter_json_snippets(text: str) -> Iterable[str]:
    for pattern in (r"\{.*?\}", r"\[.*?\]"):
        for match in re.finditer(pattern, text, flags=re.DOTALL):
            snippet = match.group(0)
            if len(snippet) < 4:
                continue
            yield snippet


def hunt_json_payload(payload: object, aliases: set[str]) -> tuple[str | None, str | None]:
    stack = [payload]
    corn = None
    soy = None

    while stack and not (corn and soy):
        node = stack.pop()
        if isinstance(node, dict):
            joined = " ".join(str(v).lower() for v in node.values() if isinstance(v, (str, int, float)))
            if aliases and not any(alias in joined for alias in aliases):
                stack.extend(node.values())
                continue

            text = joined
            if not corn and "corn" in text:
                corn = first_price(text)
            if not soy and ("soybean" in text or "soybeans" in text):
                soy = first_price(text)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)

    return corn, soy


def first_price(text: str) -> str | None:
    match = PRICE_PATTERN.search(text)
    return match.group(0).lstrip("$") if match else None


def collect_snapshot(source: SourceConfig, timeout: int) -> BidSnapshot:
    now = dt.datetime.now(dt.timezone.utc)
    try:
        html = fetch_text(source.url, timeout=timeout)
        corn, soybeans = extract_bid_prices(html, source.location_aliases)
        if not corn and not soybeans:
            return BidSnapshot(
                source=source.name,
                url=source.url,
                corn=None,
                soybeans=None,
                fetched_at=now,
                error="Fetched page, but could not find Corn/Soybeans prices for location.",
            )
        return BidSnapshot(source=source.name, url=source.url, corn=corn, soybeans=soybeans, fetched_at=now)
    except urllib.error.URLError as exc:
        return BidSnapshot(
            source=source.name,
            url=source.url,
            corn=None,
            soybeans=None,
            fetched_at=now,
            error=f"Network error: {exc}",
        )
    except Exception as exc:  # keeps the monitor running
        return BidSnapshot(
            source=source.name,
            url=source.url,
            corn=None,
            soybeans=None,
            fetched_at=now,
            error=f"Unexpected error: {exc}",
        )


def render_table(snapshots: list[BidSnapshot]) -> str:
    headers = ("Source", "Corn", "Soybeans", "Fetched (UTC)", "Status")
    rows = []
    for snap in snapshots:
        status = snap.error or "OK"
        rows.append(
            (
                snap.source,
                snap.corn or "--",
                snap.soybeans or "--",
                snap.fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
                status,
            )
        )

    widths = [len(h) for h in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def format_row(values: tuple[str, ...]) -> str:
        return " | ".join(val.ljust(widths[i]) for i, val in enumerate(values))

    line = "-+-".join("-" * w for w in widths)
    output = [format_row(headers), line]
    output.extend(format_row(r) for r in rows)
    return "\n".join(output)


def clear_screen() -> None:
    print("\033[2J\033[H", end="")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Display and auto-refresh corn/soybean cash bids for Cargill Blair and CVA East Hub."
    )
    parser.add_argument("--interval", type=int, default=300, help="Refresh interval in seconds (default: 300).")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds (default: 20).")
    parser.add_argument("--once", action="store_true", help="Fetch once and exit.")
    parser.add_argument("--no-clear", action="store_true", help="Do not clear the terminal on each refresh.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    while True:
        snapshots = [collect_snapshot(source, args.timeout) for source in DEFAULT_SOURCES]

        if not args.no_clear:
            clear_screen()
        print("Cash bid monitor (Corn/Soybeans)")
        print(render_table(snapshots))
        print(f"\nNext update in {args.interval}s. Press Ctrl+C to quit.")

        if args.once:
            return 0

        try:
            time.sleep(max(1, args.interval))
        except KeyboardInterrupt:
            print("\nStopped by user.")
            return 0


if __name__ == "__main__":
    sys.exit(main())
