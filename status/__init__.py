"""chioff-rns status generator.

A small, dependency-light toolkit that collects operational status for the
Chicago Offline public Reticulum node and renders a NomadNet `.mu` page.

The collection layer (`status.collectors`) is intentionally decoupled from the
rendering layer so the same `Snapshot` dict can later feed FastAPI, Prometheus,
or Grafana exporters without modification.
"""

__version__ = "0.1.0"
SCHEMA_VERSION = 1
