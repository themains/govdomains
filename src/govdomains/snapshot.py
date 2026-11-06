"""Portable evidence snapshots and unique-host estimates."""

import csv
import hashlib
import io
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from .core import Classifier, Evidence, validate_date


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def atomic_write(path: str | Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            name = handle.name
            handle.write(text)
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


@dataclass
class Snapshot:
    evidence: tuple[Evidence, ...]
    metadata: dict

    def __post_init__(self):
        unique = {canonical(asdict(e)): e for e in self.evidence}
        self.evidence = tuple(unique[k] for k in sorted(unique))

    @property
    def hostnames(self) -> tuple[str, ...]:
        return tuple(sorted({e.hostname for e in self.evidence}))

    def _payload(self) -> dict:
        return {
            "schema_version": 1,
            "evidence": [asdict(e) for e in self.evidence],
            "metadata": self.metadata,
        }

    @property
    def sha256(self) -> str:
        return digest(self._payload())

    def save(self, path: str | Path) -> None:
        payload = self._payload()
        atomic_write(path, canonical({**payload, "sha256": digest(payload)}) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> "Snapshot":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        checksum = payload.pop("sha256")
        if payload.get("schema_version") != 1 or digest(payload) != checksum:
            raise ValueError("Unsupported schema or snapshot checksum mismatch")
        return cls(
            tuple(Evidence(**e) for e in payload["evidence"]), payload["metadata"]
        )

    @classmethod
    def merge(cls, *snapshots: "Snapshot") -> "Snapshot":
        """Union observations, not successive states of a complete registry."""
        return cls(
            tuple(e for s in snapshots for e in s.evidence),
            {
                "operation": "observation_union",
                "inputs": [
                    {"sha256": s.sha256, "metadata": s.metadata} for s in snapshots
                ],
                "population_completeness": "unknown",
            },
        )

    def export_csv(
        self,
        path: str | Path,
        *,
        label: str | None = None,
        as_of: str | None = None,
        allow_undated_rules: bool = False,
    ) -> dict:
        classifier = Classifier(self.evidence)
        validate_date(as_of)
        cutoff = as_of or datetime.now(timezone.utc).date().isoformat()
        hosts = sorted(
            {
                e.hostname
                for e in self.evidence
                if (e.observed_on is not None and e.observed_on <= cutoff)
                or (e.observed_on is None and not as_of)
            }
        )
        rows = classifier.classify(
            hosts, as_of=as_of, allow_undated_rules=allow_undated_rules
        )
        if label is not None and label not in {
            "government",
            "not_government",
            "unknown",
        }:
            raise ValueError("Invalid label filter")
        selected = [r for r in rows if label is None or r.label == label]
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "hostname",
                "label",
                "reason",
                "methods",
                "rule_matches",
                "evidence",
                "historical_extrapolation",
            ],
        )
        writer.writeheader()
        for row in selected:
            writer.writerow(
                {
                    "hostname": row.hostname,
                    "label": row.label,
                    "reason": row.reason,
                    "methods": canonical(row.methods),
                    "rule_matches": canonical([asdict(r) for r in row.rules]),
                    "evidence": canonical([asdict(e) for e in row.evidence]),
                    "historical_extrapolation": row.historical_extrapolation,
                }
            )
        content = stream.getvalue()
        manifest = {
            "software_version": version("govdomains"),
            "evaluated_on": cutoff,
            "snapshot_sha256": self.sha256,
            "source_metadata": self.metadata,
            "unit": "hostname",
            "candidate_hosts": len(rows),
            "exported_hosts": len(selected),
            "label": label,
            "as_of": as_of,
            "allow_undated_rules": allow_undated_rules,
            "rules_sha256": digest([asdict(r) for r in classifier.rules]),
            "csv_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "population_completeness": "unknown",
        }
        atomic_write(path, content)
        atomic_write(str(path) + ".manifest.json", canonical(manifest) + "\n")
        return manifest
