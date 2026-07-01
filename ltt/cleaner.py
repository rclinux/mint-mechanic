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


_HOME = os.path.expanduser("~")
_TRASH = os.path.join(_HOME, ".local/share/Trash")


def _du(path: str) -> str:
    if not os.path.exists(path):
        return "empty"
    return _sh(f"du -sh {path!r} 2>/dev/null | cut -f1") or "—"


def _human(n: float) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


def _content_size(find_cmd: str) -> str:
    """Sum the bytes of files matched by `find_cmd` (which prints %s per file).

    Measures actual *contents*, not the enclosing directory — so a cleaned area
    reads 'empty' instead of the KBs of an emptied-but-unshrunk directory inode
    (the ext4 quirk behind the '68K APT cache' / '16K Trash' confusion).
    """
    out = _sh(find_cmd)
    total = sum(int(x) for x in out.split() if x.isdigit())
    return _human(total) if total > 0 else "empty"


def _trash_measure() -> str:
    """Report the trashed *contents*, so an emptied Trash reads 'empty' rather
    than the few KB of its own (empty) directory tree and bookkeeping files."""
    files = os.path.join(_TRASH, "files")
    try:
        if not os.path.isdir(files) or not os.listdir(files):
            return "empty"
    except OSError:
        return "—"
    return _du(_TRASH)


_MEASURES = {
    "apt_cache": lambda: _content_size(
        r"find /var/cache/apt/archives -name '*.deb' -printf '%s\n' 2>/dev/null"),
    "orphans": lambda: (f"{n} pkgs" if (n := _sh('deborphan 2>/dev/null | wc -l'))
                        not in ("", "0") else "none"),
    "thumbnails": lambda: _content_size(
        rf"find {os.path.expanduser('~/.cache/thumbnails')!r} -type f "
        r"-printf '%s\n' 2>/dev/null"),
    "trash": _trash_measure,
    "journal": lambda: (_sh("journalctl --disk-usage 2>/dev/null "
                            "| grep -oE '[0-9.]+[KMGT]?B' | tail -1") or "—"),
}

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
              # -mindepth 1 empties the contents (incl. bookkeeping) without a
              # dangerous glob; runs LAST so it also catches anything discarded
              # during this run.
              f"find {_TRASH}/files {_TRASH}/info {_TRASH}/expunged "
              f"-mindepth 1 -delete 2>/dev/null; "
              f"rm -f {_TRASH}/directorysizes 2>/dev/null; true"),
    CleanTask("journal", "Old system logs",
              "Vacuum the systemd journal to the last 7 days.", True,
              "journalctl --vacuum-time=7d"),
)


def tasks() -> tuple[CleanTask, ...]:
    return TASKS
