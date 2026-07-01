"""System Cleaner — reclaimable-space tasks (the portable half of maintenance).

Data-driven (P4): each task is a `CleanTask` with a best-effort size measurement
and a fixed shell command. No user input is ever interpolated into these
commands — they're constant and audited here — so running them via `bash -c` is
safe. User-level tasks run as you; root-level tasks elevate via pkexec. The Arch
half of ATT's maintenance (keyring, mirrors, pacman.conf, mkinitcpio) is
deliberately absent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CleanTask:
    key: str
    label: str
    description: str
    root: bool          # needs elevation
    command: str        # fixed shell command (run via bash -c)
    available: bool = True

    def measure(self) -> str:
        """Best-effort human size/count for the UI; never raises."""
        return _MEASURES.get(self.key, lambda: "")()


def _sh(cmd: str) -> str:
    try:
        out = subprocess.run(["bash", "-c", cmd], capture_output=True,
                             text=True, timeout=8, check=False)
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _du(path: str) -> str:
    if not os.path.exists(path):
        return "empty"
    return _sh(f"du -sh {path!r} 2>/dev/null | cut -f1") or "—"


_MEASURES = {
    "apt_cache": lambda: _du("/var/cache/apt/archives"),
    "orphans": lambda: (f"{n} pkgs" if (n := _sh('deborphan 2>/dev/null | wc -l'))
                        not in ("", "0") else "none"),
    "thumbnails": lambda: _du(os.path.expanduser("~/.cache/thumbnails")),
    "trash": lambda: _du(os.path.expanduser("~/.local/share/Trash")),
    "journal": lambda: (_sh("journalctl --disk-usage 2>/dev/null "
                            "| grep -oE '[0-9.]+[KMGT]?B' | tail -1") or "—"),
}

_HOME = os.path.expanduser("~")

TASKS: tuple[CleanTask, ...] = (
    CleanTask("apt_cache", "APT package cache",
              "Downloaded .deb archives in /var/cache/apt.", True,
              "apt-get clean"),
    CleanTask("orphans", "Orphaned packages",
              "Libraries no longer needed by anything (deborphan).", True,
              "deborphan | xargs -r apt-get -y purge",
              available=shutil.which("deborphan") is not None),
    CleanTask("thumbnails", "Thumbnail cache",
              "Cached image thumbnails (regenerated on demand).", False,
              f"rm -rf {_HOME}/.cache/thumbnails/*"),
    CleanTask("trash", "Trash",
              "Files in your desktop Trash.", False,
              f"rm -rf {_HOME}/.local/share/Trash/files/* "
              f"{_HOME}/.local/share/Trash/info/*"),
    CleanTask("journal", "Old system logs",
              "Vacuum the systemd journal to the last 7 days.", True,
              "journalctl --vacuum-time=7d"),
)


def tasks() -> tuple[CleanTask, ...]:
    return TASKS
