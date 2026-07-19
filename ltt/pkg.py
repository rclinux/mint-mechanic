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

import re
import shutil
import subprocess
from dataclasses import dataclass

# Debian policy 5.6.1: package names are at least two characters, lowercase
# alphanumerics plus '+', '-', '.', and must start with an alphanumeric.
_VALID_NAME = re.compile(r"^[a-z0-9][a-z0-9+.\-]+$")


class InvalidPackageName(ValueError):
    """Raised when a name bound for an elevated apt call fails validation.

    Package lists do not always originate on this machine: a Streamline profile
    is explicitly a portable, hand-editable manifest meant to be carried between
    systems. That makes it untrusted input. apt-get parses options wherever they
    appear — including in the package-name position — so an unvalidated name
    like `-o` followed by `APT::Update::Pre-Invoke::=<command>` becomes
    arbitrary command execution under the pkexec prompt, which the user reads as
    an ordinary package install. Names are validated here, at the one seam every
    package operation passes through, and the argv adds a `--` terminator so
    nothing downstream can be re-read as an option.
    """

    def __init__(self, names: list[str]) -> None:
        self.names = names
        shown = ", ".join(repr(n) for n in names[:3])
        more = f" (+{len(names) - 3} more)" if len(names) > 3 else ""
        super().__init__(f"invalid package name(s): {shown}{more}")


def validate_names(pkgs: list[str]) -> list[str]:
    """Return `pkgs` unchanged, or raise InvalidPackageName listing the bad ones."""
    bad = [p for p in pkgs if not _VALID_NAME.match(p)]
    if bad:
        raise InvalidPackageName(bad)
    return pkgs


def partition_names(pkgs: list[str]) -> tuple[list[str], list[str]]:
    """Split into (valid, rejected) so a caller can report rather than abort."""
    good = [p for p in pkgs if _VALID_NAME.match(p)]
    bad = [p for p in pkgs if not _VALID_NAME.match(p)]
    return good, bad


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
        # mapping lives in exactly one place. Names are validated and `--`
        # terminates options — see InvalidPackageName for why that matters.
        validate_names(pkgs)
        return ["pkexec", "apt-get", "install", "-y", "--", *pkgs]

    def remove_argv(self, pkgs: list[str], purge: bool = False) -> list[str]:
        verb = "purge" if purge else "remove"
        validate_names(pkgs)
        return ["pkexec", "apt-get", verb, "-y", "--", *pkgs]


def default_backend() -> PackageBackend:
    """Pick the backend for this host. Mint => apt; the seam is the point."""
    if shutil.which("apt-get"):
        return AptBackend()
    raise RuntimeError("No supported package backend found (v1 is apt-only).")
