"""systemctl wrappers for the Services view.

Reading status/enabled-state needs no root; toggling (enable/disable, start/
stop) is elevated per-action via pkexec. Phase 0 wires the read-only paths and
builds the argv for the mutating ones; Phase 2 fills in execution + UI.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceState:
    unit: str
    active: bool        # currently running
    enabled: bool       # starts at boot
    available: bool     # unit exists on this system


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", *args],
                          capture_output=True, text=True, check=False)


def state(unit: str) -> ServiceState:
    """Live read of a unit's active/enabled/available state (no root)."""
    active = _systemctl("is-active", unit).stdout.strip() == "active"
    enabled_out = _systemctl("is-enabled", unit).stdout.strip()
    # is-enabled prints e.g. enabled/disabled/static/masked, or errors if absent
    available = enabled_out not in ("", ) and "not-found" not in enabled_out
    enabled = enabled_out in ("enabled", "enabled-runtime", "static")
    return ServiceState(unit, active, enabled, available)


def enable_argv(unit: str, now: bool = True) -> list[str]:
    args = ["enable", "--now", unit] if now else ["enable", unit]
    return ["pkexec", "systemctl", *args]


def disable_argv(unit: str, now: bool = True) -> list[str]:
    args = ["disable", "--now", unit] if now else ["disable", unit]
    return ["pkexec", "systemctl", *args]
