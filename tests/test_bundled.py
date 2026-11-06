import hashlib
import io
import json
from importlib.resources import files

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from govdomains import Classifier, Evidence, Snapshot, bundled_sources, load_bundled
from govdomains.bundled import decode_bundle, encode_bundle, evidence_schema
from govdomains.cli import main


def fixture_bundle():
    snapshot = Snapshot(
        (
            Evidence(
                "city.example",
                "directory",
                observed_on="2024-01-02",
                attributes={
                    "source_value": "https://city.example/",
                    "Type": "municipality",
                },
            ),
            Evidence(
                "shared.example",
                "directory",
                observed_on="2024-01-02",
                scope="page",
                attributes={"source_value": "https://shared.example/agency"},
            ),
        ),
        {},
    )
    content = encode_bundle(snapshot)
    entry = {
        "sha256": hashlib.sha256(content).hexdigest(),
        "rows": 2,
        "hosts": 2,
        "observed_on": "2024-01-02",
    }
    return content, entry


def test_parquet_preserves_evidence_scope_attributes_and_dates():
    content, entry = fixture_bundle()
    snapshot = decode_bundle(content, entry)
    classifier = Classifier(snapshot.evidence, rules=())
    assert classifier.classify_one("city.example").label == "government"
    assert classifier.classify_one("sub.city.example").label == "unknown"
    assert classifier.classify_one("shared.example").label == "unknown"
    assert (
        classifier.classify_one("city.example", as_of="2024-01-01").label == "unknown"
    )
    assert (
        classifier.classify_one("city.example", as_of="2024-01-02").label
        == "government"
    )
    assert snapshot.evidence[0].attributes["source_value"] == "https://city.example/"


def test_checksum_and_manifest_counts_are_enforced():
    content, entry = fixture_bundle()
    with pytest.raises(ValueError, match="checksum"):
        decode_bundle(content + b"corrupt", entry)
    with pytest.raises(ValueError, match="row count"):
        decode_bundle(content, {**entry, "rows": 3})
    with pytest.raises(ValueError, match="hostname count"):
        decode_bundle(content, {**entry, "hosts": 3})
    with pytest.raises(ValueError, match="date mismatch"):
        decode_bundle(content, {**entry, "observed_on": None})


@pytest.mark.parametrize("defect", ["type", "null", "scope", "duplicate", "map_null"])
def test_corrupt_table_is_rejected_even_with_matching_checksum(defect):
    content, entry = fixture_bundle()
    table = pq.read_table(io.BytesIO(content))
    rows = table.to_pylist()
    if defect == "type":
        table = table.set_column(0, "hostname", pa.array([1, 2]))
    else:
        if defect == "null":
            rows[0]["hostname"] = None
            schema = evidence_schema().set(0, pa.field("hostname", pa.string()))
        else:
            schema = evidence_schema()
        if defect == "scope":
            rows[0]["scope"] = "subtree"
        if defect == "duplicate":
            rows[1] = rows[0]
        if defect == "map_null":
            rows[0]["attributes"] = [("bad", None)]
        table = pa.Table.from_pylist(rows, schema=schema)
    sink = io.BytesIO()
    pq.write_table(table, sink)
    corrupted = sink.getvalue()
    with pytest.raises(ValueError):
        decode_bundle(
            corrupted, {**entry, "sha256": hashlib.sha256(corrupted).hexdigest()}
        )


def test_every_shipped_bundle_loads_and_agrees_with_source_accounting():
    catalog = bundled_sources()
    assert set(catalog) == {
        "cisa",
        "govdirectory",
        "cisa_research",
        "govdirectory_research",
    }
    for name, entry in catalog.items():
        snapshot = load_bundled(name)
        assert len(snapshot.hostnames) == entry["hosts"]
        assert len(snapshot.evidence) == entry["rows"]
        assert all(e.observed_on == entry["observed_on"] for e in snapshot.evidence)
        input_rows = sum(i["counts"]["rows"] for i in entry["inputs"])
        rejected = sum(
            i["counts"]["empty"] + i["counts"]["invalid"] for i in entry["inputs"]
        )
        assert input_rows - rejected >= len(snapshot.evidence)
        assert all(
            "Security contact email" not in e.attributes for e in snapshot.evidence
        )
        assert all("source_value" in e.attributes for e in snapshot.evidence)
    assert (
        len(catalog["govdirectory"]["inputs"])
        == catalog["govdirectory"]["jurisdiction_pages"]
    )
    assert files("govdomains").joinpath("data/bundled/CC0-1.0.txt").is_file()


def test_defaults_exclude_undated_research_and_historical_inferences():
    snapshot = load_bundled()
    assert {e.attributes["bundle"] for e in snapshot.evidence} == {
        "cisa",
        "govdirectory",
    }
    historical = load_bundled("govdirectory_research")
    assert all(e.observed_on is None for e in historical.evidence)
    host = "www.bundeskanzleramt.gv.at"
    assert (
        Classifier(historical.evidence, rules=()).classify_one(host).label
        == "government"
    )
    assert (
        Classifier(historical.evidence, rules=())
        .classify_one(host, as_of="2024-01-01")
        .label
        == "unknown"
    )


def test_unknown_or_duplicate_source_selection_fails():
    with pytest.raises(ValueError, match="Unknown bundled"):
        load_bundled("../cisa")
    with pytest.raises(ValueError, match="Duplicate"):
        load_bundled("cisa", "cisa")


def test_bundled_cli_catalog_snapshot_and_classification(tmp_path, capsys):
    assert main(["bundled"]) == 0
    assert "govdirectory" in json.loads(capsys.readouterr().out)
    path = tmp_path / "list.json"
    assert main(["bundled", "govdirectory_research", "--output", str(path)]) == 0
    assert (
        len(Snapshot.load(path).hostnames)
        == bundled_sources()["govdirectory_research"]["hosts"]
    )
    capsys.readouterr()
    assert (
        main(
            [
                "classify",
                "www.bundeskanzleramt.gv.at",
                "--bundled",
                "govdirectory_research",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["label"] == "government"
    assert main(["bundled", "govdirectory"]) == 2


def test_missing_arrow_is_actionable_without_disabling_core(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "pyarrow", None)
    assert bundled_sources()["cisa"]["hosts"] > 0
    assert Classifier().classify_one("agency.gov").label == "government"
    with pytest.raises(ImportError, match=r"govdomains\[data\]"):
        load_bundled("cisa")
