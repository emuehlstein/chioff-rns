"""Configuration loading for the status generator.

Uses the standard-library ``configparser`` (INI) so no extra dependency is
needed just to read settings. All values have sane defaults tuned for the
chioff-rns deployment, and every default can be overridden in the config file.
"""
from __future__ import annotations

import configparser
import os
import socket
from dataclasses import dataclass, field
from typing import Dict, List, Optional

DEFAULT_CONFIG_PATHS = [
    os.environ.get("CHIOFF_STATUS_CONFIG", ""),
    "/etc/chioff-status.config",
    os.path.expanduser("~/.config/chioff-status.config"),
]


@dataclass
class Config:
    # --- general ---
    public_mode: bool = True
    node_hostname: str = ""
    public_address: str = "rns.chicagooffline.com"
    public_port: int = 4242
    rns_config: str = "/etc/reticulum"
    rnstatus_cmd: str = "rnstatus"
    rnpath_cmd: str = "rnpath"
    command_timeout: int = 15

    # --- services: label -> systemd unit ---
    services: Dict[str, str] = field(
        default_factory=lambda: {
            "rnsd": "rnsd.service",
            "lxmd": "lxmd.service",
            "nomadnet": "nomadnet.service",
        }
    )

    # --- output paths ---
    json_output: str = "/var/lib/chicagooffline-rns/status.json"
    page_output: str = "/home/rns/.nomadnetwork/storage/pages/status.mu"
    disk_path: str = "/"

    # --- consent allowlist: full hash -> friendly label ---
    consent_file: str = "/etc/chioff-consent.config"
    consented: Dict[str, str] = field(default_factory=dict)

    # --- history (SQLite) ---
    history_enabled: bool = True
    history_db: str = "/var/lib/chicagooffline-rns/history.db"
    history_retention_hours: int = 168

    # --- announces / events ---
    announce_window_minutes: int = 15
    announce_spike_threshold: int = 20
    events_lookback_hours: int = 2
    events_display_limit: int = 12

    # --- chicago network info shown on the page ---
    network_blurb: str = (
        "rns.chicagooffline.com is the always-on public Reticulum transport "
        "node for Chicago Offline. It routes traffic for the Chicagoland mesh, "
        "propagates LXMF mail, and serves these NomadNet pages."
    )
    local_services: List[str] = field(
        default_factory=lambda: [
            "NomadNet pages (index.mu)",
            "LXMF propagation (store & forward)",
            "Reticulum Relay Chat (rrcd.mu)",
        ]
    )

    def resolved_hostname(self) -> str:
        return self.node_hostname or socket.gethostname()


def _getbool(parser: configparser.ConfigParser, section: str, key: str, default: bool) -> bool:
    if parser.has_option(section, key):
        return parser.getboolean(section, key)
    return default


def _getint(parser: configparser.ConfigParser, section: str, key: str, default: int) -> int:
    if parser.has_option(section, key):
        return parser.getint(section, key)
    return default


def _getstr(parser: configparser.ConfigParser, section: str, key: str, default: str) -> str:
    if parser.has_option(section, key):
        return parser.get(section, key).strip()
    return default


def _getlist(parser: configparser.ConfigParser, section: str, key: str, default: List[str]) -> List[str]:
    if not parser.has_option(section, key):
        return default
    raw = parser.get(section, key)
    items = [line.strip(" -\t") for line in raw.splitlines()]
    items = [i for i in items if i]
    return items or default


def load_config(path: Optional[str] = None) -> Config:
    """Load configuration from ``path`` or the first existing default path.

    A missing config file is fine; built-in defaults are used instead.
    """
    cfg = Config()

    candidates = [path] if path else []
    candidates += DEFAULT_CONFIG_PATHS
    config_path = next((p for p in candidates if p and os.path.isfile(p)), None)
    if not config_path:
        return cfg

    parser = configparser.ConfigParser()
    # Preserve case of keys (needed for the [services] map).
    parser.optionxform = str  # type: ignore[assignment]
    parser.read(config_path)

    if parser.has_section("general"):
        cfg.public_mode = _getbool(parser, "general", "public_mode", cfg.public_mode)
        cfg.node_hostname = _getstr(parser, "general", "node_hostname", cfg.node_hostname)
        cfg.public_address = _getstr(parser, "general", "public_address", cfg.public_address)
        cfg.public_port = _getint(parser, "general", "public_port", cfg.public_port)
        cfg.rns_config = _getstr(parser, "general", "rns_config", cfg.rns_config)
        cfg.rnstatus_cmd = _getstr(parser, "general", "rnstatus_cmd", cfg.rnstatus_cmd)
        cfg.rnpath_cmd = _getstr(parser, "general", "rnpath_cmd", cfg.rnpath_cmd)
        cfg.command_timeout = _getint(parser, "general", "command_timeout", cfg.command_timeout)

    if parser.has_section("paths"):
        cfg.json_output = _getstr(parser, "paths", "json_output", cfg.json_output)
        cfg.page_output = _getstr(parser, "paths", "page_output", cfg.page_output)
        cfg.disk_path = _getstr(parser, "paths", "disk_path", cfg.disk_path)

    if parser.has_section("history"):
        cfg.history_enabled = _getbool(parser, "history", "enabled", cfg.history_enabled)
        cfg.history_db = _getstr(parser, "history", "db", cfg.history_db)
        cfg.history_retention_hours = _getint(
            parser, "history", "retention_hours", cfg.history_retention_hours
        )

    if parser.has_section("announces"):
        cfg.announce_window_minutes = _getint(
            parser, "announces", "window_minutes", cfg.announce_window_minutes
        )
        cfg.announce_spike_threshold = _getint(
            parser, "announces", "spike_threshold", cfg.announce_spike_threshold
        )

    if parser.has_section("events"):
        cfg.events_lookback_hours = _getint(
            parser, "events", "lookback_hours", cfg.events_lookback_hours
        )
        cfg.events_display_limit = _getint(
            parser, "events", "display_limit", cfg.events_display_limit
        )

    if parser.has_section("services"):
        services = {k: v.strip() for k, v in parser.items("services") if v.strip()}
        if services:
            cfg.services = services

    if parser.has_section("chicago"):
        cfg.network_blurb = _getstr(parser, "chicago", "blurb", cfg.network_blurb)
        cfg.local_services = _getlist(parser, "chicago", "local_services", cfg.local_services)

    cfg.consent_file = _getstr(parser, "paths", "consent_file", cfg.consent_file)
    # Inline [consent] entries first, then a standalone consent file (which wins).
    if parser.has_section("consent"):
        cfg.consented.update(_normalize_consent(parser.items("consent")))
    cfg.consented.update(_load_consent_file(cfg.consent_file))

    return cfg


def _normalize_consent(items) -> Dict[str, str]:
    """Lowercase hashes, keep labels; drop blanks. Maps hash -> label."""
    out: Dict[str, str] = {}
    for key, value in items:
        h = (key or "").strip().lower()
        if h:
            out[h] = (value or "").strip() or h[:8]
    return out


def _load_consent_file(path: str) -> Dict[str, str]:
    if not path or not os.path.isfile(path):
        return {}
    parser = configparser.ConfigParser()
    parser.optionxform = str  # preserve hash case before we lowercase it
    try:
        parser.read(path)
    except configparser.Error:
        return {}
    if parser.has_section("consent"):
        return _normalize_consent(parser.items("consent"))
    return {}
