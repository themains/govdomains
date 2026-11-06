# Changelog

## Unreleased

- Bundle current CISA/Govdirectory snapshots and separately selectable undated research extracts as validated Parquet tables.
- Add offline Python and CLI list loading, with provenance, scope, hashes, counts, and source licenses.
- Archive current Govdirectory jurisdiction pages and pinned CISA CSV responses; rebuild tables offline from raw archives.
- Preserve original source website addresses, Govdirectory entity links, source update dates, and CISA city names.
- Extract 170 notebook-derived hostname patterns with explicit heuristic provenance.
- Add offline classification with source evidence, abstention, conflicts, and date filters.
- Import CISA, GSA, Indian-directory, Govdirectory, and custom CSV/TSV files.
- Fetch current CISA and GSA lists explicitly.
- Collect unique Common Crawl hosts with pagination, request retries, and checkpoints.
- Save integrity-checked evidence snapshots and export hostname estimates with manifests.
- Add local and Docker checks plus CI across Python 3.11–3.14.
