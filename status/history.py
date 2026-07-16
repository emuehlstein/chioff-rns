"""Optional SQLite history store.

Tracks just enough state across runs to answer the questions the status page
asks that a single point-in-time snapshot cannot:

* "new paths in the last hour"  -> path first-seen tracking
* "recent events"               -> derived + journal events, deduplicated
* historical snapshots          -> raw JSON archive for later FastAPI/Grafana use

The store is entirely optional; if disabled or unavailable the generator still
produces a page, just without history-derived fields.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS paths (
    hash        TEXT PRIMARY KEY,
    first_seen  INTEGER NOT NULL,
    last_seen   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    type        TEXT NOT NULL,
    detail      TEXT NOT NULL,
    dedupe_key  TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS snapshots (
    ts          INTEGER PRIMARY KEY,
    json        TEXT NOT NULL
);
"""


class History:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, timeout=10)
        self.conn.row_factory = sqlite3.Row
        # Incremental auto-vacuum lets us reclaim freed pages cheaply after
        # prunes without a full-file VACUUM (which needs ~2x disk + lots of
        # RAM to rewrite the whole DB). Only takes effect on a fresh file or
        # after a one-time full VACUUM, so we also VACUUM once if the DB is
        # still in the default (auto_vacuum=NONE) mode. Prevents the snapshot
        # blob table from ballooning the file unbounded (see 2026-07-15
        # incident: history.db grew to 14 GB and filled the disk).
        self.conn.execute("PRAGMA auto_vacuum=INCREMENTAL")
        mode = self.conn.execute("PRAGMA auto_vacuum").fetchone()
        self.conn.executescript(_SCHEMA)
        self.conn.commit()
        if mode is not None and int(mode[0]) == 0:
            # DB predates incremental auto-vacuum; convert it once. This full
            # VACUUM is only paid on the first run after this change ships.
            try:
                self.conn.execute("VACUUM")
                self.conn.commit()
            except sqlite3.Error:
                pass

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    # -- paths -----------------------------------------------------------
    def update_paths(self, hashes: List[str], now: Optional[int] = None) -> int:
        """Upsert observed path hashes; return count first seen in last hour."""
        now = now or int(time.time())
        cur = self.conn.cursor()
        for h in hashes:
            cur.execute(
                """
                INSERT INTO paths(hash, first_seen, last_seen)
                VALUES (?, ?, ?)
                ON CONFLICT(hash) DO UPDATE SET last_seen=excluded.last_seen
                """,
                (h, now, now),
            )
        self.conn.commit()
        cutoff = now - 3600
        row = cur.execute(
            "SELECT COUNT(*) AS c FROM paths WHERE first_seen >= ?", (cutoff,)
        ).fetchone()
        return int(row["c"]) if row else 0

    def prune_paths(self, retention_hours: int, now: Optional[int] = None) -> None:
        now = now or int(time.time())
        cutoff = now - retention_hours * 3600
        self.conn.execute("DELETE FROM paths WHERE last_seen < ?", (cutoff,))
        self.conn.commit()

    # -- events ----------------------------------------------------------
    def add_events(self, events: List[Dict[str, Any]]) -> None:
        cur = self.conn.cursor()
        for ev in events:
            ts = ev.get("unix") or int(time.time())
            etype = ev.get("type", "info")
            detail = ev.get("detail", "")
            dedupe = f"{ts}:{etype}:{detail}"
            try:
                cur.execute(
                    "INSERT OR IGNORE INTO events(ts, type, detail, dedupe_key) VALUES (?,?,?,?)",
                    (ts, etype, detail, dedupe),
                )
            except sqlite3.Error:
                continue
        self.conn.commit()

    def recent_events(self, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT ts, type, detail FROM events ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            {"unix": r["ts"], "type": r["type"], "detail": r["detail"]}
            for r in rows
        ]

    def prune_events(self, retention_hours: int, now: Optional[int] = None) -> None:
        now = now or int(time.time())
        cutoff = now - retention_hours * 3600
        self.conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
        self.conn.commit()

    # -- snapshot archive ------------------------------------------------
    def archive_snapshot(self, snapshot: Dict[str, Any]) -> None:
        ts = snapshot.get("generated_unix") or int(time.time())
        self.conn.execute(
            "INSERT OR REPLACE INTO snapshots(ts, json) VALUES (?, ?)",
            (ts, json.dumps(snapshot, separators=(",", ":"))),
        )
        self.conn.commit()

    def prune_snapshots(self, retention_hours: int, now: Optional[int] = None) -> None:
        now = now or int(time.time())
        cutoff = now - retention_hours * 3600
        self.conn.execute("DELETE FROM snapshots WHERE ts < ?", (cutoff,))
        self.conn.commit()

    # -- housekeeping ----------------------------------------------------
    def reclaim(self) -> None:
        """Return freed pages to the OS after prunes.

        With auto_vacuum=INCREMENTAL this is a cheap, bounded operation (it
        only touches the free-page list), unlike a full VACUUM. Keeps the
        file from growing without bound as snapshot blobs churn.
        """
        try:
            self.conn.execute("PRAGMA incremental_vacuum")
            self.conn.commit()
        except sqlite3.Error:
            pass


def apply_history(snapshot: Dict[str, Any], config) -> Dict[str, Any]:
    """Enrich a snapshot with history-derived fields and persist state.

    Adds ``network.new_paths_1h`` and merges persisted recent events. Safe to
    call even when history is disabled — it simply returns the snapshot.
    """
    if not getattr(config, "history_enabled", False):
        snapshot.setdefault("network", {})["new_paths_1h"] = None
        return snapshot

    history: Optional[History] = None
    try:
        history = History(config.history_db)
        now = snapshot.get("generated_unix")

        # New paths in the last hour.
        hashes = snapshot.get("path_table", {}).get("hashes", [])
        if hashes:
            new_paths = history.update_paths(hashes, now)
            snapshot["network"]["new_paths_1h"] = new_paths

        # Detect service restarts by comparing service uptime to interval.
        derived = _derive_events(snapshot)

        # Persist journal + derived events, then read back the deduped recent set.
        history.add_events(snapshot.get("events", []) + derived)
        snapshot["events"] = history.recent_events(config.events_display_limit)

        # Archive + housekeeping.
        history.archive_snapshot(snapshot)
        history.prune_paths(config.history_retention_hours, now)
        history.prune_events(config.history_retention_hours, now)
        history.prune_snapshots(config.history_retention_hours, now)
        history.reclaim()
    except Exception as exc:
        snapshot.setdefault("errors", []).append(f"history: {exc}")
        snapshot.setdefault("network", {}).setdefault("new_paths_1h", None)
    finally:
        if history:
            history.close()

    return snapshot


def _derive_events(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate events that require interpreting the snapshot itself."""
    events: List[Dict[str, Any]] = []
    now = snapshot.get("generated_unix") or int(time.time())

    # Announce spike.
    net = snapshot.get("network", {})
    if net.get("announce_spike"):
        events.append(
            {
                "unix": now,
                "type": "announce_spike",
                "detail": f"Announce spike: {net.get('announces_window')} announces "
                f"in {net.get('announce_window_minutes')}m",
            }
        )

    # Service recently (re)started (uptime less than ~2 generation intervals).
    services = snapshot.get("health", {}).get("services", {})
    for label, info in services.items():
        uptime = info.get("uptime_seconds")
        if info.get("active") and uptime is not None and uptime < 90:
            events.append(
                {
                    "unix": now,
                    "type": "service_restart",
                    "detail": f"{label} recently started ({int(uptime)}s uptime)",
                }
            )
    return events
