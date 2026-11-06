API reference
=============

Classification
--------------

.. autosummary::
   :toctree: api

   govdomains.Classifier
   govdomains.Rule
   govdomains.Evidence
   govdomains.Result
   govdomains.normalize_hostname
   govdomains.load_rules

Bundled lists and snapshots
--------------------------------

.. autosummary::
   :toctree: api

   govdomains.bundled_sources
   govdomains.load_bundled
   govdomains.Snapshot

Collection and imports
----------------------

.. autosummary::
   :toctree: api

   govdomains.sources.fetch_list
   govdomains.sources.import_list
   govdomains.sources.parse_list
   govdomains.crawl.CommonCrawl
   govdomains.crawl.import_crawl_csv
   govdomains.crawl.patterns_for
