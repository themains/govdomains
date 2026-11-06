# govdomains

[![CI](https://github.com/themains/govdomains/actions/workflows/ci.yml/badge.svg)](https://github.com/themains/govdomains/actions/workflows/ci.yml)

[![Docs](https://github.com/themains/govdomains/actions/workflows/docs.yml/badge.svg)](https://themains.github.io/govdomains/)

<!-- SPHINX-START -->

Infer government affiliation from hostname patterns and source-list evidence.
Collect candidate hosts from official lists and Common Crawl, combine the
observations, and export estimates with their provenance.

The package extracts the discovery patterns developed in
[gov_privacy](https://github.com/themains/gov_privacy). It ships 170 research
heuristics covering 162 country labels and selected CISA and Govdirectory lists.
The bundled lists are dated source snapshots, not a complete global population.
The rules have not been independently validated as a classifier. A positive
result is an inference; a pattern match does not verify ownership, existence,
or current use. A missing match means unknown.

## Install

Python 3.12 or newer. Until a PyPI release is published:

```sh
pip install 'govdomains[data] @ git+https://github.com/themains/govdomains.git'
```

There is no implicit network access during import or classification. Fetching
source lists and querying Common Crawl are explicit operations. No model,
browser, paid API, or separate dataset download is required. The `data` extra
installs PyArrow to read the bundled Parquet tables. Omit the extra when using
only patterns, local CSV imports, and network collection.

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

`load_bundled()` selects the latest **shipped** CISA and Govdirectory snapshots.
It does not fetch updates. `Classifier()` by itself continues to use patterns
only; pass the snapshot's evidence to include the lists.

| Bundle | Unique listed hostnames | Observation date | Default |
|---|---:|---|---|
| `cisa` | 17,025 | 2026-11-06 UTC retrieval | Yes |
| `govdirectory` | 12,787 | 2026-11-06 UTC collection | Yes |
| `cisa_research` | 12,047 | Unknown, retained from gov_privacy | No |
| `govdirectory_research` | 9,696 | Unknown, retained from gov_privacy | No |

The Govdirectory snapshot covers the 46 jurisdiction pages published by its
index, including the European Union. This is source coverage, not a claim that
every government body in those jurisdictions is represented. Website addresses,
institution names, source categories, entity links, and source update dates are
retained where supplied. Government tiers are not harmonized across sources.

```sh
govdomains bundled
govdomains bundled --output lists.json
govdomains bundled govdirectory_research --output research.json
govdomains classify www.bundeskanzleramt.gv.at --bundled govdirectory
govdomains export lists.json --label government --output hosts.csv
```

Select one or more named snapshots with `load_bundled("govdirectory")` or
`load_bundled("cisa_research", "govdirectory_research")`. Research extracts are
never silently mixed into the default selection. Their unknown dates remain
unknown, so they cannot establish a dated historical inference. A retrieval
date does not establish that every entry was current on that date.

`snapshot.hostnames` includes all listed candidate hosts, including page-scoped
observations. Classification/export can narrow this to inferred government
hosts. Page-only evidence does not establish affiliation for the entire host,
and exact-host list evidence does not propagate to its subdomains.

The four normalized tables occupy about 1.9 MB before wheel compression. Each
has a declared Arrow schema, counts, SHA-256 checksum, upstream provenance, and
CC0 license attribution. Raw downloaded responses are preserved in the
repository's `data/raw/`, outside the wheel. See [data documentation](https://themains.github.io/govdomains/data.html)
for source scope, historical comparisons, and the fetch/build commands.

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
recognize likely positives and abstain elsewhere. Contrary list/review evidence
produces `unknown` with `reason="conflicting_evidence"`; absence from a list
never produces a negative. Results expose the matched rules, supporting source
records, dates, and original source categories. They do not assign invented
probabilities or universal administrative levels.

```sh
govdomains classify agency.gov agency.gov.example.org
govdomains classify --file hosts.txt --snapshot sources.json
govdomains rules --country 'India'
```

The unit is a **hostname**, including subdomains. URLs are accepted as inputs,
but paths are ignored and this is reported. A government page on a commercial
platform cannot establish that the whole platform is governmental. Exact list
evidence does not propagate to parent names, siblings, or child names.

## Collect and combine sources

```sh
govdomains fetch cisa --output cisa.json
govdomains fetch gsa --output gsa.json

govdomains discover --suffix gov --index CC-MAIN-2024-30 \
  --max-pages 1 --checkpoint cc-progress.json --output cc-sample.json

govdomains merge cisa.json gsa.json cc-sample.json --output sources.json
govdomains export sources.json --label government --output hosts.csv
```

`fetch` retrieves the current CISA `.gov` or GSA nonstandard-domain list and
records the retrieval observation date, content hash, and import counts. These
lists have different scopes, can be stale, and are not guaranteed complete.
Source membership contributes an inference, not an ownership certificate.

`discover` searches one Common Crawl index and suffix. The default reads **one
page**. Use `--all-pages` to traverse every reported page; large namespaces may
take substantial time. Requests are serial, delayed, and retry transient HTTP
failures. Completed pages are checkpointed; rerunning the same query resumes
from the last completed page. `--max-pages` is the total budget, including pages
already checkpointed. The checkpoint must not be shared between queries.

Collection streams URL records into unique-host summaries. It preserves first
and last capture timestamps without saving the URLs or page bodies. Failures
raise errors and do not overwrite the final output. `query_complete` means all
reported pages of that query were read, **not** that all government hosts were
found. Common Crawl observations have an unknown affiliation label until other
evidence or rules contribute a classification.

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

Formats: `cisa`, `gsa`, `india`, `govdirectory`, and `generic`. Generic CSV expects
a `hostname` column; use `--column` and `--delimiter` for other tables. Import
preserves selected institutional attributes, counts missing/invalid values,
rejects incompatible schemas, and treats non-root URL listings as page-scoped
evidence. Page-scoped evidence alone does not label a host government.
Undated files stay undated. No date is inferred from the filename or Git history.

To reuse a notebook-exported Common Crawl CSV without retaining URL rows:

```sh
govdomains import-crawl common_crawl_sample_n1000.csv \
  --source CC-MAIN-2024-30-sample --output crawl.json
```

This streams the `url` and `timestamp` columns into unique-host observations,
preserves capture-date bounds, and records the input file hash. It treats crawl
rows as discovery observations, not government labels.

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

Merging snapshots unions observations. It does **not** reconstruct changing
registry membership: an older positive can persist, and contrary observations
can conflict. Keep separate source snapshots when comparing periods. Crawl
first/last timestamps summarize observations, not an ownership interval.

## Files and reproducibility

Snapshots are portable JSON with a schema version and SHA-256 integrity check.
They contain evidence and source metadata. Saving uses an atomic replacement;
corrupt snapshots are rejected. Repeated identical evidence is deduplicated.

CSV export creates one row per normalized observed hostname, with evidence and
matched rules encoded as JSON columns. A companion `.manifest.json` records the
input snapshot and rule hashes, filters, counts, source metadata, and CSV hash.
Hostnames, subdomains, and `www` aliases are not silently collapsed into one
institution. All exported populations have unknown completeness.

Selected CISA and Govdirectory source lists are bundled under CC0-1.0; their
manifest records input hashes, source URLs, dates, and row accounting. The
loader checks the Parquet checksum, schema, dates, required values, uniqueness,
and counts before returning evidence. The code remains Apache-2.0 licensed.
No crawl URL inventory or website content corpus is shipped. Source data keeps
its own license and redistribution conditions. India and GSA imports remain
available, but their lists are not included in this first bundle.

## Development

```sh
uv sync --all-groups
make ci
make ci-docker
```

`make ci` runs Ruff, Pyright, docstring checks, tests, Sphinx with Furo,
and distribution validation. `make check` runs the full preen conformance check. Tests block network access and exercise installed-package behavior,
normalization, conflicts, historical filtering, source parsing, CLI roundtrips,
streaming collection, pagination, checkpoints, failure recovery, bundled data
integrity, and parsing of archived Govdirectory pages.

Docker CI uses the standard `python:3.14-slim` image; override `PYTHON_IMAGE` to
test another supported version. GitHub CI tests Python 3.12 and 3.14 through py-canon’s shared workflow.

## Scope and next validation

This is an alpha implementation, not a benchmarked government classifier.
The next measurement task is independent annotation across jurisdictions,
languages, conventional and nonstandard namespaces, shared hosts, and ambiguous
public bodies. Evaluate pattern-only, list-only, and combined inference
separately from candidate-discovery coverage.

Content-model integration (including piedomains), automatic political-level
inference, and a maintained global dataset are not implemented. They should be
added only after their contribution and maintenance costs are measured.

See [changelog](https://themains.github.io/govdomains/changelog.html) for development history. Code is licensed
under Apache-2.0.
