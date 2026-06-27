"""CLI entry point: collect -> store JSON -> render NomadNet page.

Usage:
    python3 -m status.generate [--config PATH] [--dry-run] [--print]

Designed to be invoked by a systemd timer once per minute. Exit code is 0 on
success even when individual collectors degrade (failures are recorded in the
snapshot ``errors`` list and surfaced on the page).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from .collectors import collect_snapshot
from .config import load_config
from .history import apply_history


def _write_json(snapshot: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, indent=2, sort_keys=False)
    os.replace(tmp, path)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="chioff-rns status generator")
    parser.add_argument("--config", help="Path to status config (INI).")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect and render but do not write JSON or the page.",
    )
    parser.add_argument(
        "--print",
        dest="print_page",
        action="store_true",
        help="Print the rendered page to stdout.",
    )
    parser.add_argument(
        "--json",
        dest="print_json",
        action="store_true",
        help="Print the snapshot JSON to stdout.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)

    snapshot = collect_snapshot(config)
    snapshot = apply_history(snapshot, config)

    if args.print_json:
        print(json.dumps(snapshot, indent=2))

    # Render the page (import here so --json works without Jinja2 installed).
    from .render import render_page, write_page

    if args.dry_run:
        text = render_page(snapshot, config)
        if args.print_page:
            print(text)
        return 0

    _write_json(snapshot, config.json_output)
    text = write_page(snapshot, config)

    if args.print_page:
        print(text)

    # Report degraded collectors to stderr for journald visibility.
    if snapshot.get("errors"):
        sys.stderr.write(
            "status: %d collector note(s): %s\n"
            % (len(snapshot["errors"]), "; ".join(snapshot["errors"]))
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
