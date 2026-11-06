import json

import pytest

from govdomains import Classifier, Evidence, Snapshot
from govdomains.sources import parse_list


def test_cisa_preserves_types_but_not_contacts():
    source = (
        "Domain name,Domain type,Security contact email\n"
        "city.gov,City,private@example.org\n"
    )
    snapshot = parse_list(
        source, source="cisa:test", format="cisa", observed_on="2024-01-01"
    )
    assert snapshot.evidence[0].attributes == {
        "Domain type": "City",
        "source_value": "city.gov",
    }
    assert snapshot.evidence[0].observed_on == "2024-01-01"


def test_import_reports_missing_invalid_and_shared_hosts():
    source = (
        "url,name,sector\nhttps://city.example/,City,Local\n"
        "https://platform.example/agency,Agency,National\n"
        ",Missing,x\nhttp://127.0.0.1/,IP,x\n"
    )
    snapshot = parse_list(source, source="directory", format="india")
    assert snapshot.metadata["counts"] == {
        "rows": 4,
        "empty": 1,
        "invalid": 1,
        "page_scoped": 1,
    }
    assert (
        Classifier(snapshot.evidence).classify_one("platform.example").label
        == "unknown"
    )


@pytest.mark.parametrize(
    "source",
    ["Wrong column\na.gov\n", "hostname\na.gov,extra\n", "hostname\n127.0.0.1\n"],
)
def test_invalid_source_fails(source):
    with pytest.raises(ValueError):
        parse_list(source, source="test")


def test_bom_and_uk_custom_column():
    snapshot = parse_list(
        "\ufeffDomain Name,Owner\ncity.gov.uk,Town\n", source="uk", column="Domain Name"
    )
    assert snapshot.hostnames == ("city.gov.uk",)


def test_snapshot_roundtrip_dedup_and_integrity(tmp_path):
    evidence = Evidence("city.example", "directory", observed_on="2024-01-01")
    snapshot = Snapshot((evidence, evidence), {"source": "test"})
    path = tmp_path / "snapshot.json"
    snapshot.save(path)
    assert len(Snapshot.load(path).evidence) == 1
    assert Snapshot.load(path).sha256 == snapshot.sha256
    payload = json.loads(path.read_text())
    payload["evidence"][0]["hostname"] = "changed.example"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="checksum"):
        Snapshot.load(path)


def test_merge_keeps_source_identity_and_deterministic_export(tmp_path):
    a = Snapshot((Evidence("city.example", "a"),), {"source": "a"})
    b = Snapshot((Evidence("city.example", "b"),), {"source": "b"})
    merged = Snapshot.merge(a, b)
    assert merged.hostnames == ("city.example",)
    assert len(merged.evidence) == 2
    path = tmp_path / "hosts.csv"
    report = merged.export_csv(path, label="government")
    assert report["exported_hosts"] == 1
    original = path.read_bytes()
    merged.export_csv(path, label="government")
    assert path.read_bytes() == original
    assert (
        json.loads(path.with_suffix(".csv.manifest.json").read_text())[
            "snapshot_sha256"
        ]
        == merged.sha256
    )


def test_historical_export_does_not_discover_future_hosts(tmp_path):
    snapshot = Snapshot(
        (
            Evidence("past.gov", "old", observed_on="2020-01-01"),
            Evidence("future.gov", "new", observed_on="2025-01-01"),
        ),
        {},
    )
    path = tmp_path / "hosts.csv"
    snapshot.export_csv(path, as_of="2021-01-01", allow_undated_rules=True)
    assert "past.gov" in path.read_text()
    assert "future.gov" not in path.read_text()


def test_fetch_cisa_observation_and_failure():
    import requests
    from test_crawl import Response, Session

    from govdomains.sources import fetch_list

    response = Response()
    response.text = "Domain name,Domain type\ncity.gov,City\n"
    response.headers = {"ETag": "test-revision"}
    snapshot = fetch_list("cisa", session=Session(response))
    assert snapshot.metadata["date_basis"] == "retrieval_observation"
    assert snapshot.metadata["etag"] == "test-revision"
    assert snapshot.evidence[0].observed_on
    with pytest.raises(requests.HTTPError):
        fetch_list("cisa", session=Session(Response(error=True)))
