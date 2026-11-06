# Bundled source lists

The wheel contains normalized Parquet observations and their manifest in
`src/govdomains/data/bundled/`. Raw response bodies and the build input catalog
live here in `data/raw/`, outside the wheel. Parsing/building never requires
network access. The raw archives occupy about 1.6 MB compressed; the four
normalized tables occupy about 1.9 MB.

| Snapshot | Source rows | Empty addresses | Rejected addresses | Unique hostnames |
|---|---:|---:|---:|---:|
| CISA, retrieved 2026-11-06 | 17,025 | 0 | 0 | 17,025 |
| Govdirectory, collected 2026-11-06 | 20,107 | 5,700 | 6 | 12,787 |
| CISA research extract, date unknown | 12,047 | 0 | 0 | 12,047 |
| Govdirectory research extract, date unknown | 12,255 | 1,875 | 0 | 9,696 |

Govdirectory's published index enumerates 46 jurisdiction pages, all of which
were archived and parsed. Its pages report a source update date of 2026-09-25;
the collection date is later and is recorded separately. The older extract
covers 34 source labels. The updated list shares 9,368 hostnames with that
extract, adds 3,419, and does not contain 328 of its hostnames. These are changes
in source membership, not established government adoption or abandonment dates.
The package does not union the older extract into the default snapshot.

The default CISA/Govdirectory union has 29,800 listed candidate hostnames;
29,450 receive a government inference when combined with the bundled patterns.
The rest have only page-scoped positive observations outside the matching rules.
These are hostname counts, not counts of government organizations. Aliases and
subdomains remain distinct. Source completeness and independent affiliation
accuracy are unknown.

## Source provenance and licenses

- **CISA:** [dotgov-data](https://github.com/cisagov/dotgov-data), under its
  explicit [CC0 license](https://github.com/cisagov/dotgov-data/blob/main/LICENSE).
  Fetching resolves the upstream Git commit first and downloads the CSV and
  license at that immutable revision. The raw body retains the original CSV;
  normalized tables omit security-contact email fields and retain institutional
  name, source domain type, agency, city, and state where present.
- **Govdirectory:** [country index](https://www.govdirectory.org/countries/),
  with [CC0 data terms](https://www.govdirectory.org/about/). The site's download
  button constructs a TSV in JavaScript from each agency table. The parser reads
  those same fields from archived HTML, preserving every website link if a row
  has several. It retains name, raw type, source jurisdiction label, Govdirectory
  entity link, original website address, and reported source update date.
- **Research extracts:** the CISA and combined Govdirectory files from
  [gov_privacy](https://github.com/themains/gov_privacy), pinned to the Git commit
  recorded in `data/raw/catalog.json`. The source observation dates are unknown.
  Neither the Git commit time nor today's import time is substituted for them.

The current Govdirectory index also includes India and the European Union.
This does not replace the much larger NIC India directory used in gov_privacy.
That directory's [website policy](https://igod.gov.in/website_policies) requires
permission for reproduction, so it is not redistributed here. GSA is also left
out of this first explicitly CC0 bundle. Existing GSA and India import support
is unchanged. No crawl URL corpus is included.

## Data layout and schema

```text
data/
  raw/
    catalog.json
    2026-11-06/cisa/*.jsonl.gz
    2026-11-06/govdirectory/*.jsonl.gz
    research/*.jsonl.gz
src/govdomains/data/bundled/
  manifest.json
  cisa.parquet
  govdirectory.parquet
  cisa_research.parquet
  govdirectory_research.parquet
  CC0-1.0.txt
scripts/update_bundles.py
```

Each raw archive is a gzip-compressed JSON line containing the original UTF-8
body, its SHA-256, URL, retrieval timestamp, HTTP status and selected response
headers. Research archives record their pinned source URL and a null retrieval
timestamp. Successful archives are checksum-verified on resume. Failed requests
are not treated as completed sources. The input catalog is promoted only after
the entire fetch succeeds. Existing raw collection folders remain available
when a later collection becomes the build input.

The table schema is defined by `govdomains.bundled.evidence_schema()` and tested
against the installed data. Schema version 1 has:

| Field | Arrow type | Null allowed | Meaning |
|---|---|---|---|
| `hostname` | string | No | Normalized IDNA hostname, preserving subdomains |
| `source` | string | No | Immutable CSV URL or Govdirectory jurisdiction-page URL |
| `observed_on` | date32 | Yes | Retrieval/collection observation; null for undated extracts |
| `scope` | string | No | `exact` or `page`; never implicitly a subtree |
| `attributes` | map<string, string> | No | Original source fields, website address, bundle ID, raw archive path |

Each row is a source-list observation with label `government`, not a verified
ownership certificate. Multiple observations for a hostname remain separate
when their provenance or attributes differ. Exact duplicate evidence is
deduplicated. The manifest declares table hashes, observation dates, licenses,
input hashes, row counts, unique-host counts, and input-row accounting. Raw
source labels are preserved without creating a universal government hierarchy.

## Refresh and rebuild

From the repository root:

```sh
pip install -e '.[dev]'
python scripts/update_bundles.py fetch --collection 2026-11-06
python scripts/update_bundles.py import-research ../gov_privacy
python scripts/update_bundles.py build
make ci
```

Use a new collection folder for a fresh retrieval. Reusing a collection resumes
its verified archives, including its pinned CISA revision; it does not pretend
that cached responses were fetched again. The research import is needed only
when initially preparing those extracts. A different research file is refused
instead of silently replacing the archived one. To reproduce the shipped
tables, run only `build` against the checked-in catalog and raw archives.

Requests are serial with a short delay, verified TLS, timeouts, and the package's
retry policy. A failed collection can be resumed; it is not published as an empty
list. Unexpected page structure fails parsing. Missing website fields and invalid
hostnames are counted separately. Govdirectory's six rejected address rows are
localized to Austria (4), Russia (1), and Switzerland (1); their original values
remain in the archived source pages. Non-root website addresses keep page scope,
so shared platforms are not automatically classified as government hosts.

Publication is deliberate: review the catalog, rejected counts, membership
changes, licenses, and tests before committing a refreshed bundle. There is no
scheduled data replacement or hidden network access when a user loads a bundle.
