"""Parse Govdirectory's published country lists without network access."""

import csv
import io
import re
from urllib.parse import urljoin, urlsplit

from .sources import parse_list


def soup_from_html(content: str):
    """Parse an archived page with the optional collection dependencies."""
    from bs4 import BeautifulSoup

    return BeautifulSoup(content, "html.parser")


def country_pages(content: str) -> list[dict[str, str]]:
    """Enumerate the jurisdiction pages in the published directory index."""
    soup = soup_from_html(content)
    links = soup.select("main ul.box-list li a")
    if not links:
        raise ValueError("Govdirectory country index has no jurisdiction links")
    pages = []
    for link in links:
        path = link.get("href", "")
        if not isinstance(path, str) or not re.fullmatch(r"/[a-z-]+/", path):
            raise ValueError("Unexpected Govdirectory country link")
        pages.append(
            {
                "label": link.get_text(strip=True),
                "url": urljoin("https://www.govdirectory.org", path),
            }
        )
    if len({page["url"] for page in pages}) != len(pages):
        raise ValueError("Duplicate Govdirectory country pages")
    return pages


def parse_country(content: str, *, url: str, jurisdiction_label: str, observed_on: str):
    """Reproduce the site's TSV fields, retaining every listed website address."""
    soup = soup_from_html(content)
    body = soup.select_one("tbody#mainOrgTable")
    if body is None or soup.select_one("a#download") is None:
        raise ValueError("Govdirectory page is missing its agency table")
    date_match = re.search(
        r"Data last updated\s+(\d{4}-\d{2}-\d{2})", soup.get_text(" ", strip=True)
    )
    updated_on = date_match.group(1) if date_match else ""
    buffer = io.StringIO()
    fields = [
        "Name",
        "Govdirectory URL",
        "Type",
        "Website",
        "source_file",
        "source_updated_on",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    agency_count = 0
    for row in body.find_all("tr", recursive=False):
        cells = row.find_all("td", recursive=False)
        if len(cells) != 3:
            raise ValueError("Malformed Govdirectory agency row")
        entity_link = cells[0].find("a")
        if entity_link is None:
            raise ValueError("Missing Govdirectory entity link")
        entity_path = entity_link.get("href")
        if not isinstance(entity_path, str):
            raise ValueError("Invalid Govdirectory entity link")
        agency_count += 1
        entity = urljoin(url, entity_path)
        if urlsplit(entity).netloc != "www.govdirectory.org" or not re.search(
            r"/Q\d+/$", entity
        ):
            raise ValueError("Invalid Govdirectory entity link")
        websites = cells[1].select('a[title="Website"]')
        for website in websites or [None]:
            address = website.get("href", "") if website else ""
            if not isinstance(address, str):
                raise ValueError("Invalid website address attribute")
            writer.writerow(
                {
                    "Name": cells[0].get_text(" ", strip=True),
                    "Govdirectory URL": entity,
                    "Type": cells[2].get_text(" ", strip=True),
                    "Website": urljoin(url, address) if address else "",
                    "source_file": jurisdiction_label,
                    "source_updated_on": updated_on,
                }
            )
    if not agency_count:
        raise ValueError("Govdirectory agency table is empty")
    snapshot = parse_list(
        buffer.getvalue(), source=url, format="govdirectory", observed_on=observed_on
    )
    snapshot.metadata.update(
        agency_rows=agency_count,
        jurisdiction_label=jurisdiction_label,
        source_updated_on=updated_on or None,
    )
    return snapshot
