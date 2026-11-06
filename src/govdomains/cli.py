"""Command-line classification, collection, and evidence export."""

import argparse
import json
import sys
from pathlib import Path

import requests

from .core import Classifier, load_rules
from .crawl import CommonCrawl, import_crawl_csv
from .snapshot import Snapshot
from .sources import FORMATS, SOURCES, fetch_list, import_list


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    classify = commands.add_parser("classify", help="Classify supplied hosts offline")
    classify.add_argument("hosts", nargs="*")
    classify.add_argument("--file", type=Path)
    classify.add_argument("--snapshot", type=Path)
    classify.add_argument("--as-of")
    classify.add_argument("--allow-undated-rules", action="store_true")
    rules = commands.add_parser("rules", help="List the bundled discovery rules")
    rules.add_argument("--country")
    fetch = commands.add_parser("fetch", help="Fetch a current source list explicitly")
    fetch.add_argument("source", choices=sorted(SOURCES))
    fetch.add_argument("--output", required=True, type=Path)
    imp = commands.add_parser("import-list", help="Import a saved CSV or TSV")
    imp.add_argument("path", type=Path)
    imp.add_argument("--format", choices=sorted(FORMATS), default="generic")
    imp.add_argument("--source", required=True)
    imp.add_argument("--date")
    imp.add_argument("--column")
    imp.add_argument("--delimiter")
    imp.add_argument("--output", required=True, type=Path)
    imported_crawl = commands.add_parser(
        "import-crawl", help="Collapse a saved CDX CSV"
    )
    imported_crawl.add_argument("path", type=Path)
    imported_crawl.add_argument("--source", required=True)
    imported_crawl.add_argument("--output", required=True, type=Path)
    discover = commands.add_parser("discover", help="Collect unique Common Crawl hosts")
    discover.add_argument("--suffix", required=True)
    discover.add_argument("--index", required=True)
    budget = discover.add_mutually_exclusive_group()
    budget.add_argument("--max-pages", type=int, default=1)
    budget.add_argument("--all-pages", action="store_true")
    discover.add_argument("--checkpoint", type=Path)
    discover.add_argument("--output", required=True, type=Path)
    merge = commands.add_parser("merge", help="Union evidence snapshots")
    merge.add_argument("snapshots", type=Path, nargs="+")
    merge.add_argument("--output", type=Path, required=True)
    export = commands.add_parser(
        "export", help="Export unique-host estimates and manifest"
    )
    export.add_argument("snapshot", type=Path)
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--label", choices=["government", "not_government", "unknown"])
    export.add_argument("--as-of")
    export.add_argument("--allow-undated-rules", action="store_true")
    return root


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "classify":
            values = args.hosts + (
                args.file.read_text().splitlines() if args.file else []
            )
            if not values:
                raise ValueError("Supply hosts or --file")
            evidence = Snapshot.load(args.snapshot).evidence if args.snapshot else ()
            results = Classifier(evidence).classify(
                values, as_of=args.as_of, allow_undated_rules=args.allow_undated_rules
            )
            for result in results:
                print(json.dumps(result.to_dict(), ensure_ascii=False))
            return int(any(result.status == "error" for result in results))
        if args.command == "rules":
            from dataclasses import asdict

            for rule in load_rules():
                if not args.country or (
                    rule.country and rule.country.casefold() == args.country.casefold()
                ):
                    print(json.dumps(asdict(rule), ensure_ascii=False))
            return 0
        if args.command == "export":
            report = Snapshot.load(args.snapshot).export_csv(
                args.output,
                label=args.label,
                as_of=args.as_of,
                allow_undated_rules=args.allow_undated_rules,
            )
        else:
            if args.command == "fetch":
                snapshot = fetch_list(args.source)
            elif args.command == "import-crawl":
                snapshot = import_crawl_csv(args.path, source=args.source)
            elif args.command == "import-list":
                snapshot = import_list(
                    args.path,
                    source=args.source,
                    format=args.format,
                    observed_on=args.date,
                    column=args.column,
                    delimiter=args.delimiter,
                )
            elif args.command == "discover":
                with CommonCrawl(args.index) as client:
                    snapshot = client.collect(
                        args.suffix,
                        max_pages=None if args.all_pages else args.max_pages,
                        checkpoint=args.checkpoint,
                    )
            else:
                snapshot = Snapshot.merge(*(Snapshot.load(p) for p in args.snapshots))
            snapshot.save(args.output)
            report = {"hosts": len(snapshot.hostnames), "metadata": snapshot.metadata}
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 0
    except (ValueError, KeyError, TypeError, OSError, requests.RequestException) as exc:
        print(f"govdomains: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
