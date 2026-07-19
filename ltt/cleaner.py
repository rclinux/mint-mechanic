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
import shlex
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
    confirm: bool = False   # must show its true blast radius and be confirmed

    def measure(self) -> str:
        """Best-effort human size/count for the UI; never raises."""
        return _MEASURES.get(self.key, lambda: "")()


def _sh(cmd: str, timeout: int = 8) -> str:
    try:
        out = subprocess.run(["bash", "-c", cmd], capture_output=True,
                             text=True, timeout=timeout, check=False)
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


_HOME = os.path.expanduser("~")
_TRASH = os.path.join(_HOME, ".local/share/Trash")
_THUMBS = os.path.join(_HOME, ".cache/thumbnails")

# Every path below is interpolated into a shell string, so it goes through
# shlex.quote first. A home directory containing a space would otherwise
# word-split — turning `rm -rf /home/jane doe/.cache/thumbnails/*` into an
# rm against `/home/jane`, a wrong-path delete rather than a mere failure.
# (Python's !r is repr, not shell quoting, and does not survive a path
# containing a single quote.)
_Q_THUMBS = shlex.quote(_THUMBS)


def _du(path: str) -> str:
    if not os.path.exists(path):
        return "empty"
    return _sh(f"du -sh {shlex.quote(path)} 2>/dev/null | cut -f1") or "—"


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
        rf"find {_Q_THUMBS} -type f "
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
              "Libraries no longer needed by anything (deborphan). "
              "Shows exactly what would be removed before doing anything.", True,
              "",  # built at run time from a confirmed, previewed set
              available=shutil.which("deborphan") is not None,
              confirm=True),
    CleanTask("thumbnails", "Thumbnail cache",
              "Cached image thumbnails (regenerated on demand).", False,
              # The directory is quoted; the glob stays outside the quotes so
              # the shell still expands it.
              f"rm -rf {_Q_THUMBS}/*"),
    CleanTask("trash", "Trash",
              "Files in your desktop Trash.", False,
              # -mindepth 1 empties the contents (incl. bookkeeping) without a
              # dangerous glob; runs LAST so it also catches anything discarded
              # during this run.
              f"find {shlex.quote(_TRASH + '/files')} "
              f"{shlex.quote(_TRASH + '/info')} "
              f"{shlex.quote(_TRASH + '/expunged')} "
              f"-mindepth 1 -delete 2>/dev/null; "
              f"rm -f {shlex.quote(_TRASH + '/directorysizes')} 2>/dev/null; true"),
    CleanTask("journal", "Old system logs",
              "Vacuum the systemd journal to the last 7 days.", True,
              "journalctl --vacuum-time=7d"),
)


def tasks() -> tuple[CleanTask, ...]:
    return TASKS


# --------------------------------------------------------------- orphan purge
#
# This path exists because the naive version of this task did real damage. It
# used to run, unattended and unconfirmed:
#
#     deborphan | xargs -r apt-get -y purge
#
# deborphan lists libraries with no reverse dependencies, which sounds safe. But
# purging them *cascades*: apt also removes everything depending on them. On a
# live Mint 22.3 desktop, 27 "orphans" cascaded into 179 removed packages,
# including cinnamon, cinnamon-session, mint-meta-cinnamon, mint-meta-core, the
# NVIDIA driver and gir1.2-gtk-4.0 -- i.e. the desktop environment and the
# graphics stack, silently, behind one checkbox and one password prompt.
#
# Note that a priority/essential guard would NOT have caught it: cinnamon is
# Priority: optional, Essential: no. The only honest protection is to compute
# the real removal set with apt's own dry run and put it in front of the user,
# plus a hard refusal when session-critical packages appear in it.

# Packages whose removal would cost you your desktop, your login manager or your
# graphics driver. Matched as prefixes against the full cascade.
_CRITICAL_PREFIXES = (
    "cinnamon", "mint-meta-", "mint-common", "mintsystem", "mintdesktop",
    "nemo", "muffin", "xserver-xorg", "lightdm", "mdm", "gdm3", "sddm",
    "nvidia-driver", "xorg", "mesa-", "systemd", "network-manager",
)


def orphan_list() -> list[str]:
    """deborphan's candidates, normalised and validated.

    deborphan prints `name:arch` (e.g. `ftp:all`); the arch qualifier is
    stripped so names can be validated the same way every other package name
    in this app is.
    """
    from .pkg import partition_names

    raw = _sh("deborphan 2>/dev/null").split()
    names = [n.split(":", 1)[0] for n in raw if n.strip()]
    good, _bad = partition_names(names)
    return sorted(set(good))


def purge_preview(pkgs: list[str]) -> list[str]:
    """Every package apt would actually remove -- the true blast radius.

    Uses apt's own simulation, so the cascade is apt's answer rather than our
    guess. Returns the full removal set, which is normally much larger than
    `pkgs`.
    """
    from .pkg import validate_names

    if not pkgs:
        return []
    validate_names(pkgs)
    # apt's simulation marks a purge with `Purg <name>` and a plain removal with
    # `Remv <name>`; accept both. Getting this prefix wrong is dangerous in the
    # worst direction -- an unmatched prefix yields an EMPTY preview, which reads
    # to the user as "nothing will be removed" immediately before apt removes
    # everything. The preview is only a safeguard if it can never silently
    # under-report, so purge_preview_failed() distinguishes "nothing to do" from
    # "could not determine", and the view refuses to proceed on the latter.
    out = _sh("apt-get -s purge -- " + " ".join(shlex.quote(p) for p in pkgs),
              timeout=60)
    removed = []
    for line in out.splitlines():
        if line.startswith(("Purg ", "Remv ")):
            parts = line.split()
            if len(parts) > 1:
                removed.append(parts[1])
    return sorted(set(removed))


def purge_preview_failed(pkgs: list[str], preview: list[str]) -> bool:
    """True when a preview cannot be trusted, so the caller must not proceed.

    Asking to purge real packages and being told nothing would be removed means
    the simulation failed (apt missing, timeout, output format changed) rather
    than that the operation is a no-op.
    """
    return bool(pkgs) and not preview


def critical_in(removals: list[str]) -> list[str]:
    """Session-critical packages inside a removal set (empty == safe to offer)."""
    hits = [p for p in removals
            if any(p.startswith(pre) for pre in _CRITICAL_PREFIXES)]
    return sorted(set(hits))


def orphan_purge_argv(pkgs: list[str]) -> list[str]:
    """Elevated argv for a purge the user has seen in full and confirmed."""
    from .pkg import validate_names

    validate_names(pkgs)
    return ["pkexec", "apt-get", "purge", "-y", "--", *pkgs]
