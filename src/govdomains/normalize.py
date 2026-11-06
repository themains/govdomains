"""Normalize inputs without contacting DNS or a website."""

import ipaddress
import re
from urllib.parse import urlsplit

import idna


def normalize_hostname(value: str) -> str:
    """Return an IDNA hostname from a bare name or HTTP(S) URL.

    URL credentials are rejected, and IP addresses are not domain inputs.
    A path is ignored, never treated as evidence about its hosting domain.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected a nonempty hostname or HTTP(S) URL")
    value = value.strip()
    if any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        raise ValueError("Whitespace, controls, and backslashes are not allowed")
    parsed = urlsplit(
        value if "://" in value or value.startswith("//") else "//" + value
    )
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Only HTTP(S) URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not allowed")
    _ = parsed.port
    host = (parsed.hostname or "").removesuffix(".")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP addresses are not hostnames")
    try:
        host = idna.encode(host, uts46=True, std3_rules=True).decode("ascii").lower()
    except idna.IDNAError as exc:
        raise ValueError("Invalid IDNA hostname") from exc
    if len(host) > 253 or not re.search(r"[a-z]", host.rsplit(".", 1)[-1]):
        raise ValueError("Invalid hostname")
    return host


def has_page_path(value: str) -> bool:
    """Report whether an address identifies a path, query, or fragment."""
    parsed = urlsplit(
        value if "://" in value or value.startswith("//") else "//" + value
    )
    return bool(parsed.path.strip("/") or parsed.query or parsed.fragment)
