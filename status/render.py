"""Render a snapshot dict into a NomadNet micron (.mu) page.

Rendering is isolated from collection so the snapshot contract can be reused by
other consumers (FastAPI, Prometheus, Grafana) that do not need micron output.

Jinja2 is used for the template. If Jinja2 is unavailable, a clear error is
raised so the operator knows to ``pip install jinja2``.
"""
from __future__ import annotations

import datetime as _dt
import os
from typing import Any, Dict

from .util import human_bytes, human_duration

# Micron color codes (backtick + F + 3 hex nibbles).
C_HEAD = "`F0cf"   # cyan headings
C_BODY = "`Ffff"   # white body
C_HL = "`Ffb3"     # amber highlight
C_DIM = "`F888"    # gray / muted
C_FOOT = "`F555"   # footer gray
C_GOOD = "`F0f0"   # green
C_WARN = "`Ffa0"   # amber
C_BAD = "`Ff00"    # red

TEMPLATE_NAME = "status.mu.j2"


def _dot(state: str) -> str:
    """Return a colored status marker that resets to body color after."""
    marker = {
        "ok": f"{C_GOOD}\u25cf{C_BODY}",
        "warn": f"{C_WARN}\u25cf{C_BODY}",
        "bad": f"{C_BAD}\u25cf{C_BODY}",
    }.get(state, f"{C_DIM}?{C_BODY}")
    return marker


def _bool_dot(value: Any) -> str:
    if value is True:
        return _dot("ok")
    if value is False:
        return _dot("bad")
    return _dot("warn")


def _fmt_time(unix: Any) -> str:
    if not unix:
        return "unknown"
    try:
        return _dt.datetime.fromtimestamp(int(unix), _dt.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%SZ"
        )
    except (ValueError, OverflowError, OSError):
        return "unknown"


def _build_environment():
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Jinja2 is required to render the status page. Install it with "
            "'pip install jinja2'."
        ) from exc

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.globals.update(
        {
            "C_HEAD": C_HEAD,
            "C_BODY": C_BODY,
            "C_HL": C_HL,
            "C_DIM": C_DIM,
            "C_FOOT": C_FOOT,
            "C_GOOD": C_GOOD,
            "C_WARN": C_WARN,
            "C_BAD": C_BAD,
            "dot": _dot,
            "bool_dot": _bool_dot,
            "fmt_time": _fmt_time,
        }
    )
    env.filters["hb"] = human_bytes
    env.filters["hd"] = human_duration
    return env


# Friendly labels + ordering for the interface section.
INTERFACE_LABELS = [
    ("tcp_server", "TCP Server"),
    ("tcp_client", "TCP Client"),
    ("auto", "AutoInterface"),
    ("rnode_lora", "RNode LoRa"),
    ("kiss_tnc", "KISS TNC"),
    ("serial", "Serial"),
    ("i2p", "I2P"),
    ("udp", "UDP"),
    ("other", "Other"),
    ("local", "Local"),
]


def render_page(snapshot: Dict[str, Any], config) -> str:
    """Render the snapshot into micron page text."""
    env = _build_environment()
    template = env.get_template(TEMPLATE_NAME)

    # Group interfaces by category for the template.
    grouped: Dict[str, list] = {}
    for iface in snapshot.get("interfaces", []):
        grouped.setdefault(iface.get("category", "other"), []).append(iface)

    interface_groups = [
        (label, grouped[cat]) for cat, label in INTERFACE_LABELS if cat in grouped
    ]

    return template.render(
        s=snapshot,
        cfg=config,
        interface_groups=interface_groups,
    )


def write_page(snapshot: Dict[str, Any], config) -> str:
    """Render and atomically write the .mu page. Returns the rendered text."""
    text = render_page(snapshot, config)
    out_path = config.page_output
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    tmp_path = f"{out_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(tmp_path, out_path)
    return text
