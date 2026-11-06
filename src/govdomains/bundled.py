"""Offline source snapshots distributed with the package."""

import hashlib
import io
import json
import re
from datetime import date
from importlib.resources import files

from .core import Evidence, validate_date
from .snapshot import Snapshot


def evidence_schema():
    """Return the explicit Arrow schema for bundled list observations."""
    try:
        import pyarrow as pa
    except ImportError as exc:
        raise ImportError(
            "Bundled lists require: pip install 'govdomains[data]'"
        ) from exc
    return pa.schema(
        [
            pa.field("hostname", pa.string(), nullable=False),
            pa.field("source", pa.string(), nullable=False),
            pa.field("observed_on", pa.date32()),
            pa.field("scope", pa.string(), nullable=False),
            pa.field("attributes", pa.map_(pa.string(), pa.string()), nullable=False),
        ],
        metadata={b"govdomains_schema_version": b"1"},
    )


def bundled_sources() -> dict[str, dict]:
    """Describe available snapshots without loading tables or accessing the network."""
    manifest = json.loads(
        files("govdomains").joinpath("data/bundled/manifest.json").read_text()
    )
    if manifest.get("schema_version") != 1 or not isinstance(
        manifest.get("sources"), dict
    ):
        raise ValueError("Unsupported bundled manifest schema")
    for name, entry in manifest["sources"].items():
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", name):
            raise ValueError("Invalid bundle identifier")
        if entry.get("file") != name + ".parquet":
            raise ValueError("Invalid bundle filename")
        if not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", "")):
            raise ValueError("Invalid bundle checksum")
        for field in ("rows", "hosts"):
            if type(entry.get(field)) is not int or entry[field] < 1:
                raise ValueError("Invalid bundle counts")
        if type(entry.get("default")) is not bool:
            raise ValueError("Invalid default bundle flag")
        validate_date(entry["observed_on"])
        if not entry.get("license") or not entry.get("inputs"):
            raise ValueError("Bundle is missing license or provenance")
    return manifest["sources"]


def decode_bundle(content: bytes, entry: dict) -> Snapshot:
    """Validate and decode one Parquet snapshot using its manifest entry."""
    schema = evidence_schema()
    import pyarrow.parquet as pq

    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise ValueError("Bundled table checksum mismatch")
    table = pq.read_table(io.BytesIO(content))
    if not table.schema.equals(schema) or table.schema.metadata != schema.metadata:
        raise ValueError("Bundled table schema mismatch")
    if table.num_rows != entry["rows"]:
        raise ValueError("Bundled table row count mismatch")
    for field in schema:
        if not field.nullable and table[field.name].null_count:
            raise ValueError("Null in required bundle field")
    evidence = []
    for row in table.to_pylist():
        attributes = dict(row["attributes"])
        if len(attributes) != len(row["attributes"]) or any(
            not isinstance(value, str) for value in attributes.values()
        ):
            raise ValueError("Invalid bundled attributes")
        observed = row["observed_on"].isoformat() if row["observed_on"] else None
        if observed != entry["observed_on"]:
            raise ValueError("Bundled observation date mismatch")
        item = Evidence(
            row["hostname"],
            row["source"],
            observed_on=observed,
            scope=row["scope"],
            attributes=attributes,
        )
        if item.hostname != row["hostname"]:
            raise ValueError("Bundled hostname is not normalized")
        evidence.append(item)
    snapshot = Snapshot(tuple(evidence), {"bundle": entry})
    if (
        len(snapshot.evidence) != entry["rows"]
        or len(snapshot.hostnames) != entry["hosts"]
    ):
        raise ValueError("Bundled uniqueness or hostname count mismatch")
    return snapshot


def load_bundled(*names: str) -> Snapshot:
    """Load selected offline lists; default to the latest shipped source snapshots.

    Research extracts with unknown collection dates require explicit selection.
    Shipped snapshots are not guaranteed to represent current source membership.
    """
    catalog = bundled_sources()
    selected = names or tuple(name for name, item in catalog.items() if item["default"])
    if not selected:
        raise ValueError("No default bundled sources")
    if len(set(selected)) != len(selected):
        raise ValueError("Duplicate bundled source selection")
    snapshots = []
    for name in selected:
        if name not in catalog:
            raise ValueError(
                f"Unknown bundled source {name!r}; choose from {', '.join(catalog)}"
            )
        entry = catalog[name]
        content = (
            files("govdomains").joinpath("data/bundled", entry["file"]).read_bytes()
        )
        snapshots.append(decode_bundle(content, entry))
    return snapshots[0] if len(snapshots) == 1 else Snapshot.merge(*snapshots)


def encode_bundle(snapshot: Snapshot) -> bytes:
    """Serialize list evidence for the offline build stage."""
    schema = evidence_schema()
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = []
    for item in snapshot.evidence:
        if item.method != "list" or item.label != "government":
            raise ValueError("Bundles contain government source-list observations only")
        if any(not isinstance(value, str) for value in item.attributes.values()):
            raise ValueError("Bundled source attributes must be strings")
        rows.append(
            {
                "hostname": item.hostname,
                "source": item.source,
                "observed_on": (
                    date.fromisoformat(item.observed_on) if item.observed_on else None
                ),
                "scope": item.scope,
                "attributes": sorted(item.attributes.items()),
            }
        )
    sink = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), sink, compression="zstd")
    return sink.getvalue()
