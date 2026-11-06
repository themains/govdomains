import json

import pytest
import requests

from govdomains import Snapshot
from govdomains.crawl import CommonCrawl, import_crawl_csv, patterns_for


class Response:
    def __init__(self, data=None, records=(), error=False):
        self.data, self.records, self.error = data, records, error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.error:
            raise requests.HTTPError("503 unavailable")

    def json(self):
        return self.data

    def iter_lines(self):
        for item in self.records:
            yield json.dumps(item).encode()


class Session:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


def capture(host, stamp="20240713123456"):
    return {"url": "https://" + host + "/page", "timestamp": stamp}


def test_dedup_pagination_and_checkpoint_resume(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    session = Session(
        Response({"pages": 2}),
        Response(records=[capture("a.gov"), capture("a.gov", "20240714123456")]),
    )
    first = CommonCrawl("CC-MAIN-2024-30", session=session, delay=0).collect(
        "gov", checkpoint=checkpoint
    )
    assert first.hostnames == ("a.gov",)
    assert not first.metadata["query_complete"]
    assert first.evidence[0].attributes["last_capture"] == "20240714123456"
    resumed = Session(Response({"pages": 2}), Response(records=[capture("b.gov")]))
    final = CommonCrawl("CC-MAIN-2024-30", session=resumed, delay=0).collect(
        "gov", max_pages=None, checkpoint=checkpoint
    )
    assert final.hostnames == ("a.gov", "b.gov")
    assert final.metadata["query_complete"]
    assert final.metadata["capture_count"] == 3
    assert resumed.calls[1]["params"]["page"] == 1
    assert final.evidence[0].label == "unknown"
    assert "url" not in final.evidence[0].attributes


def test_failure_does_not_advance_checkpoint(tmp_path):
    path = tmp_path / "checkpoint.json"
    session = Session(
        Response({"pages": 2}),
        Response(records=[capture("a.gov")]),
        Response(error=True),
    )
    with pytest.raises(requests.HTTPError):
        CommonCrawl("CC-MAIN-2024-30", session=session, delay=0).collect(
            "gov", max_pages=None, checkpoint=path
        )
    assert Snapshot.load(path).metadata["next_page"] == 1
    assert not Snapshot.load(path).metadata["query_complete"]


def test_checkpoint_query_mismatch(tmp_path):
    path = tmp_path / "checkpoint.json"
    session = Session(Response({"pages": 1}), Response(records=[capture("a.gov")]))
    client = CommonCrawl("CC-MAIN-2024-30", session=session, delay=0)
    client.collect("gov", checkpoint=path)
    with pytest.raises(ValueError, match="different query"):
        client.collect("gov.uk", checkpoint=path)


@pytest.mark.parametrize("response", [Response({"pages": "2"}), Response(error=True)])
def test_page_count_failures_are_not_empty_results(response):
    with pytest.raises((ValueError, requests.HTTPError)):
        CommonCrawl("CC-MAIN-2024-30", session=Session(response)).collect("gov")


def test_invalid_capture_and_outside_query_fail():
    session = Session(
        Response({"pages": 1}), Response(records=[capture("a.gov.evil.org")])
    )
    with pytest.raises(ValueError, match="outside"):
        CommonCrawl("CC-MAIN-2024-30", session=session, delay=0).collect("gov")


def test_zero_pages_and_country_patterns():
    result = CommonCrawl(
        "CC-MAIN-2024-30", session=Session(Response({"pages": 0}))
    ).collect("gov")
    assert result.metadata["query_complete"]
    assert result.hostnames == ()
    assert patterns_for("United States") == ("gov", "mil")
    with pytest.raises(ValueError):
        patterns_for("Unknown")


def test_smaller_budget_does_not_return_a_larger_checkpoint(tmp_path):
    path = tmp_path / "checkpoint.json"
    session = Session(
        Response({"pages": 2}),
        Response(records=[capture("a.gov")]),
        Response(records=[capture("b.gov")]),
        Response({"pages": 2}),
    )
    client = CommonCrawl("CC-MAIN-2024-30", session=session, delay=0)
    client.collect("gov", max_pages=None, checkpoint=path)
    with pytest.raises(ValueError, match="budget"):
        client.collect("gov", max_pages=1, checkpoint=path)


def test_import_notebook_crawl_csv(tmp_path):
    source = tmp_path / "crawl.csv"
    source.write_text(
        "url,timestamp\nhttps://a.gov/page,20240701120000\n"
        "https://a.gov/other,20240702120000\n"
    )
    snapshot = import_crawl_csv(source, source="CC-MAIN-2024-30")
    assert snapshot.hostnames == ("a.gov",)
    assert snapshot.metadata["capture_count"] == 2
    assert snapshot.evidence[0].label == "unknown"
    assert snapshot.evidence[0].scope == "exact"
    assert snapshot.evidence[0].attributes["first_capture"] == "20240701120000"


def test_partial_page_is_not_checkpointed(tmp_path):
    path = tmp_path / "checkpoint.json"
    session = Session(
        Response({"pages": 2}),
        Response(records=[capture("a.gov")]),
        Response(records=[capture("b.gov"), {"message": "bad response"}]),
    )
    with pytest.raises(KeyError):
        CommonCrawl("CC-MAIN-2024-30", session=session, delay=0).collect(
            "gov", max_pages=None, checkpoint=path
        )
    saved = Snapshot.load(path)
    assert saved.hostnames == ("a.gov",)
    assert saved.metadata["next_page"] == 1
