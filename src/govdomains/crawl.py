"""Collect unique hosts from the Common Crawl CDX API, one index page at a time."""

import csv
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

from .core import Evidence, load_rules
from .normalize import normalize_hostname
from .snapshot import Snapshot
from .sources import http_session


def _observe(hosts: dict, record: dict, suffix: str | None = None) -> None:
    host = normalize_hostname(record["url"])
    if suffix and host != suffix and not host.endswith("." + suffix):
        raise ValueError("Common Crawl returned a host outside the query")
    stamp = record["timestamp"]
    if not isinstance(stamp, str) or not re.fullmatch(r"\d{14}", stamp):
        raise ValueError("Invalid Common Crawl capture timestamp")
    datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    first, last = hosts.get(host, (stamp, stamp))
    hosts[host] = (min(first, stamp), max(last, stamp))


def _evidence(hosts: dict, source: str, **attributes) -> tuple[Evidence, ...]:
    return tuple(
        Evidence(
            host,
            source,
            method="crawl",
            label="unknown",
            observed_on=datetime.strptime(first, "%Y%m%d%H%M%S")
            .replace(tzinfo=UTC)
            .date()
            .isoformat(),
            attributes={"first_capture": first, "last_capture": last, **attributes},
        )
        for host, (first, last) in hosts.items()
    )


def import_crawl_csv(path: str | Path, *, source: str) -> Snapshot:
    """Stream a notebook-exported CDX CSV into unique-host observations."""
    hosts: dict[str, tuple[str, str]] = {}
    count = 0
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"url", "timestamp"} <= set(reader.fieldnames):
            raise ValueError("Crawl CSV must contain url and timestamp columns")
        for record in reader:
            if None in record:
                raise ValueError(f"Malformed CSV row {reader.line_num}")
            _observe(hosts, record)
            count += 1
    with Path(path).open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    return Snapshot(
        _evidence(hosts, source),
        {
            "source": source,
            "format": "commoncrawl_csv",
            "capture_count": count,
            "content_sha256": checksum,
            "population_completeness": "unknown",
        },
    )


def patterns_for(country: str) -> tuple[str, ...]:
    """Return notebook-derived discovery suffixes for an exact country label."""
    suffixes = tuple(
        sorted(
            {
                r.suffix
                for r in load_rules()
                if r.country and r.country.casefold() == country.casefold()
            }
        )
    )
    if not suffixes:
        raise ValueError(f"No patterns for country label {country!r}")
    return suffixes


class CommonCrawl:
    """Serial, retrying collection. All-page traversal is explicit, not default.

    A checkpoint stores host summaries after each completed page. Retrying the
    same query resumes there; errors never become a successful empty result.
    """

    def __init__(
        self, index: str, *, session: requests.Session | None = None, delay: float = 1.0
    ):
        """Configure a crawl index and an optional caller-owned HTTP session."""
        if not re.fullmatch(r"CC-MAIN-\d{4}-\d{2}", index):
            raise ValueError("Index must look like CC-MAIN-2024-30")
        if delay < 0:
            raise ValueError("Delay must be nonnegative")
        self.index = index
        self.endpoint = f"https://index.commoncrawl.org/{index}-index"
        self.session = session or http_session()
        self._owns_session = session is None
        self.delay = delay

    def close(self):
        """Close the HTTP session only when this client created it."""
        if self._owns_session:
            self.session.close()

    def __enter__(self):
        """Return this client for use as a context manager."""
        return self

    def __exit__(self, *args):
        """Release an owned HTTP session when leaving the context."""
        self.close()

    def collect(
        self,
        suffix: str,
        *,
        max_pages: int | None = 1,
        checkpoint: str | Path | None = None,
    ) -> Snapshot:
        """Return host observations, not URL rows or government ownership claims.

        ``max_pages`` is a total page budget including checkpointed pages.
        ``None`` traverses every page reported for this query. Checkpoints are
        tied to the index and suffix and can be resumed with a larger budget.
        """
        suffix = normalize_hostname(suffix.removeprefix("*."))
        if max_pages is not None and (type(max_pages) is not int or max_pages < 1):
            raise ValueError("max_pages must be a positive integer or None")
        query = {"index": self.index, "suffix": suffix, "page_size": 1}
        hosts: dict[str, tuple[str, str]] = {}
        next_page = 0
        capture_count = 0
        if checkpoint and Path(checkpoint).exists():
            saved = Snapshot.load(checkpoint)
            if saved.metadata.get("query") != query:
                raise ValueError("Checkpoint belongs to a different query")
            next_page = saved.metadata["next_page"]
            capture_count = saved.metadata["capture_count"]
            hosts = {
                e.hostname: (
                    e.attributes["first_capture"],
                    e.attributes["last_capture"],
                )
                for e in saved.evidence
            }
        params = {"url": suffix, "matchType": "domain", "output": "json", "pageSize": 1}
        with self.session.get(
            self.endpoint, params={**params, "showNumPages": "true"}, timeout=(10, 120)
        ) as response:
            response.raise_for_status()
            page_info = response.json()
        pages = page_info.get("pages")
        if type(pages) is not int or pages < 0:
            raise ValueError("Common Crawl returned an invalid page count")
        if next_page > pages:
            raise ValueError("Index page count changed; use a new checkpoint")
        stop = pages if max_pages is None else min(pages, max_pages)
        if next_page > stop:
            raise ValueError("Page budget is smaller than the completed checkpoint")

        def snapshot():
            evidence = _evidence(hosts, self.endpoint, discovery_suffix=suffix)
            return Snapshot(
                evidence,
                {
                    "source": self.endpoint,
                    "query": query,
                    "next_page": next_page,
                    "total_pages": pages,
                    "capture_count": capture_count,
                    "query_complete": next_page == pages,
                    "population_completeness": "unknown",
                },
            )

        for page in range(next_page, stop):
            time.sleep(self.delay)
            with self.session.get(
                self.endpoint,
                params={**params, "page": page, "fl": "url,timestamp"},
                stream=True,
                timeout=(10, 120),
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    record = json.loads(line)
                    _observe(hosts, record, suffix)
                    capture_count += 1
            next_page = page + 1
            if checkpoint:
                snapshot().save(checkpoint)
        return snapshot()
