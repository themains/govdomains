"""Transparent classification from name rules and dated host evidence."""

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timezone
from importlib.resources import files
from typing import Iterable

from .normalize import has_page_path, normalize_hostname

LABELS = {"government", "not_government", "unknown"}


def validate_date(value: str | None) -> str | None:
    if value is not None:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError("Dates must use YYYY-MM-DD")
    return value


@dataclass(frozen=True)
class Rule:
    suffix: str
    country: str | None = None
    scope: str = "subtree"
    label: str = "government"
    source: str = "user"
    basis: str = "user_rule"
    valid_from: str | None = None
    valid_to: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "suffix", normalize_hostname(self.suffix))
        if self.scope not in {"exact", "subtree"} or self.label not in LABELS:
            raise ValueError("Invalid rule scope or label")
        validate_date(self.valid_from)
        validate_date(self.valid_to)
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValueError("Rule interval must have a start before its exclusive end")

    def matches(self, hostname: str) -> bool:
        return hostname == self.suffix or (
            self.scope == "subtree" and hostname.endswith("." + self.suffix)
        )


@dataclass(frozen=True)
class Evidence:
    hostname: str
    source: str
    method: str = "list"
    label: str = "government"
    observed_on: str | None = None
    scope: str = "exact"
    attributes: dict = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "hostname", normalize_hostname(self.hostname))
        if self.label not in LABELS or self.scope not in {"exact", "page"}:
            raise ValueError("Invalid evidence label or scope")
        if not self.source or self.method not in {"list", "crawl", "review", "content"}:
            raise ValueError("Evidence requires a source and a supported method")
        validate_date(self.observed_on)
        json.dumps(self.attributes, allow_nan=False)


@dataclass(frozen=True)
class Result:
    hostname: str | None
    label: str
    status: str
    reason: str
    rules: tuple[Rule, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    path_ignored: bool = False
    historical_extrapolation: bool = False
    evaluated_on: str | None = None

    @property
    def methods(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                ({"pattern"} if self.rules else set())
                | {
                    e.method
                    for e in self.evidence
                    if e.scope == "exact" and e.label != "unknown"
                }
            )
        )

    def to_dict(self) -> dict:
        return {**asdict(self), "methods": list(self.methods)}


def load_rules() -> tuple[Rule, ...]:
    """Load the notebook-derived heuristic rules bundled with the package."""
    data = json.loads(
        files("govdomains").joinpath("data/rules.json").read_text(encoding="utf-8")
    )
    return tuple(Rule(**record) for record in data["rules"])


class Classifier:
    """Classify offline. List evidence applies to exact hosts, never descendants.

    ``as_of`` filters evidence observations, not ownership intervals. Undated
    rules are excluded from historical queries unless explicitly opted in.
    """

    def __init__(
        self, evidence: Iterable[Evidence] = (), *, rules: Iterable[Rule] | None = None
    ):
        self.rules = tuple(load_rules() if rules is None else rules)
        self._evidence: dict[str, list[Evidence]] = defaultdict(list)
        for item in evidence:
            self._evidence[item.hostname].append(item)

    def classify_one(
        self,
        value: str,
        *,
        as_of: str | None = None,
        allow_undated_rules: bool = False,
    ) -> Result:
        validate_date(as_of)
        cutoff = as_of or datetime.now(timezone.utc).date().isoformat()
        try:
            host = normalize_hostname(value)
            path_ignored = has_page_path(value)
        except (ValueError, TypeError):
            return Result(None, "unknown", "error", "invalid_input")
        matches = [
            r
            for r in self.rules
            if r.matches(host)
            and (
                (not as_of or r.valid_from is not None or allow_undated_rules)
                and (r.valid_from is None or r.valid_from <= cutoff)
                and (r.valid_to is None or cutoff < r.valid_to)
            )
        ]
        if matches:
            longest = max(len(r.suffix.split(".")) for r in matches)
            matches = [r for r in matches if len(r.suffix.split(".")) == longest]
        evidence = tuple(
            e
            for e in self._evidence.get(host, ())
            if (
                (not as_of and e.observed_on is None)
                or (e.observed_on is not None and e.observed_on <= cutoff)
            )
        )
        if as_of:
            evidence = tuple(
                (
                    replace(
                        e,
                        attributes={
                            k: v for k, v in e.attributes.items() if k != "last_capture"
                        },
                    )
                    if e.method == "crawl"
                    and e.attributes.get("last_capture", "")[:8]
                    > as_of.replace("-", "")
                    else e
                )
                for e in evidence
            )
        labels = {r.label for r in matches} | {
            e.label for e in evidence if e.scope == "exact"
        }
        labels.discard("unknown")
        conflict = len(labels) > 1
        label = next(iter(labels)) if len(labels) == 1 else "unknown"
        return Result(
            host,
            label,
            "ok",
            (
                "conflicting_evidence"
                if conflict
                else "matched" if labels else "no_signal"
            ),
            tuple(matches),
            evidence,
            path_ignored,
            bool(as_of and any(r.valid_from is None for r in matches)),
            cutoff,
        )

    def classify(self, values: Iterable[str], **kwargs) -> list[Result]:
        if isinstance(values, str):
            raise TypeError("Pass an iterable of hostnames, or use classify_one")
        return [self.classify_one(value, **kwargs) for value in values]
