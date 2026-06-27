"""Small, dependency-free helpers shared across collectors.

Everything here uses only the Python standard library so the collection layer
stays portable and reusable.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import List, Optional, Tuple


def run(cmd: List[str], timeout: int = 10) -> Tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr).

    Never raises: missing binaries, timeouts, and unexpected errors are all
    mapped to a non-zero return code so callers can degrade gracefully.
    """
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except PermissionError as exc:
        return 126, "", str(exc)
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s: {' '.join(cmd)}"
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return 1, "", str(exc)


def which(name: str) -> Optional[str]:
    """Return the resolved path of a binary, or None if not on PATH."""
    return shutil.which(name)


_SIZE_UNITS = {
    "B": 1,
    "KB": 1000,
    "K": 1000,
    "KIB": 1024,
    "MB": 1000 ** 2,
    "M": 1000 ** 2,
    "MIB": 1024 ** 2,
    "GB": 1000 ** 3,
    "G": 1000 ** 3,
    "GIB": 1024 ** 3,
    "TB": 1000 ** 4,
    "T": 1000 ** 4,
    "TIB": 1024 ** 4,
}

_SIZE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)")


def parse_size_to_bytes(text: str) -> Optional[int]:
    """Parse a human readable size such as '1.23 MB' into bytes.

    Returns None when nothing parseable is found. Tolerant of the unit casing
    and spacing variations emitted by different rnstatus versions.
    """
    if not text:
        return None
    match = _SIZE_RE.search(text)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    factor = _SIZE_UNITS.get(unit)
    if factor is None:
        return None
    return int(value * factor)


def human_bytes(num: Optional[float]) -> str:
    """Format a byte count using binary units. Returns 'n/a' for None."""
    if num is None:
        return "n/a"
    value = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if abs(value) < 1024.0:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} EiB"


def human_duration(seconds: Optional[float]) -> str:
    """Format a duration in seconds as a compact 'Nd Nh Nm' string."""
    if seconds is None or seconds < 0:
        return "n/a"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)
