"""Archive source lists, import research extracts, and build offline tables."""

import argparse
import gzip
import hashlib
import json
import logging
import shutil
import subprocess
import sys
import time
import zlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from govdomains.bundled import decode_bundle, encode_bundle
from govdomains.directory import country_pages, parse_country
from govdomains.snapshot import Snapshot, atomic_write
from govdomains.sources import http_session, parse_list

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
CATALOG = RAW / "catalog.json"
LICENSE_URL = "https://www.govdirectory.org/about/"


def checksum(content):
    """Hash a raw response body or encoded table."""
    return hashlib.sha256(content).hexdigest()


def archive(path, record):
    """Atomically save a response record in a reproducible gzip archive."""
    content = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(gzip.compress(content, mtime=0))
    temporary.replace(path)


def read_archive(path):
    """Read an archived response and verify successful retrieval and its checksum."""
    record = json.loads(gzip.decompress(path.read_bytes()))
    if (
        record.get("ok") is not True
        or checksum(record["body"].encode()) != record["sha256"]
    ):
        raise ValueError(f"Unsuccessful or corrupt source archive: {path}")
    return record


def fetch_archive(session, url, path):
    """Resume a verified response archive or explicitly retrieve its source."""
    if path.exists():
        try:
            record = read_archive(path)
            if record["url"] != url:
                raise ValueError("Archive URL differs from requested source")
            return record
        except (ValueError, OSError, EOFError, zlib.error):
            pass
    with session.get(url, timeout=(15, 90)) as response:
        body = response.content.decode("utf-8")
        record = {
            "url": url,
            "fetched_at": datetime.now(UTC).isoformat(),
            "status": response.status_code,
            "ok": response.status_code == 200,
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "body": body,
            "sha256": checksum(body.encode()),
        }
        archive(path, record)
        response.raise_for_status()
    if not record["ok"]:
        raise ValueError(f"Unexpected source response: {response.status_code}")
    logging.getLogger(__name__).info("Archived %s", url)
    return record


def catalog():
    """Read the current raw-source catalog, or return an empty catalog."""
    return json.loads(CATALOG.read_text()) if CATALOG.exists() else {}


def save_catalog(entries):
    """Atomically replace the raw-source catalog."""
    atomic_write(CATALOG, json.dumps(entries, indent=2, sort_keys=True) + "\n")


def descriptor(path, record, **extra):
    """Describe an archived source using a repository-relative path."""
    return {
        "raw_path": str(path.relative_to(ROOT)),
        "url": record["url"],
        "sha256": record["sha256"],
        "fetched_at": record["fetched_at"],
        **extra,
    }


def fetch(collection):
    """Archive all pages before changing which snapshots the package builds."""
    destination = RAW / collection
    entries = catalog()
    with http_session() as session:
        commit_path = destination / "cisa/revision.jsonl.gz"
        revision_record = fetch_archive(
            session,
            "https://api.github.com/repos/cisagov/dotgov-data/commits/main",
            commit_path,
        )
        revision = json.loads(revision_record["body"])["sha"]
        prefix = f"https://raw.githubusercontent.com/cisagov/dotgov-data/{revision}/"
        path = destination / "cisa/current-full.jsonl.gz"
        record = fetch_archive(session, prefix + "current-full.csv", path)
        license_path = destination / "cisa/license.jsonl.gz"
        license_record = fetch_archive(session, prefix + "LICENSE", license_path)
        entries["cisa"] = {
            "default": True,
            "format": "cisa",
            "license": "CC0-1.0",
            "license_url": prefix + "LICENSE",
            "upstream_revision": revision,
            "observed_on": record["fetched_at"][:10],
            "date_basis": "retrieval_observation",
            "inputs": [descriptor(path, record)],
            "license_input": descriptor(license_path, license_record),
        }
        index_path = destination / "govdirectory/countries.jsonl.gz"
        index = fetch_archive(
            session, "https://www.govdirectory.org/countries/", index_path
        )
        pages = country_pages(index["body"])
        inputs = []
        for page in pages:
            slug = urlsplit(page["url"]).path.strip("/")
            path = destination / "govdirectory" / (slug + ".jsonl.gz")
            record = fetch_archive(session, page["url"], path)
            inputs.append(descriptor(path, record, jurisdiction_label=page["label"]))
            time.sleep(0.25)
        terms_path = destination / "govdirectory/terms.jsonl.gz"
        terms = fetch_archive(session, LICENSE_URL, terms_path)
        entries["govdirectory"] = {
            "default": True,
            "format": "govdirectory_html",
            "license": "CC0-1.0",
            "license_url": LICENSE_URL,
            "observed_on": max(item["fetched_at"] for item in inputs)[:10],
            "date_basis": "collection_completed; individual retrieval times in inputs",
            "inputs": inputs,
            "index_input": descriptor(index_path, index),
            "license_input": descriptor(terms_path, terms),
            "jurisdiction_pages": len(pages),
        }
    save_catalog(entries)


def import_research(repository):
    """Archive the original research extracts at an immutable Git revision."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is required to import research extracts")
    revision = (
        subprocess.check_output(  # noqa: S603 - fixed Git command, no shell
            [git, "-C", str(repository), "rev-parse", "HEAD"]
        )
        .decode()
        .strip()
    )
    entries = catalog()
    for name, filename, fmt, license_url in [
        (
            "cisa_research",
            "us_gov_domain_list.csv",
            "cisa",
            "https://github.com/cisagov/dotgov-data/blob/main/LICENSE",
        ),
        ("govdirectory_research", "combined_tsv_data.tsv", "govdirectory", LICENSE_URL),
    ]:
        body = subprocess.check_output(  # noqa: S603 - fixed Git command, no shell
            [git, "-C", str(repository), "show", f"{revision}:data/{filename}"]
        ).decode("utf-8")
        record = {
            "url": (
                "https://raw.githubusercontent.com/themains/gov_privacy/"
                f"{revision}/data/{filename}"
            ),
            "fetched_at": None,
            "ok": True,
            "body": body,
            "sha256": checksum(body.encode()),
        }
        path = RAW / "research" / (name + ".jsonl.gz")
        if path.exists() and read_archive(path)["sha256"] != record["sha256"]:
            raise ValueError("Refusing to replace a different research extract")
        archive(path, record)
        entries[name] = {
            "default": False,
            "format": fmt,
            "license": "CC0-1.0",
            "license_url": license_url,
            "observed_on": None,
            "date_basis": (
                "unknown original collection date; Git date is not an observation date"
            ),
            "upstream_revision": revision,
            "inputs": [descriptor(path, record)],
        }
    save_catalog(entries)


def build():
    """Build and validate packaged Parquet tables entirely from archived responses."""
    entries = catalog()
    if not entries:
        raise ValueError("No archived sources; run fetch or import-research first")
    output = ROOT / "src/govdomains/data/bundled"
    output.mkdir(parents=True, exist_ok=True)
    sources = {}
    tables = {}
    for name, entry in sorted(entries.items()):
        snapshots = []
        audits = []
        for item in entry["inputs"]:
            raw = read_archive(ROOT / item["raw_path"])
            if raw["sha256"] != item["sha256"] or raw["url"] != item["url"]:
                raise ValueError("Source archive differs from catalog")
            if entry["format"] == "govdirectory_html":
                snapshot = parse_country(
                    raw["body"],
                    url=item["url"],
                    jurisdiction_label=item["jurisdiction_label"],
                    observed_on=entry["observed_on"],
                )
            else:
                snapshot = parse_list(
                    raw["body"],
                    source=item["url"],
                    source_format=entry["format"],
                    observed_on=entry["observed_on"],
                )
            audits.append(
                {
                    **item,
                    "counts": snapshot.metadata["counts"],
                    "agency_rows": snapshot.metadata.get("agency_rows"),
                    "source_updated_on": snapshot.metadata.get("source_updated_on"),
                }
            )
            snapshot.evidence = tuple(
                replace(
                    e,
                    attributes={
                        **e.attributes,
                        "raw_path": item["raw_path"],
                        "bundle": name,
                    },
                )
                for e in snapshot.evidence
            )
            snapshots.append(snapshot)
        snapshot = Snapshot.merge(*snapshots)
        content = encode_bundle(snapshot)
        manifest = {
            **entry,
            "inputs": audits,
            "file": name + ".parquet",
            "sha256": checksum(content),
            "rows": len(snapshot.evidence),
            "hosts": len(snapshot.hostnames),
            "population_completeness": "unknown",
            "label_basis": "source_membership",
        }
        decode_bundle(content, manifest)
        tables[manifest["file"]] = content
        sources[name] = manifest
        sys.stdout.write(
            json.dumps(
                {
                    "bundle": name,
                    "rows": manifest["rows"],
                    "hosts": manifest["hosts"],
                    "bytes": len(content),
                    "source_counts": {
                        key: sum(a["counts"][key] for a in audits)
                        for key in ("rows", "empty", "invalid", "page_scoped")
                    },
                }
            )
            + "\n"
        )
    if "cisa" in entries:
        license_record = read_archive(
            ROOT / entries["cisa"]["license_input"]["raw_path"]
        )
        tables["CC0-1.0.txt"] = license_record["body"].encode()
    for filename, content in tables.items():
        path = output / filename
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
    atomic_write(
        output / "manifest.json",
        json.dumps({"schema_version": 1, "sources": sources}, indent=2, sort_keys=True)
        + "\n",
    )


def main():
    """Run the selected collection, research-import, or offline-build stage."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_parser = commands.add_parser("fetch")
    fetch_parser.add_argument(
        "--collection", default=datetime.now(UTC).date().isoformat()
    )
    research = commands.add_parser("import-research")
    research.add_argument("repository", type=Path)
    commands.add_parser("build")
    args = parser.parse_args()
    if args.command == "fetch":
        if (
            not args.collection
            or Path(args.collection).name != args.collection
            or args.collection in {".", ".."}
        ):
            raise ValueError("Collection must be a single directory name")
        fetch(args.collection)
    elif args.command == "import-research":
        import_research(args.repository)
    else:
        build()


if __name__ == "__main__":
    main()
