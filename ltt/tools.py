"""Cross-launch the sibling tools (integration by launch, not merge — P2).

Mint Mechanic never absorbs disk-recovery-tool or workstation-dashboard; it
launches them when installed. When one isn't installed, the menu item stays
enabled but offers to point the user at its project page / install command —
Mint Mechanic never downloads or runs a remote installer itself (that would mean
executing remote code as root, against this app's whole no-blanket-root ethos).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class SiblingTool:
    key: str
    name: str
    commands: tuple[str, ...]   # launcher command candidates on PATH
    repo_url: str
    install_command: str        # the git clone + install one-liner
    blurb: str                  # one line: what it is

    def installed_command(self) -> str | None:
        for c in self.commands:
            path = shutil.which(c)
            if path:
                return path
        return None


SIBLINGS: tuple[SiblingTool, ...] = (
    SiblingTool(
        key="drt",
        name="Disk Recovery Tool",
        commands=("recovery-tool",),
        repo_url="https://github.com/rcraig57/disk-recovery-tool",
        install_command=(
            "git clone https://github.com/rcraig57/disk-recovery-tool && "
            "cd disk-recovery-tool && sudo ./install.sh"),
        blurb="Full-disk backup & restore with partclone — the heavy, "
              "root-level job, kept in its own app.",
    ),
    SiblingTool(
        key="dashboard",
        name="Workstation Dashboard",
        commands=("workstation-dashboard",),
        repo_url="https://github.com/rclinux/workstation-dashboard",
        install_command=(
            "git clone https://github.com/rclinux/workstation-dashboard && "
            "cd workstation-dashboard && sudo ./install.sh"),
        blurb="A read-only GO/NO-GO hardware health panel for your machine.",
    ),
)


def launch(command: str) -> bool:
    """Start `command` detached from this process."""
    try:
        subprocess.Popen([command], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False
