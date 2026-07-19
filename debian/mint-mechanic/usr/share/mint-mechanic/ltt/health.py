"""GO / NO-GO health checks (the concept borrowed from Workstation Dashboard).

A handful of quick, read-only checks that roll up into a single at-a-glance
verdict. Each returns a status and a one-line detail; everything is best-effort
and never raises. The checks run off the UI thread (they shell out).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

try:
    import psutil
except ImportError:
    psutil = None

GO, WARN, NOGO, UNKNOWN = "go", "warn", "nogo", "unknown"
_RANK = {GO: 0, UNKNOWN: 1, WARN: 2, NOGO: 3}


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    status: str
    detail: str


def _sh(cmd: str, timeout: int = 8) -> str:
    try:
        out = subprocess.run(["bash", "-c", cmd], capture_output=True,
                             text=True, timeout=timeout, check=False)
        return out.stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def _disk() -> Check:
    if psutil is None:
        return Check("disk", "Disk", UNKNOWN, "psutil unavailable")
    pct = psutil.disk_usage("/").percent
    status = GO if pct < 85 else WARN if pct < 95 else NOGO
    return Check("disk", "Disk", status, f"root filesystem {pct:.0f}% full")


# Units that "fail" harmlessly on an installed system (live-ISO artifacts, etc.).
_BENIGN_FAILED = {"casper-md5check.service"}


def _failed_units() -> Check:
    out = _sh("systemctl --failed --no-legend --plain 2>/dev/null")
    names = [ln.split()[0] for ln in out.splitlines() if ln.strip()]
    names = [n for n in names if n not in _BENIGN_FAILED]
    if not names:
        return Check("units", "Services", GO, "no failed units")
    return Check("units", "Services", NOGO,
                 f"{len(names)} failed: {', '.join(names[:3])}")


def _updates() -> Check:
    out = _sh("apt list --upgradable 2>/dev/null")
    n = sum(1 for ln in out.splitlines() if "/" in ln and "upgradable" in ln)
    if n == 0:
        return Check("updates", "Updates", GO, "system up to date")
    return Check("updates", "Updates", WARN, f"{n} package updates available")


def _reboot() -> Check:
    if os.path.exists("/run/reboot-required") or os.path.exists("/var/run/reboot-required"):
        return Check("reboot", "Reboot", WARN, "reboot required to finish updates")
    return Check("reboot", "Reboot", GO, "no reboot pending")


def run_checks() -> list[Check]:
    return [_disk(), _failed_units(), _updates(), _reboot()]


def overall(checks: list[Check]) -> str:
    return max((c.status for c in checks), key=lambda s: _RANK.get(s, 1),
               default=UNKNOWN)
