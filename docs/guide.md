# Work with bundled government-domain lists

This workflow runs offline with the `data` extra installed. These examples
are executed by Sphinx's doctest builder during local checks and documentation CI.

## Choose the source snapshots

Inspect the catalog before combining observations. The names ending in
`_research` identify the original undated extracts; the other two identify
the latest shipped snapshots, whose retrieval dates are in the catalog.

```{doctest}
>>> from govdomains import Classifier, Snapshot, bundled_sources, load_bundled
>>> sorted(bundled_sources())
['cisa', 'cisa_research', 'govdirectory', 'govdirectory_research']
>>> snapshot = load_bundled()
>>> len(snapshot.hostnames)
29800
```

These are candidate hostnames, including subdomains and page-scoped listings.
Loading a bundle never contacts a source website or silently updates the data.

## Classify with the source evidence

Austria's Federal Chancellery illustrates the contribution of list evidence:
its hostname falls outside the package's default namespace patterns.

```{doctest}
>>> host = "www.bundeskanzleramt.gv.at"
>>> Classifier().classify_one(host).label
'unknown'
>>> classifier = Classifier(snapshot.evidence)
>>> result = classifier.classify_one(host)
>>> result.label, result.methods
('government', ('list',))
>>> any(e.attributes.get("Govdirectory URL") for e in result.evidence)
True
```

The result is an inference from source membership. It does not independently
verify ownership or current use. Evidence for an exact host does not classify
its subdomains, and a listing of a page on a shared platform does not classify
the entire platform.

## Preserve the snapshot you used

Saving captures the observations and source metadata. Loading verifies the
snapshot's checksum; later source updates do not change the saved result.

```{doctest}
>>> from pathlib import Path
>>> from tempfile import TemporaryDirectory
>>> with TemporaryDirectory() as directory:
...     path = Path(directory) / "sources.json"
...     snapshot.save(path)
...     restored = Snapshot.load(path)
...     print(restored.sha256 == snapshot.sha256)
True
```

Use `snapshot.export_csv("hosts.csv", label="government")` to export inferred
government hostnames with a companion manifest. An unfiltered export retains
unknown classifications as well.

## Be explicit about historical limits

The research extract has no known observation date. Its membership can support
an undated inference, but cannot establish what was known by a historical date.

```{doctest}
>>> research = load_bundled("govdirectory_research")
>>> classifier = Classifier(research.evidence, rules=())
>>> classifier.classify_one(host).label
'government'
>>> classifier.classify_one(host, as_of="2024-07-26").label
'unknown'
```

For dated sources, `as_of` filters observations through the requested date.
It does not reconstruct continuous government ownership or infer removal from
the absence of a hostname in a later list. Consult the [data documentation](data.md)
for source dates, membership changes, licenses, and reproducible update commands.
