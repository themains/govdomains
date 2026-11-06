# govdomains

[![CI](https://github.com/themains/govdomains/actions/workflows/ci.yml/badge.svg)](https://github.com/themains/govdomains/actions/workflows/ci.yml)

[![Docs](https://github.com/themains/govdomains/actions/workflows/docs.yml/badge.svg)](https://themains.github.io/govdomains/)

<!-- SPHINX-START -->

`govdomains` helps you build a list of likely government hostnames and inspect
why each one was included. It combines hostname patterns such as `.gov` with
evidence from source lists. It ships selected CISA and Govdirectory lists and
can collect more hosts from live sources or Common Crawl.

The unit is a hostname, including subdomains. The package keeps `agency.gov`
and `www.agency.gov` separate. It accepts URLs as input, but classifies the
hostname and reports when it ignores a path.

The 170 patterns, covering 162 country labels, come from
[gov_privacy](https://github.com/themains/gov_privacy). Neither the patterns nor
the lists establish a complete population of government hosts. A positive result
is an inference about affiliation; it does not verify ownership, existence, or
current use. A missing match means `unknown`.

## Install

Python 3.12 or newer. Until a PyPI release is published:

```sh
pip install 'govdomains[data] @ git+https://github.com/themains/govdomains.git'
```

The `data` extra installs PyArrow to read the bundled Parquet tables. Omit it
when using only patterns, local CSV imports, and network collection. Import and
classification work offline; fetching lists and querying Common Crawl require
explicit calls. You do not need a model, browser, paid API, or separate dataset
download.

## Use the bundled lists offline

```python
from govdomains import Classifier, bundled_sources, load_bundled

print(bundled_sources().keys())
snapshot = load_bundled()
print(len(snapshot.hostnames))
classifier = Classifier(snapshot.evidence)
result = classifier.classify_one("www.bundeskanzleramt.gv.at")
print(result.label, result.methods)
```

`load_bundled()` loads the CISA and Govdirectory snapshots shipped with the
installed package. It does not fetch updates. Pass `snapshot.evidence` to
`Classifier` to use the lists alongside the patterns; `Classifier()` alone
uses only patterns.

| Bundle | Unique listed hostnames | Observation date | Default |
|---|---:|---|---|
| `cisa` | 17,025 | 2026-11-06 UTC retrieval | Yes |
| `govdirectory` | 12,787 | 2026-11-06 UTC collection | Yes |
| `cisa_research` | 12,047 | Unknown, retained from gov_privacy | No |
| `govdirectory_research` | 9,696 | Unknown, retained from gov_privacy | No |

The Govdirectory snapshot covers its 46 published jurisdiction pages, including
the European Union. Those pages can omit government bodies. The package retains
website addresses, institution names, source categories, entity links, and
update dates where supplied. It preserves each source's categories without
mapping them to a common set of government tiers.

```sh
govdomains bundled
govdomains bundled --output lists.json
govdomains bundled govdirectory_research --output research.json
govdomains classify www.bundeskanzleramt.gv.at --bundled govdirectory
govdomains export lists.json --label government --output hosts.csv
```

Select specific snapshots with `load_bundled("govdirectory")` or
`load_bundled("cisa_research", "govdirectory_research")`. The older research
extracts are available only by name. Their observation dates are unknown, so
they cannot support a dated historical inference. For dated snapshots, the
retrieval date records when the list was collected; entries may already have
been stale.

`snapshot.hostnames` contains all listed candidate hosts. Some entries refer
only to a page on a host, so the number of candidates can exceed the number
classified as government. Use `export --label government` to select hosts
with evidence that supports that inference.

The four normalized tables occupy about 1.9 MB before wheel compression.
The repository keeps the raw downloaded responses in `data/raw/`, outside the
wheel. The [data documentation](https://themains.github.io/govdomains/data.html)
describes source coverage, historical comparisons, and how to fetch and rebuild
the tables.

## Classify hostnames

```python
from govdomains import Classifier, Evidence

classifier = Classifier(
    [Evidence("city.example", source="my-reviewed-list", observed_on="2024-07-01")]
)
for result in classifier.classify(
    [
        "agency.gov",
        "city.example",
        "agency.gov.example.org",
    ]
):
    print(result.hostname, result.label, result.methods)
```

The labels are `government`, `not_government`, and `unknown`. The default rules
identify likely government hosts and return `unknown` for the rest. Conflicting
positive and negative evidence produces `unknown` with
`reason="conflicting_evidence"`. Absence from a list never produces a negative.
Each result includes its matched rules and supporting source records, with
dates and original source categories. Results do not include probabilities or
inferred administrative levels.

```sh
govdomains classify agency.gov agency.gov.example.org
govdomains classify --file hosts.txt --snapshot sources.json
govdomains rules --country 'India'
```

Evidence applies at the scope recorded by its source. A listing for one page
on a commercial platform cannot establish that the whole platform is
governmental. Evidence for an exact hostname does not extend to its parent,
siblings, or subdomains.

## Collect and combine sources

```sh
govdomains fetch cisa --output cisa.json
govdomains fetch gsa --output gsa.json

govdomains discover --suffix gov --index CC-MAIN-2024-30 \
  --max-pages 1 --checkpoint cc-progress.json --output cc-sample.json

govdomains merge cisa.json gsa.json cc-sample.json --output sources.json
govdomains export sources.json --label government --output hosts.csv
```

`fetch` retrieves the CISA `.gov` or GSA nonstandard-domain list available at
the time of the request. It records the retrieval date, content hash, and import
counts. The two lists cover different kinds of domains and can contain stale
entries or omissions.

`discover` searches one Common Crawl index for a suffix. It reads one page by
default. Use `--all-pages` to read every reported page; large namespaces may take
substantial time. The collector delays requests, sends them one at a time, and
retries transient HTTP failures.

A checkpoint records completed pages. Rerunning the same query resumes from the
last completed page. `--max-pages` sets the total page budget, including pages
already checkpointed. Use a separate checkpoint for each query.

The collector reads URL records and saves one summary per host, with its first
and last capture timestamps. It does not save the URLs or page bodies. If
collection fails, it raises an error and preserves any existing final output.
`query_complete` records whether every reported page was read; a completed query
can still miss government hosts. Common Crawl observations have an `unknown`
affiliation label unless other evidence or rules support a classification.

```python
from govdomains.crawl import CommonCrawl, patterns_for
from govdomains import Snapshot
from govdomains.sources import fetch_list

with CommonCrawl("CC-MAIN-2024-30") as crawl:
    observed = crawl.collect("gov", max_pages=1)

combined = Snapshot.merge(fetch_list("cisa"), observed)
combined.save("sources.json")
combined.export_csv("hosts.csv", label="government")
print(patterns_for("United States"))
```

`patterns_for` exposes the notebook's country labels and discovery suffixes.
It does not promise coverage of all government namespaces in that country.

## Import local and historical lists

```sh
govdomains import-list old-cisa.csv --format cisa --source cisa-2024 \
  --date 2024-07-01 --output old-cisa.json

govdomains import-list uk.csv --column 'Domain Name' --source uk-list \
  --date 2025-01-13 --output uk.json

govdomains import-list combined_tsv_data.tsv --format govdirectory \
  --source govdirectory-extract --output govdirectory.json
```

The importer supports `cisa`, `gsa`, `india`, `govdirectory`, and `generic`
formats. Generic CSV expects a `hostname` column; use `--column` and
`--delimiter` for other tables. The importer preserves selected institutional
attributes, counts missing and invalid values, and rejects incompatible schemas.
It treats URLs with a path beyond the root as evidence about that page, which
alone cannot label the host government. Files without a supplied observation
date stay undated; filenames and Git history do not determine that date.

To reuse a notebook-exported Common Crawl CSV without retaining URL rows:

```sh
govdomains import-crawl common_crawl_sample_n1000.csv \
  --source CC-MAIN-2024-30-sample --output crawl.json
```

The crawl importer reads the `url` and `timestamp` columns, groups observations
by hostname, and preserves the first and last capture dates. It records the
input file hash and leaves affiliation `unknown`.

```python
from govdomains import Classifier, Snapshot

snapshot = Snapshot.load("old-cisa.json")
result = Classifier(snapshot.evidence).classify_one("agency.gov", as_of="2024-07-01")
```

`as_of` includes only observations dated at or before that day. It does not infer
continuous ownership, apply source removals, or certify the host's status on
that date. Undated rules are excluded from historical queries by default.
`allow_undated_rules=True` (CLI: `--allow-undated-rules`) explicitly extrapolates
them and marks the affected results. User-supplied `Rule` objects can instead
specify `valid_from` and exclusive `valid_to` dates.

Without `as_of`, rules are evaluated against today's UTC date, and the result
records `evaluated_on`. Dated rules outside their interval do not apply.

Merging snapshots keeps the union of their observations. An older positive
therefore persists even if a newer list omits the host, and contrary observations
can conflict. Keep separate snapshots when comparing list membership over time.
A host's first and last crawl timestamps record sightings; they do not define
an ownership interval.

## Files and reproducibility

Snapshots store evidence and source metadata in portable JSON, with a schema
version and SHA-256 integrity check. Saving replaces the file atomically, and
loading rejects corrupt snapshots. Repeated identical evidence is deduplicated.

CSV export creates one row per normalized observed hostname, with evidence and
matched rules encoded as JSON columns. A companion `.manifest.json` records the
input snapshot and rule hashes, filters, counts, source metadata, and CSV hash.
Each hostname remains a separate row, so the row count is not an institution
count. The completeness of any exported population is unknown.

The bundled CISA and Govdirectory data are licensed under CC0-1.0. Their
manifest records input hashes, source URLs, dates, and counts. The loader checks
each Parquet table's checksum, Arrow schema, dates, required values, uniqueness,
and counts before returning evidence. The package ships no crawl URL inventory
or website content. It supports India and GSA imports, but does not bundle those
lists. Imported data retain their source's license and redistribution conditions.
The package code is licensed under Apache-2.0.

## Development

```sh
uv sync --all-groups
make ci
make ci-docker
```

`make ci` runs Ruff, Pyright, docstring checks, tests, Sphinx with Furo, and
distribution validation. `make check` runs the full preen conformance check.
Tests block network access. They exercise installed-package behavior,
normalization, conflicts, historical filtering, source parsing, CLI roundtrips,
streaming collection, pagination, checkpoints, failure recovery, bundled data
integrity, and parsing of archived Govdirectory pages.

Docker CI uses the standard `python:3.14-slim` image; override `PYTHON_IMAGE` to
test another supported version. GitHub CI tests Python 3.12 and 3.14 through
py-canon's shared workflow.

## Validation status

The classifier is an alpha implementation and has not been independently
benchmarked. Validation needs independently annotated examples across
jurisdictions, languages, conventional and nonstandard namespaces, shared
hosts, and ambiguous public bodies. It should measure pattern-only, list-only,
and combined classification separately from how many candidate hosts each
collection method finds.

Content models such as piedomains, automatic inference of government tiers,
and a maintained global dataset are not implemented. Adding them requires
measuring their contribution and maintenance costs.

The [changelog](https://themains.github.io/govdomains/changelog.html) records
development history.
