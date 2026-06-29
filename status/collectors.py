"""Data collection layer for the chioff-rns status generator.

Each collector is defensive: any failure is captured into the ``errors`` list of
the resulting snapshot rather than raising. The output is a plain ``dict``
(JSON-serializable) so it can be reused by any downstream consumer — the
NomadNet renderer today, and FastAPI / Prometheus / Grafana later.

Public entry point:  ``collect_snapshot(config) -> dict``
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import time
from typing import Any, Dict, List, Optional

from . import SCHEMA_VERSION
from .anonymize import anonymize_hash, anonymize_ip, consent_label
from .config import Config
from .util import parse_size_to_bytes, run, which

# ---------------------------------------------------------------------------
# System / service health
# ---------------------------------------------------------------------------


def collect_system(config: Config, errors: List[str]) -> Dict[str, Any]:
    """Host-level health: uptime, load, CPU, memory, disk."""
    data: Dict[str, Any] = {}

    # Uptime from /proc/uptime (Linux).
    try:
        with open("/proc/uptime", "r", encoding="ascii") as handle:
            data["uptime_seconds"] = float(handle.read().split()[0])
    except Exception as exc:  # pragma: no cover - non-Linux / restricted
        data["uptime_seconds"] = None
        errors.append(f"system.uptime: {exc}")

    # Load average + CPU count.
    try:
        data["load"] = list(os.getloadavg())
    except (OSError, AttributeError) as exc:
        data["load"] = None
        errors.append(f"system.load: {exc}")
    data["cpu_count"] = os.cpu_count()

    # Memory from /proc/meminfo.
    data["memory"] = _read_meminfo(errors)

    # Disk usage for the configured path.
    try:
        import shutil

        usage = shutil.disk_usage(config.disk_path)
        data["disk"] = {
            "path": config.disk_path,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": round(usage.used / usage.total * 100, 1) if usage.total else None,
        }
    except Exception as exc:
        data["disk"] = None
        errors.append(f"system.disk: {exc}")

    return data


def _read_meminfo(errors: List[str]) -> Optional[Dict[str, Any]]:
    try:
        info: Dict[str, int] = {}
        with open("/proc/meminfo", "r", encoding="ascii") as handle:
            for line in handle:
                key, _, rest = line.partition(":")
                value = rest.strip().split()
                if value and value[0].isdigit():
                    info[key.strip()] = int(value[0]) * 1024  # kB -> bytes
        total = info.get("MemTotal")
        available = info.get("MemAvailable")
        if total is None:
            return None
        used = total - available if available is not None else None
        return {
            "total": total,
            "available": available,
            "used": used,
            "percent": round(used / total * 100, 1) if (used and total) else None,
        }
    except Exception as exc:
        errors.append(f"system.memory: {exc}")
        return None


def collect_services(config: Config, errors: List[str]) -> Dict[str, Any]:
    """systemd state + uptime for each configured unit."""
    if not which("systemctl"):
        errors.append("services: systemctl not available")
        return {label: {"active": None, "state": "unknown", "uptime_seconds": None}
                for label in config.services}

    host_uptime = _host_uptime_seconds()
    result: Dict[str, Any] = {}
    for label, unit in config.services.items():
        rc, out, _ = run(["systemctl", "is-active", unit], timeout=config.command_timeout)
        state = out.strip() or "unknown"
        active = state == "active"
        uptime = _service_uptime_seconds(unit, host_uptime, config.command_timeout)
        result[label] = {
            "unit": unit,
            "active": active,
            "state": state,
            "uptime_seconds": uptime,
        }
    return result


def _host_uptime_seconds() -> Optional[float]:
    try:
        with open("/proc/uptime", "r", encoding="ascii") as handle:
            return float(handle.read().split()[0])
    except Exception:
        return None


def _service_uptime_seconds(unit: str, host_uptime: Optional[float], timeout: int) -> Optional[float]:
    """Derive service uptime from the monotonic activation timestamp.

    Using the monotonic clock avoids timezone parsing headaches.
    """
    if host_uptime is None:
        return None
    rc, out, _ = run(
        ["systemctl", "show", unit, "-p", "ActiveEnterTimestampMonotonic"],
        timeout=timeout,
    )
    if rc != 0:
        return None
    match = re.search(r"=(\d+)", out)
    if not match:
        return None
    activated_monotonic_us = int(match.group(1))
    if activated_monotonic_us <= 0:
        return None
    activated_seconds_since_boot = activated_monotonic_us / 1_000_000
    uptime = host_uptime - activated_seconds_since_boot
    return uptime if uptime >= 0 else None


# ---------------------------------------------------------------------------
# rnstatus parsing (interfaces + transport summary)
# ---------------------------------------------------------------------------

# Map raw rnstatus interface type tokens to friendly section categories.
_IFACE_CATEGORY = {
    "TCPServerInterface": "tcp_server",
    "TCPClientInterface": "tcp_client",
    "TCPInterface": "tcp_client",
    "AutoInterface": "auto",
    "RNodeInterface": "rnode_lora",
    "RNodeMultiInterface": "rnode_lora",
    "KISSInterface": "kiss_tnc",
    "SerialInterface": "serial",
    "AX25KISSInterface": "kiss_tnc",
    "I2PInterface": "i2p",
    "UDPInterface": "udp",
    "LocalInterface": "local",
}

_TRAFFIC_RE = re.compile(
    r"([0-9.]+\s*[A-Za-z]+)\s*[\u2191\u2193]"  # value + up/down arrow
)


def collect_rnstatus(config: Config, errors: List[str]) -> Dict[str, Any]:
    """Run rnstatus and parse interfaces + transport destination/path counts."""
    cmd = [config.rnstatus_cmd]
    if config.rns_config:
        cmd += ["--config", config.rns_config]
    rc, out, err = run(cmd, timeout=config.command_timeout)
    if rc != 0 or not out.strip():
        errors.append(f"rnstatus: rc={rc} {err.strip() or 'no output'}")
        return {"available": False, "interfaces": [], "destinations": None, "paths": None}

    return _parse_rnstatus(out, config)


def _parse_rnstatus(text: str, config: Config) -> Dict[str, Any]:
    interfaces: List[Dict[str, Any]] = []
    destinations: Optional[int] = None
    paths: Optional[int] = None
    transport_id: Optional[str] = None

    blocks = re.split(r"\n\s*\n", text.strip())
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        header = lines[0].strip()

        # Transport summary line, e.g.:
        #   "Reticulum Transport Instance <hash> running"
        #   "  Found 12 destinations and 5 paths"
        m = re.search(r"(\d+)\s+destinations?", block)
        if m:
            destinations = int(m.group(1))
        m = re.search(r"(\d+)\s+paths?", block)
        if m:
            paths = int(m.group(1))
        m = re.search(r"Transport Instance\s+([0-9a-fA-F]+)", block)
        if m:
            transport_id = anonymize_hash(m.group(1), config.public_mode, consented=config.consented)

        iface = _parse_interface_block(header, lines[1:], config)
        if iface:
            interfaces.append(iface)

    return {
        "available": True,
        "interfaces": interfaces,
        "destinations": destinations,
        "paths": paths,
        "transport_id": transport_id,
    }


def _parse_interface_block(header: str, body: List[str], config: Config) -> Optional[Dict[str, Any]]:
    hm = re.match(r"^([A-Za-z0-9_]+)\[(.*)\]$", header)
    if not hm:
        return None
    iface_type = hm.group(1)
    detail = hm.group(2)

    # Friendly name is the portion before the first '/'.
    friendly = detail.split("/", 1)[0].strip() or iface_type
    endpoint = detail.split("/", 1)[1].strip() if "/" in detail else ""

    fields: Dict[str, str] = {}
    for line in body:
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()

    status_raw = fields.get("status", "").lower()
    online = status_raw.startswith("up") or status_raw.startswith("on")

    rx_bytes = tx_bytes = None
    traffic = fields.get("traffic")
    if traffic:
        matches = _TRAFFIC_RE.findall(traffic)
        # rnstatus prints up (tx) first, then down (rx).
        if len(matches) >= 1:
            tx_bytes = parse_size_to_bytes(matches[0])
        if len(matches) >= 2:
            rx_bytes = parse_size_to_bytes(matches[1])

    peer_count = None
    peers_field = fields.get("peers") or fields.get("connected")
    if peers_field:
        pm = re.search(r"(\d+)", peers_field)
        if pm:
            peer_count = int(pm.group(1))

    if config.public_mode and endpoint:
        endpoint = anonymize_ip(endpoint, config.public_mode)

    return {
        "type": iface_type,
        "category": _IFACE_CATEGORY.get(iface_type, "other"),
        "name": friendly,
        "endpoint": endpoint,
        "online": online,
        "status": fields.get("status", "unknown"),
        "mode": fields.get("mode"),
        "rate": fields.get("rate"),
        "rx_bytes": rx_bytes,
        "tx_bytes": tx_bytes,
        "peer_count": peer_count,
        "raw_fields": fields,
    }


# ---------------------------------------------------------------------------
# rnpath (path table)
# ---------------------------------------------------------------------------


def collect_paths(config: Config, errors: List[str], names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Parse the rnpath path table using JSON output (-j flag).

    Falls back to text parsing if JSON output is unavailable (older rnpath).
    """
    names = names or {}
    # Try JSON output first — faster and more reliable.
    cmd_json = [config.rnpath_cmd, "--table", "-j"]
    if config.rns_config:
        cmd_json += ["--config", config.rns_config]
    rc, out, err = run(cmd_json, timeout=config.command_timeout)
    if rc == 0 and out.strip():
        return _parse_rnpath_json(out, config, errors, names)

    # Fallback: text parsing for older rnpath versions.
    cmd_text = [config.rnpath_cmd, "--table"]
    if config.rns_config:
        cmd_text += ["--config", config.rns_config]
    rc, out, err = run(cmd_text, timeout=config.command_timeout)
    if rc != 0 or not out.strip():
        errors.append(f"rnpath: rc={rc} {err.strip() or 'no output'}")
        return {"available": False, "count": 0, "entries": [], "hashes": []}
    return _parse_rnpath_text(out, config, names)


def _parse_rnpath_json(out: str, config: Config, errors: List[str], names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Parse rnpath JSON output (rnpath --table -j)."""
    names = names or {}
    import json as _json
    try:
        raw = _json.loads(out)
    except Exception as exc:
        errors.append(f"rnpath json parse: {exc}")
        return {"available": False, "count": 0, "entries": [], "hashes": []}

    entries: List[Dict[str, Any]] = []
    hashes: List[str] = []
    for item in raw:
        try:
            dest_hash = item.get("hash", "")
            via_hash = item.get("via", "")
            hops = int(item.get("hops", 0))
            iface = item.get("interface", "")
            hashes.append(dest_hash)
            entries.append(
                {
                    "destination": anonymize_hash(dest_hash, config.public_mode),
                    "destination_full": dest_hash,
                    "name": names.get(dest_hash.lower()),
                    "hops": hops,
                    "via": anonymize_hash(via_hash, config.public_mode),
                    "via_full": via_hash,
                    "via_name": names.get(via_hash.lower()),
                    "interface": iface,
                }
            )
        except Exception:
            continue

    transport_peers = len({e["via"] for e in entries if e.get("via")})
    return {
        "available": True,
        "count": len(hashes),
        "entries": entries,
        "hashes": hashes,
        "transport_peers": transport_peers,
    }


def _parse_rnpath_text(out: str, config: Config, names: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Parse rnpath plain-text output (fallback for older rnpath versions)."""
    names = names or {}
    entries: List[Dict[str, Any]] = []
    hashes: List[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # rnpath emits: "<dest_hash> is <n> hops away via <via_hash> on <iface> expires ..."
        # Strip optional angle-bracket wrapping around hashes.
        line_stripped = re.sub(r"<([0-9a-fA-F]+)>", r"\1", line)
        m = re.match(
            r"^([0-9a-fA-F]+)\s+is\s+(\d+)\s+hops?\s+away\s+via\s+([0-9a-fA-F]+)(?:\s+on\s+(.*?))?(?:\s+expires\s+.*)?$",
            line_stripped,
        )
        if not m:
            # Fallback: capture any leading hash so counts stay meaningful.
            mh = re.match(r"^<?([0-9a-fA-F]{8,})>?", line)
            if mh:
                hashes.append(mh.group(1))
            continue
        dest_hash = m.group(1)
        via_hash = m.group(3)
        hashes.append(dest_hash)
        entries.append(
            {
                "destination": anonymize_hash(dest_hash, config.public_mode, consented=config.consented),
                "destination_full": anonymize_hash(dest_hash, config.public_mode, consented=config.consented),
                "destination_label": consent_label(dest_hash, config.consented),
                "name": names.get(dest_hash.lower()),
                "hops": int(m.group(2)),
                "via": anonymize_hash(via_hash, config.public_mode, consented=config.consented),
                "via_full": anonymize_hash(via_hash, config.public_mode, consented=config.consented),
                "via_label": consent_label(via_hash, config.consented),
                "via_name": names.get(via_hash.lower()),
                "interface": (m.group(4) or "").strip(),
            }
        )

    transport_peers = len({e["via"] for e in entries if e.get("via")})
    return {
        "available": True,
        "count": len(hashes),
        "entries": entries,
        "hashes": hashes,
        "transport_peers": transport_peers,
    }


# ---------------------------------------------------------------------------
# TCP socket peers (port 4242)
# ---------------------------------------------------------------------------


def collect_tcp_peers(config: Config, errors: List[str]) -> Dict[str, Any]:
    """Count established TCP connections involving the Reticulum port via ss."""
    port = config.public_port
    if not which("ss"):
        errors.append("tcp_peers: ss not available")
        return {"available": False, "count": 0, "inbound": [], "outbound": []}

    rc, out, err = run(["ss", "-Htn", "state", "established"], timeout=config.command_timeout)
    if rc != 0:
        errors.append(f"tcp_peers: ss rc={rc} {err.strip()}")
        return {"available": False, "count": 0, "inbound": [], "outbound": []}

    inbound: List[str] = []
    outbound: List[str] = []
    port_suffix = f":{port}"
    for line in out.splitlines():
        cols = line.split()
        if len(cols) < 4:
            continue
        local, remote = cols[-2], cols[-1]
        if local.endswith(port_suffix):
            inbound.append(anonymize_ip(remote, config.public_mode))
        elif remote.endswith(port_suffix):
            outbound.append(anonymize_ip(remote, config.public_mode))

    return {
        "available": True,
        "count": len(inbound) + len(outbound),
        "inbound": inbound,
        "outbound": outbound,
    }


# ---------------------------------------------------------------------------
# journalctl: announces + events
# ---------------------------------------------------------------------------

_EVENT_RULES = [
    (re.compile(r"connection.*(established)|connected to|peer connected", re.I), "peer_connected"),
    (re.compile(r"(connection.*(lost|closed|timed out))|disconnected|link closed", re.I), "peer_disconnected"),
    (re.compile(r"\bstarted\b.*(reticulum|nomad|lxm)|starting reticulum", re.I), "service_restart"),
    (re.compile(r"error|traceback|exception|failed", re.I), "error"),
]


def collect_journal(config: Config, errors: List[str]) -> Dict[str, Any]:
    """Parse rnsd journal logs for announce counts and notable events.

    This is best-effort and depends on the active log level. Counts are
    reported with an ``available`` flag so the page can be honest about gaps.
    """
    rnsd_unit = config.services.get("rnsd", "rnsd.service")
    if not which("journalctl"):
        errors.append("journal: journalctl not available")
        return {
            "available": False,
            "announces_window": None,
            "events": [],
        }

    lookback_hours = config.events_lookback_hours or 2
    since = f"{lookback_hours} hours ago"
    rc, out, err = run(
        [
            "journalctl",
            "-u",
            rnsd_unit,
            "--since",
            since,
            "-o",
            "short-iso",
            "--no-pager",
        ],
        timeout=config.command_timeout,
    )
    if rc != 0:
        errors.append(f"journal: journalctl rc={rc} {err.strip()}")
        return {"available": False, "announces_window": None, "events": []}

    now = _dt.datetime.now(_dt.timezone.utc)
    window_start = now - _dt.timedelta(minutes=config.announce_window_minutes)

    announces_window = 0
    events: List[Dict[str, Any]] = []
    for line in out.splitlines():
        ts = _parse_journal_timestamp(line)
        lowered = line.lower()

        if "announce" in lowered:
            if ts is None or ts >= window_start:
                announces_window += 1

        for pattern, event_type in _EVENT_RULES:
            if pattern.search(line):
                events.append(
                    {
                        "time": ts.isoformat() if ts else None,
                        "unix": int(ts.timestamp()) if ts else None,
                        "type": event_type,
                        "detail": _redact_log_line(line, config),
                    }
                )
                break

    # Newest first, capped.
    events.sort(key=lambda e: e.get("unix") or 0, reverse=True)
    events = events[: config.events_display_limit]

    return {
        "available": True,
        "announces_window": announces_window,
        "events": events,
    }


_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([+-]\d{2}:?\d{2})?")


def _parse_journal_timestamp(line: str) -> Optional[_dt.datetime]:
    match = _TS_RE.match(line.strip())
    if not match:
        return None
    base = match.group(1)
    tz = match.group(2)
    try:
        if tz:
            tz = tz.replace(":", "")
            dt = _dt.datetime.strptime(base + tz, "%Y-%m-%dT%H:%M:%S%z")
        else:
            dt = _dt.datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=_dt.timezone.utc
            )
        return dt.astimezone(_dt.timezone.utc)
    except ValueError:
        return None


_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_HASH_IN_LINE_RE = re.compile(r"\b[0-9a-fA-F]{16,}\b")


def _redact_log_line(line: str, config: Config) -> str:
    """Strip the leading timestamp/host prefix and redact IPs/hashes if public."""
    # Drop the ISO timestamp + hostname + unit prefix; keep the message tail.
    msg = line
    parts = line.split(":", 3)
    if len(parts) == 4:
        msg = parts[3].strip()
    msg = msg.strip()
    if config.public_mode:
        msg = _IP_RE.sub(lambda m: anonymize_ip(m.group(0), True), msg)
        msg = _HASH_IN_LINE_RE.sub(lambda m: anonymize_hash(m.group(0), True), msg)
    return msg[:160]


# ---------------------------------------------------------------------------
# Announce name map  (reads RNS known_destinations storage file)
# ---------------------------------------------------------------------------


def collect_names(config: Config, errors: List[str]) -> Dict[str, str]:
    """Return a {full_hex_hash: display_name} map scraped from the RNS
    known_destinations storage file without importing RNS.

    The file is a msgpack list of entries; each entry is a list whose
    element [3] is raw app_data bytes.  Names are extracted by scanning
    for the longest printable ASCII run — this is intentionally loose so
    it works across Sideband, NomadNet, Inertia, and custom firmwares.
    """
    storage_dir = config.rns_config  # e.g. /etc/reticulum
    kd_path = os.path.join(storage_dir, "storage", "known_destinations")
    if not os.path.isfile(kd_path):
        errors.append("names: known_destinations file not found")
        return {}

    try:
        # Use the bundled umsgpack via a tiny subprocess so we don't need
        # to import RNS (which would start a second transport instance).
        script = r"""
import sys, os, re
rns_site = None
for p in sys.path:
    if os.path.isfile(os.path.join(p, 'RNS', 'vendor', 'umsgpack.py')):
        rns_site = p
        break
if not rns_site:
    sys.exit(1)
sys.path.insert(0, rns_site)
import RNS.vendor.umsgpack as mp

kd_path = sys.argv[1]
with open(kd_path, 'rb') as fh:
    raw = fh.read()
try:
    data = mp.unpackb(raw)
except Exception:
    sys.exit(0)

results = {}
if isinstance(data, dict):
    items = data.items()
elif isinstance(data, list):
    items = [(e[0], e[1:]) for e in data if isinstance(e, (list, tuple)) and len(e) >= 2]
else:
    sys.exit(0)

for k, v in items:
    try:
        h = k.hex() if isinstance(k, bytes) else str(k)
        entry = v if isinstance(v, (list, tuple)) else [v]
        app_data = entry[3] if len(entry) > 3 else None
        if not app_data or not isinstance(app_data, bytes):
            continue
        # Plain UTF-8 first
        try:
            candidate = app_data.decode('utf-8').strip()
            if 2 <= len(candidate) <= 60 and all(32 <= ord(c) < 127 for c in candidate):
                results[h] = candidate
                continue
        except Exception:
            pass
        # Longest printable ASCII run
        runs = re.findall(b'[ -~]{4,}', app_data)
        if runs:
            best = max(runs, key=len).decode('ascii').strip()
            if 4 <= len(best) <= 60:
                results[h] = best
    except Exception:
        pass

for h, n in results.items():
    sys.stdout.write(h + '\t' + n + '\n')
"""
        rc, out, err = run(
            ["python3", "-c", script, kd_path],
            timeout=config.command_timeout,
        )
        if rc != 0:
            errors.append(f"names: scraper rc={rc}")
            return {}
        names: Dict[str, str] = {}
        for line in out.splitlines():
            parts = line.split("\t", 1)
            if len(parts) == 2:
                names[parts[0].lower()] = parts[1]
        return names
    except Exception as exc:
        errors.append(f"names: {exc}")
        return {}


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _clean_error(message: str) -> str:
    """Collapse an error to a single, length-capped line.

    Keeps collector notes readable and avoids leaking multi-line tracebacks
    (and the local filesystem paths they contain) onto the public page.
    """
    first_line = (message or "").strip().splitlines()
    text = first_line[0] if first_line else ""
    return text[:160]


def collect_snapshot(config: Config) -> Dict[str, Any]:
    """Run every collector and assemble a JSON-serializable snapshot dict.

    This is the single reusable contract for all downstream consumers.
    """
    errors: List[str] = []
    now = _dt.datetime.now(_dt.timezone.utc)

    services = collect_services(config, errors)
    system = collect_system(config, errors)
    rnstatus = collect_rnstatus(config, errors)
    names = collect_names(config, errors)
    paths = collect_paths(config, errors, names)
    tcp = collect_tcp_peers(config, errors)
    journal = collect_journal(config, errors)

    # Prefer rnstatus destination/path counts; fall back to rnpath table.
    destinations = rnstatus.get("destinations")
    path_count = rnstatus.get("paths")
    if path_count is None and paths.get("available"):
        path_count = paths.get("count")

    transport_peers = paths.get("transport_peers")

    announces_window = journal.get("announces_window")
    spike = (
        announces_window is not None
        and announces_window >= config.announce_spike_threshold
    )

    snapshot: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "generated_unix": int(now.timestamp()),
        "public_mode": config.public_mode,
        "node": {
            "hostname": config.resolved_hostname(),
            "public_address": config.public_address,
            "public_port": config.public_port,
            "transport_id": rnstatus.get("transport_id"),
        },
        "health": {
            "services": services,
            "system": system,
        },
        "network": {
            "tcp_peers": tcp,
            "destinations": destinations,
            "paths": path_count,
            "announces_window": announces_window,
            "announce_window_minutes": config.announce_window_minutes,
            "announce_spike": spike,
            "announce_available": journal.get("available", False),
            "new_paths_1h": None,  # filled in by history layer
            "transport_peers": transport_peers,
        },
        "interfaces": rnstatus.get("interfaces", []),
        "path_table": {
            "available": paths.get("available", False),
            "count": paths.get("count", 0),
            "entries": paths.get("entries", []),
            "hashes": paths.get("hashes", []),
        },
        "peer_attribution": {
            "instrumented": False,
            "note": (
                "Per-peer destination/route attribution is not yet instrumented. "
                "Reticulum does not expose which transport peer imported a given "
                "path through rnstatus/rnpath. Future work: hook Reticulum path "
                "learning to attribute imported destinations per peer."
            ),
            "peers": [],
        },
        "events": journal.get("events", []),
        "errors": errors,
    }
    snapshot["errors"] = [_clean_error(e) for e in errors]
    return snapshot
