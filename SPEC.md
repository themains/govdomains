# govdomains implementation specification

The package combines name-pattern inference, source-list evidence, and hostname discovery. It ships the notebook-derived rule set, selected offline source snapshots, and tools to collect or import evidence. Source snapshots do not constitute a maintained global population.

## Public operations

- `Classifier` combines scoped name rules with exact-host evidence. Results preserve methods, dates, original source categories, and conflicts. Unsupported inputs abstain.
- `import_list` reads saved CISA, GSA, Indian-directory, Govdirectory, or generic CSV/TSV files. URL paths are page-scoped and cannot establish host-level affiliation.
- `fetch_list` explicitly retrieves current CISA or GSA data. The observation date is the retrieval date, not a claimed registration date.
- `import_crawl_csv` streams notebook-exported crawl observations into dated unique-host summaries.
- `CommonCrawl.collect` collects unique hostnames for a suffix in a selected index. The default is one page; complete traversal is explicit. Checkpoints resume completed pages, and failures do not become successful empty results.
- `Snapshot` saves checksummed evidence, unions observations, and exports unique-host estimates with a manifest.
- `bundled_sources()` describes the offline list catalog without importing PyArrow. `load_bundled(*names)` validates and loads selected Parquet snapshots. Its default selection uses the latest shipped CISA and Govdirectory lists; undated research extracts require explicit selection. `Classifier` receives their evidence explicitly.

The README is the user guide and the source for API examples. CLI commands mirror these operations. No query imports a network dependency's data or performs implicit discovery.

## Meaning of the output

The labels are `government`, `not_government`, and `unknown`. The shipped rules are research heuristics, not independently evaluated certificates of government ownership. A domain matching a pattern may not exist. List membership is a fallible inference signal. Evidence absence is not a negative label. Conflicts abstain.

A hostname is the unit. Preserve subdomains and aliases; do not claim host counts are organization or website counts. A government page on a commercial host does not classify its parent platform. Source-list evidence applies to the exact hostname only. Domain-pattern subtree rules are explicit and can have more specific exceptions.

There is no universal political hierarchy or inferred government level. Source categories are preserved without inventing equivalences across jurisdictions. There is no calibrated probability unless a future target-specific model is evaluated.

## Dates and history

Explicit `as_of` queries exclude later and undated observations. Undated name rules are excluded unless the caller requests extrapolation, which is marked in the result. User rules can specify effective intervals. Without `as_of`, evaluation uses the current UTC date and records it; undated evidence and heuristics remain available.

A historical result describes supported inferences from observations available through a date. It does not reconstruct domain ownership, continuous government use, or complete registry membership. A merged snapshot unions observations; it does not interpret missing rows as deletion events. Keep dated snapshots separate when comparing source membership.

## Distribution and validation

Package code and rules are independently usable offline. Bundled list tables use explicit Arrow schemas and a validated JSON catalog with hashes, counts, license attribution, source URLs, and observation-date meaning. The optional `data` extra supplies PyArrow. Source-specific attributes preserve original website addresses and institutional labels without imposing a global taxonomy.

Raw source responses and the input catalog live under `data/raw/`; the offline builder reads only those archives and writes `src/govdomains/data/bundled/`. Fetching and building are separate commands. Current collection can resume from verified archived responses; failures never silently produce an empty successful bundle. Older research extracts retain unknown dates. Only normalized CC0 CISA/Govdirectory tables and their manifest/license ship in the wheel. No crawl URL inventory, page content corpus, screenshot corpus, or paid model run is included.

Validation covers parsing, IDNA, label boundaries, exact/subtree matching, source schemas, shared-host evidence, conflicts, historical leakage, streaming deduplication, retries, pagination, checkpoint integrity, deterministic exports, installed wheels, and CLI error handling. Local checks include Black, isort, flake8, pytest, build/twine validation, and Docker CI. CI exercises Python 3.11–3.14.

Independent affiliation accuracy and discovery completeness remain unmeasured. Further work should benchmark pattern-only, list-only, and combined estimates against independently reviewed examples before integrating content-model predictions or committing to a global dataset.
