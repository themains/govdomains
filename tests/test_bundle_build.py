import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def builder(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/update_bundles.py"
    spec = importlib.util.spec_from_file_location("update_bundles", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "RAW", tmp_path / "data/raw")
    monkeypatch.setattr(module, "CATALOG", tmp_path / "data/raw/catalog.json")
    return module


def test_raw_archive_checksum_and_completion_are_enforced(builder, tmp_path):
    path = tmp_path / "input.jsonl.gz"
    record = {
        "body": "original\n",
        "sha256": builder.checksum(b"original\n"),
        "ok": True,
    }
    builder.archive(path, record)
    assert builder.read_archive(path) == record
    builder.archive(path, {**record, "body": "changed"})
    with pytest.raises(ValueError, match="corrupt"):
        builder.read_archive(path)
    builder.archive(path, {**record, "ok": False})
    with pytest.raises(ValueError, match="Unsuccessful"):
        builder.read_archive(path)


def test_verified_archive_resume_never_refetches(builder, tmp_path):
    path = tmp_path / "input.jsonl.gz"
    record = {
        "body": "source",
        "sha256": builder.checksum(b"source"),
        "ok": True,
        "url": "https://source.example/",
    }
    builder.archive(path, record)
    assert builder.fetch_archive(None, record["url"], path) == record


def test_offline_build_is_reproducible_and_rejects_changed_inputs(builder, tmp_path):
    body = "Domain name,Domain type,City\ncity.gov,City,Springfield\n"
    record = {
        "body": body,
        "sha256": builder.checksum(body.encode()),
        "ok": True,
        "url": "https://source.example/cisa.csv",
        "fetched_at": "2024-01-02T00:00:00+00:00",
    }
    path = tmp_path / "data/raw/input.jsonl.gz"
    builder.archive(path, record)
    builder.save_catalog(
        {
            "example": {
                "default": True,
                "format": "cisa",
                "license": "CC0-1.0",
                "observed_on": "2024-01-02",
                "inputs": [builder.descriptor(path, record)],
            }
        }
    )
    builder.build()
    output = tmp_path / "src/govdomains/data/bundled"
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    builder.build()
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["sources"]["example"]["hosts"] == 1
    replacement = body.replace("city.gov", "different.gov")
    builder.archive(
        path,
        {
            **record,
            "body": replacement,
            "sha256": builder.checksum(replacement.encode()),
        },
    )
    with pytest.raises(ValueError, match="differs from catalog"):
        builder.build()
