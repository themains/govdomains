from pathlib import Path

import pytest

from govdomains.directory import country_pages, parse_country

PAGE = (Path(__file__).parent / "fixtures/govdirectory.html").read_text()


def parse(content):
    return parse_country(
        content,
        url="https://www.govdirectory.org/switzerland/",
        jurisdiction_label="Switzerland",
        observed_on="2026-11-06",
    )


def test_real_directory_rows_preserve_entity_links_and_source_dates():
    snapshot = parse(PAGE)
    assert snapshot.hostnames == ("www.vbs.admin.ch", "www.wbf.admin.ch")
    assert snapshot.metadata["agency_rows"] == 2
    assert snapshot.metadata["source_updated_on"] == "2026-09-25"
    department = next(e for e in snapshot.evidence if e.hostname == "www.vbs.admin.ch")
    expected_name = (
        "Federal Department of Defence, "  # codespell:ignore
        "Civil Protection and Sports"
    )
    assert department.attributes["Name"] == expected_name
    assert (
        department.attributes["Govdirectory URL"]
        == "https://www.govdirectory.org/switzerland/Q667135/"
    )
    assert department.attributes["Type"] == "federal department of Switzerland"
    assert department.observed_on == "2026-11-06"


def test_page_scope_and_missing_website_are_accounted_for():
    changed = PAGE.replace(
        'href="https://www.vbs.admin.ch/"', 'href="https://shared.example/agency"'
    )
    changed = changed.replace('title="Website"', 'title="Other"', 1)
    snapshot = parse(changed)
    assert snapshot.metadata["counts"]["empty"] == 1
    assert len(snapshot.evidence) == 1
    changed = PAGE.replace(
        'href="https://www.vbs.admin.ch/"', 'href="https://shared.example/agency"'
    )
    snapshot = parse(changed)
    assert (
        next(e for e in snapshot.evidence if e.hostname == "shared.example").scope
        == "page"
    )


def test_directory_index_keeps_jurisdiction_labels():
    content = (
        '<main><ul class="box-list">'
        '<li><a href="/european-union/">European Union</a></li>'
        '<li><a href="/switzerland/">Switzerland</a></li></ul></main>'
    )
    assert country_pages(content)[0] == {
        "label": "European Union",
        "url": "https://www.govdirectory.org/european-union/",
    }
    with pytest.raises(ValueError, match="country link"):
        country_pages(content.replace("/switzerland/", "https://unrelated.example/"))


@pytest.mark.parametrize(
    "content",
    [
        "<html>Service unavailable</html>",
        PAGE.replace('id="mainOrgTable"', 'id="changed"'),
        PAGE.replace("Q667135/", "not-an-entity/"),
    ],
)
def test_changed_or_invalid_directory_pages_fail(content):
    with pytest.raises(ValueError):
        parse(content)
