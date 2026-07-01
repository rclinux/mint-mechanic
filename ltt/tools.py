"""Cross-launch the sibling tools (integration by launch, not merge — P2).

Mint Mechanic never absorbs disk-recovery-tool or workstation-dashboard; it just
launches them if they're installed. Each launch is detached so closing Mint
Mechanic doesn't take the sibling down with it.
"""

from __future__ import annotations

import shutil
import subprocess


def _which_any(candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        path = shutil.which(c)
        if path:
            return path
    return None


def drt_command() -> str | None:
    """The disk-recovery-tool launcher, if installed."""
    return _which_any(("recovery-tool",))


def dashboard_command() -> str | None:
    """The workstation-dashboard launcher, if installed."""
    return _which_any(("workstation-dashboard",))


def launch(command: str) -> bool:
    """Start `command` detached from this process."""
    try:
        subprocess.Popen([command], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False
