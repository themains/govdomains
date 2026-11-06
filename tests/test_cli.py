import json

from govdomains.cli import main


def test_cli_offline_classification(capsys):
    assert main(["classify", "agency.gov", "government-news.example"]) == 0
    results = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["label"] for r in results] == ["government", "unknown"]
    assert main(["classify", "https://user:secret@agency.gov"]) == 1
    assert "secret" not in capsys.readouterr().out


def test_cli_import_export_roundtrip(tmp_path, capsys):
    source = tmp_path / "list.csv"
    source.write_text("hostname\ncity.example\n")
    snapshot = tmp_path / "snapshot.json"
    target = tmp_path / "hosts.csv"
    assert (
        main(
            ["import-list", str(source), "--source", "test", "--output", str(snapshot)]
        )
        == 0
    )
    assert main(["export", str(snapshot), "--output", str(target)]) == 0
    assert "city.example" in target.read_text()
    assert main(["classify", "--snapshot", str(snapshot), "city.example"]) == 0
    assert '"label": "government"' in capsys.readouterr().out


def test_cli_error_leaves_existing_output(tmp_path, capsys):
    source = tmp_path / "bad.csv"
    source.write_text("bad\nwrong\n")
    target = tmp_path / "snapshot.json"
    target.write_text("preserve")
    assert (
        main(["import-list", str(source), "--source", "test", "--output", str(target)])
        == 2
    )
    assert target.read_text() == "preserve"
