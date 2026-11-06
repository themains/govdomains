"""Government hostname inference and evidence collection."""

from .core import Classifier, Evidence, Result, Rule, load_rules
from .normalize import normalize_hostname
from .snapshot import Snapshot

__all__ = [
    "Classifier",
    "Evidence",
    "Result",
    "Rule",
    "Snapshot",
    "load_rules",
    "normalize_hostname",
]
