"""Redaction helpers for public_mode.

When ``public_mode`` is enabled we never expose full peer IP addresses or
destination hashes on the public NomadNet page. In operator mode the raw
values are preserved so a local operator can see full detail.

A consent allowlist (mapping full hash -> friendly label) lets specific nodes
opt in to having their full hash and a friendly name shown even on the public
page. This is how we expose paths between known, consenting nodes (e.g.
rns.chicagooffline.com, home, bowmanville) while still redacting everyone else.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Dict, Optional


def anonymize_ip(value: str, public_mode: bool) -> str:
    """Truncate an IP address when in public mode.

    IPv4 -> first two octets retained ("203.0.x.x").
    IPv6 -> first two hextets retained ("2001:db8:…").
    Non-IP strings are passed through hash truncation as a fallback.
    """
    if not public_mode or not value:
        return value

    host = value
    port = ""
    # Split an optional :port suffix for IPv4 / hostname.
    if value.count(":") == 1 and "." in value:
        host, port = value.rsplit(":", 1)

    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return anonymize_hash(value, public_mode)

    if ip.version == 4:
        octets = host.split(".")
        host = f"{octets[0]}.{octets[1]}.x.x"
    else:
        groups = host.strip("[]").split(":")
        kept = [g for g in groups if g][:2]
        host = ":".join(kept) + ":…"

    return f"{host}:{port}" if port else host


_HASH_RE = re.compile(r"^[0-9a-fA-F]{8,}$")


def _match_consent(value: str, consented: Optional[Dict[str, str]]) -> Optional[str]:
    """Return the canonical consented hash if ``value`` matches one, else None.

    Matching is case-insensitive and tolerant of an entered prefix: a configured
    hash matches when either side is a prefix of the other (>= 8 hex chars).
    """
    if not consented or not value:
        return None
    candidate = value.strip().lower()
    if candidate in consented:
        return candidate
    for full in consented:
        if len(candidate) >= 8 and (full.startswith(candidate) or candidate.startswith(full)):
            return full
    return None


def is_consented(value: str, consented: Optional[Dict[str, str]]) -> bool:
    return _match_consent(value, consented) is not None


def consent_label(value: str, consented: Optional[Dict[str, str]]) -> Optional[str]:
    """Friendly label for a consented hash, or None."""
    full = _match_consent(value, consented)
    return consented.get(full) if full else None


def anonymize_hash(
    value: str,
    public_mode: bool,
    keep: int = 8,
    consented: Optional[Dict[str, str]] = None,
) -> str:
    """Truncate a Reticulum/destination hash to ``keep`` hex chars in public mode.

    Hashes on the consent allowlist are always shown in full, regardless of
    public_mode, since their operators opted in.
    """
    if is_consented(value, consented):
        return value.strip().lower()
    if not public_mode or not value:
        return value
    candidate = value.strip()
    if _HASH_RE.match(candidate) and len(candidate) > keep:
        return candidate[:keep] + "…"
    return value


def maybe_redact_endpoint(endpoint: str, public_mode: bool) -> str:
    """Redact an 'ip:port' or 'host:port' endpoint for public display."""
    return anonymize_ip(endpoint, public_mode)


def redact_optional(value: Optional[str], public_mode: bool) -> Optional[str]:
    if value is None:
        return None
    return anonymize_hash(value, public_mode)
