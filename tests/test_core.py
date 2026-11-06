import pytest

from govdomains import Classifier, Evidence, Rule, load_rules, normalize_hostname


@pytest.mark.parametrize(
    "value,host",
    [
        ("HTTPS://Agency.GOV.:443/path?q=1", "agency.gov"),
        ("https://政务.cn/", "xn--zfr164b.cn"),
        ("service.agency.gov", "service.agency.gov"),
        ("//agency.gov/path", "agency.gov"),
    ],
)
def test_normalize(value, host):
    assert normalize_hostname(value) == host


@pytest.mark.parametrize(
    "value",
    [
        "",
        "https://",
        "https://user:secret@agency.gov/",
        "https://agency.gov:bad",
        "https://127.0.0.1/",
        "[::1]",
        "agency.gov\\@example.org",
        "a b.gov",
        "agency.gov\nexample.org",
        "https://a..gov/",
        "ftp://agency.gov/",
        None,
    ],
)
def test_invalid_input_is_not_negative(value):
    result = Classifier().classify_one(value)
    assert result.status == "error"
    assert result.label == "unknown"


def test_bundled_patterns_and_boundaries():
    classifier = Classifier()
    results = classifier.classify(
        [
            "agency.gov",
            "office.gov.uk",
            "agency.gov.example.org",
            "example.org/gov.uk",
            "agency.nic.in",
            "agency.govt.nz",
            "government-news.com",
        ]
    )
    assert [r.label for r in results] == [
        "government",
        "government",
        "unknown",
        "unknown",
        "government",
        "government",
        "unknown",
    ]
    assert results[3].path_ignored
    assert len(load_rules()) == 170
    assert all(r.basis == "research_heuristic" for r in load_rules())


def test_lists_extend_patterns_without_inheriting():
    classifier = Classifier([Evidence("city.example", "official-directory")])
    assert classifier.classify_one("city.example").methods == ("list",)
    assert classifier.classify_one("other.city.example").label == "unknown"


def test_shared_host_page_is_not_host_evidence():
    result = Classifier(
        [Evidence("platform.example", "directory", scope="page")]
    ).classify_one("platform.example/agency")
    assert result.label == "unknown"
    assert result.evidence[0].scope == "page"
    assert result.methods == ()


def test_conflicting_signals_abstain():
    evidence = Evidence("agency.gov", "review", method="review", label="not_government")
    result = Classifier([evidence]).classify_one("agency.gov")
    assert result.label == "unknown"
    assert result.reason == "conflicting_evidence"
    assert set(result.methods) == {"review", "pattern"}


def test_specific_rule_exception():
    rules = [Rule("gov"), Rule("tenant.gov", label="not_government", scope="exact")]
    classifier = Classifier(rules=rules)
    assert classifier.classify_one("tenant.gov").label == "not_government"
    assert classifier.classify_one("sub.tenant.gov").label == "government"


def test_historical_dates_and_extrapolation():
    evidence = [
        Evidence("city.example", "old", observed_on="2020-01-01"),
        Evidence("new.example", "new", observed_on="2025-01-01"),
        Evidence("undated.example", "unknown"),
    ]
    classifier = Classifier(evidence)
    kwargs = {"as_of": "2021-01-01"}
    assert classifier.classify_one("city.example", **kwargs).label == "government"
    for host in ["new.example", "undated.example", "agency.gov"]:
        assert classifier.classify_one(host, **kwargs).label == "unknown"
    result = classifier.classify_one("agency.gov", **kwargs, allow_undated_rules=True)
    assert result.label == "government"
    assert result.historical_extrapolation


def test_rule_interval_exclusive_end():
    classifier = Classifier(
        rules=[Rule("gov", valid_from="2020-01-01", valid_to="2022-01-01")]
    )
    assert classifier.classify_one("a.gov", as_of="2021-01-01").label == "government"
    assert classifier.classify_one("a.gov", as_of="2022-01-01").label == "unknown"
    assert classifier.classify_one("a.gov").label == "unknown"


def test_historical_crawl_summary_withholds_future_capture():
    item = Evidence(
        "a.gov",
        "crawl",
        method="crawl",
        label="unknown",
        observed_on="2024-07-01",
        attributes={
            "first_capture": "20240701120000",
            "last_capture": "20240730120000",
        },
    )
    result = Classifier([item]).classify_one("a.gov", as_of="2024-07-15")
    assert "last_capture" not in result.evidence[0].attributes
    assert item.attributes["last_capture"] == "20240730120000"


def test_dates_and_batch_shape_validate():
    with pytest.raises(ValueError):
        Evidence("a.gov", "x", observed_on="20250101")
    with pytest.raises(ValueError):
        Classifier().classify_one("a.gov", as_of="not-a-date")
    with pytest.raises(TypeError):
        Classifier().classify("agency.gov")
