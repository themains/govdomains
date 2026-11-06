"""Government hostname inference and evidence collection."""

from importlib.metadata import version

from .bundled import bundled_sources, load_bundled
from .core import Classifier, Evidence, Result, Rule, load_rules
from .normalize import normalize_hostname
from .snapshot import Snapshot

__all__ = [
    "Classifier",
    "Evidence",
    "Result",
    "Rule",
    "Snapshot",
    "bundled_sources",
    "load_bundled",
    "load_rules",
    "normalize_hostname",
]

__version__ = version("govdomains")
