"""The ONE package-manager abstraction (design principle P5).

Every install / remove / query / list-manual in Mint Mechanic routes through
this module — never a raw `apt`/`dpkg` call scattered in the UI. This is the
deliberate anti-ATT lesson: the Arch Linux Tweak Tool hardcodes pacman ~115
times across 44 files with no chokepoint, which is exactly why it can't be
ported. Here there is a single seam.

v1 is Mint-only, so `AptBackend` is the only implementation — but the surface
is generic (`PackageBackend`) so a dnf/pacman backend could slot in later as a
one-file drop-in rather than a hunt-and-replace.

Privilege rule: read-only queries run as the user; mutating operations
(install/remove) are elevated per-action via pkexec, never under a blanket-root
app. Phase 0 establishes the interface and the read-only paths; the mutating
paths build their argv here and are wired to execution in a later phase.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class PkgResult:
    """Outcome of a package operation (or a dry-run argv for a pending one)."""
    ok: bool
    argv: list[str]
    stdout: str = ""
    stderr: str = ""


class PackageBackend:
    """Abstract surface every backend implements. v1 ships AptBackend only."""

    name = "abstract"

    def list_manual(self) -> list[str]:
        raise NotImplementedError

    def installed_set(self) -> set[str]:
        raise NotImplementedError

    def is_installed(self, pkg: str) -> bool:
        raise NotImplementedError

    def install_argv(self, pkgs: list[str]) -> list[str]:
        raise NotImplementedError

    def remove_argv(self, pkgs: list[str], purge: bool = False) -> list[str]:
        raise NotImplementedError


class AptBackend(PackageBackend):
    """Debian/Ubuntu/Mint backend. Read-only paths are live in Phase 0."""

    name = "apt"

    def list_manual(self) -> list[str]:
        """Manually-installed packages — the basis of a Streamline profile."""
        out = subprocess.run(
            ["apt-mark", "showmanual"],
            capture_output=True, text=True, check=False,
        )
        return sorted(p for p in out.stdout.split() if p)

    def installed_set(self) -> set[str]:
        """All currently-installed package names, in one call (for import diffs)."""
        out = subprocess.run(
            ["dpkg-query", "-W", "-f=${db:Status-Status} ${Package}\n"],
            capture_output=True, text=True, check=False,
        )
        installed = set()
        for line in out.stdout.splitlines():
            status, _, name = line.partition(" ")
            if status == "installed" and name:
                installed.add(name)
        return installed

    def is_installed(self, pkg: str) -> bool:
        out = subprocess.run(
            ["dpkg-query", "-W", "-f=${db:Status-Status}", pkg],
            capture_output=True, text=True, check=False,
        )
        return out.returncode == 0 and out.stdout.strip() == "installed"

    def install_argv(self, pkgs: list[str]) -> list[str]:
        # Elevated per-action at call time (Phase 3+). Built here so the verb
        # mapping lives in exactly one place.
        return ["pkexec", "apt-get", "install", "-y", *pkgs]

    def remove_argv(self, pkgs: list[str], purge: bool = False) -> list[str]:
        verb = "purge" if purge else "remove"
        return ["pkexec", "apt-get", verb, "-y", *pkgs]


def default_backend() -> PackageBackend:
    """Pick the backend for this host. Mint => apt; the seam is the point."""
    if shutil.which("apt-get"):
        return AptBackend()
    raise RuntimeError("No supported package backend found (v1 is apt-only).")
