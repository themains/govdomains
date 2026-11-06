"""Import source lists without interpreting their labels as a global taxonomy."""

import csv
import hashlib
import io
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .core import Evidence, validate_date
from .normalize import has_page_path, normalize_hostname
from .snapshot import Snapshot

SOURCES = {
    "cisa": (
        "https://raw.githubusercontent.com/cisagov/dotgov-data/main/current-full.csv"
    ),
    "gsa": (
        "https://raw.githubusercontent.com/GSA/govt-urls/main/1_govt_urls_full.csv"
    ),
}
FORMATS = {
    "cisa": (
        "Domain name",
        ",",
        ["Domain type", "Agency", "Organization name", "City", "State"],
    ),
    "gsa": (
        "Domain name",
        ",",
        ["Agency", "Type of government", "Federal branch", "State"],
    ),
    "india": ("url", ",", ["name", "sector"]),
    "govdirectory": (
        "Website",
        "\t",
        ["Name", "Type", "source_file", "Govdirectory URL", "source_updated_on"],
    ),
    "generic": ("hostname", ",", []),
}


def http_session() -> requests.Session:
    """Create a session with bounded retries for transient source failures."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        allowed_methods={"GET"},
        status_forcelist=[429, 500, 502, 503, 504],
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.headers["User-Agent"] = (
        f"govdomains/{version('govdomains')} (+https://github.com/themains/govdomains)"
    )
    return session


def parse_list(
    content: str,
    *,
    source: str,
    source_format: str = "generic",
    observed_on: str | None = None,
    column: str | None = None,
    delimiter: str | None = None,
    label: str = "government",
) -> Snapshot:
    """Parse a saved list. Non-root URL listings remain page-scoped evidence.

    Source membership is an inference signal, not verification of ownership.
    Missing or invalid values are counted; missing schema raises an error.
    """
    validate_date(observed_on)
    if source_format not in FORMATS:
        raise ValueError(f"Unknown list format: {source_format}")
    default_column, default_delimiter, attributes = FORMATS[source_format]
    column = column or default_column
    reader = csv.DictReader(
        io.StringIO(content.lstrip("\ufeff")), delimiter=delimiter or default_delimiter
    )
    if reader.fieldnames is None or column not in reader.fieldnames:
        raise ValueError(f"Source must contain column {column!r}")
    evidence = []
    counts = {"rows": 0, "empty": 0, "invalid": 0, "page_scoped": 0}
    for row in reader:
        counts["rows"] += 1
        if None in row:
            raise ValueError(f"Malformed CSV row {reader.line_num}")
        value = row.get(column)
        if value is None or not value.strip():
            counts["empty"] += 1
            continue
        try:
            host = normalize_hostname(value)
        except ValueError:
            counts["invalid"] += 1
            continue
        scope = "page" if has_page_path(value) else "exact"
        counts["page_scoped"] += scope == "page"
        evidence.append(
            Evidence(
                host,
                source,
                label=label,
                observed_on=observed_on,
                scope=scope,
                attributes={
                    **{key: row[key] for key in attributes if row.get(key)},
                    "source_value": value.strip(),
                },
            )
        )
    if counts["rows"] and not evidence:
        raise ValueError("Source contained rows but no usable hostnames")
    return Snapshot(
        tuple(evidence),
        {
            "source": source,
            "format": source_format,
            "observed_on": observed_on,
            "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "counts": counts,
            "label_basis": "source_membership",
            "population_completeness": "unknown",
        },
    )


def import_list(path: str | Path, **kwargs) -> Snapshot:
    """Import a local CSV/TSV; caller must supply its source identifier."""
    return parse_list(Path(path).read_text(encoding="utf-8"), **kwargs)


def fetch_list(name: str, *, session: requests.Session | None = None) -> Snapshot:
    """Explicitly fetch a current CISA or GSA list. Date is retrieval observation."""
    if name not in SOURCES:
        raise ValueError(f"Supported live sources: {', '.join(SOURCES)}")
    own_session = session is None
    session = session or http_session()
    try:
        with session.get(SOURCES[name], timeout=(10, 90)) as response:
            response.raise_for_status()
            response.encoding = "utf-8"
            result = parse_list(
                response.text,
                source=SOURCES[name],
                source_format=name,
                observed_on=datetime.now(UTC).date().isoformat(),
            )
            result.metadata["date_basis"] = "retrieval_observation"
            result.metadata["etag"] = response.headers.get("ETag")
            return result
    finally:
        if own_session:
            session.close()
