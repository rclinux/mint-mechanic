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

import os
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


# ------------------------------------------------------- removal blast radius
#
# Every path that removes packages must show what apt will ACTUALLY do before it
# does it. This lives here, at the one package seam (P5), because both the
# Cleaner's orphan purge and the Uninstaller need it and must not drift apart.
#
# Why this exists: the Cleaner once ran `deborphan | xargs -r apt-get -y purge`
# unattended. deborphan named 27 libraries; apt's cascade removed 179 packages
# including cinnamon, cinnamon-session, mint-meta-core, the NVIDIA driver and
# gir1.2-gtk-4.0 -- the desktop environment and graphics stack -- from a single
# checkbox. The user's shortlist is never the blast radius; only apt's own dry
# run is.
#
# An Essential/Priority guard does NOT substitute for this: cinnamon is
# Priority: optional, Essential: no.

# Packages whose removal costs you your desktop, your login manager or your
# graphics driver.
#
# Two lists, because one shape does not fit both cases:
#
#   * PREFIXES for families where every member is genuinely part of the session
#     (all `cinnamon*`, every `xserver-xorg*` driver, every `nvidia-driver*`).
#   * EXACT names everywhere a prefix would over-match. `mate-` would match all
#     68 mate-* packages including mate-calc; `xfce4` would match all 53
#     including xfce4-eyes-plugin. Refusing to let someone uninstall a
#     calculator teaches them to ignore the guard, and a guard that is ignored
#     protects nothing.
#
# `mesa-` was deliberately REMOVED as a prefix: it matched mesa-utils (a
# harmless diagnostic) while missing libgl1-mesa-dri and libglx-mesa0 -- the
# actual drivers. It protected the toy and not the thing that matters.
CRITICAL_PREFIXES = (
    # Cinnamon / Mint (this tool's home turf)
    "cinnamon", "muffin", "mint-meta-", "mint-common", "mintsystem",
    "mintdesktop",
    # KWin: every kwin* package is Plasma compositor infrastructure
    "kwin",
    # X, display managers, graphics drivers
    "xserver-xorg", "xorg", "lightdm", "gdm3", "sddm", "mdm",
    "nvidia-driver",
    # Core system plumbing
    "systemd", "network-manager",
)

# Exact names: desktop sessions, window managers, panels and session metapackages
# across the desktops someone might actually be running, plus the graphics
# libraries whose names don't share a usable prefix.
CRITICAL_PACKAGES = frozenset({
    # Cinnamon (the file manager; nemo-* extensions stay removable)
    "nemo",
    # MATE
    "mate-session-manager", "mate-panel", "mate-settings-daemon",
    "mate-desktop", "mate-desktop-environment", "mate-core",
    "marco", "caja", "ubuntu-mate-desktop",
    # XFCE
    "xfce4", "xfce4-session", "xfce4-panel", "xfce4-settings",
    "xfdesktop4", "xfwm4", "xubuntu-desktop",
    # KDE Plasma
    "plasma-desktop", "plasma-workspace", "kde-plasma-desktop",
    "kubuntu-desktop",
    # GNOME
    "gnome-shell", "gnome-session", "mutter", "ubuntu-desktop",
    # Budgie / LXQt / LXDE
    "budgie-desktop", "ubuntu-budgie-desktop",
    "lxqt-session", "lxsession", "lubuntu-desktop",
    # Display managers without a safe prefix
    "lxdm", "slim",
    # Graphics libraries the prefixes miss
    "libgl1-mesa-dri", "libglx-mesa0", "mesa-va-drivers",
    "mesa-vulkan-drivers",
})


def _pkg_owning(path: str) -> str | None:
    """The package that owns an on-disk path (via `dpkg -S`), or None.

    Returns None for anything dpkg does not own -- e.g. a DKMS kernel module,
    whose .ko is built locally and belongs to no package -- so an unowned probe
    result simply contributes no protection rather than a wrong or empty name.
    """
    try:
        out = subprocess.run(
            ["dpkg", "-S", path],
            capture_output=True, text=True, timeout=10, check=False)
    except (subprocess.SubprocessError, OSError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    # "cinnamon-common: /usr/share/xsessions/cinnamon.desktop" -> "cinnamon-common"
    first = out.stdout.strip().splitlines()[0]
    name = first.split(":", 1)[0].strip()
    return name or None


def live_critical_packages() -> set[str]:
    """Packages the CURRENTLY RUNNING session depends on, on THIS machine.

    The static CRITICAL_* lists can only protect desktops we thought to name.
    This asks the self-updating question instead -- what is drawing the screen
    right now? -- so an exotic desktop that never made the list is still caught,
    because it is the one running. Purely additive: a detection miss yields an
    empty set and the static denylist still applies, so this can only ever
    refuse MORE, never less. Injected into critical_in() rather than called
    inside it, so that function stays pure and this probes the system once.

    Covers the two facts that map cleanly to a package -- the active display
    manager and the running desktop session. Graphics drivers are deliberately
    NOT probed: the in-use driver is often a DKMS module dpkg does not own (on
    this box `nvidia.ko` lives under updates/dkms and maps to no package), so it
    would contribute nothing. The graphics libraries stay on the static
    CRITICAL_PACKAGES list, which is reliable.
    """
    live: set[str] = set()

    # 1. Active display manager: unit -> its ExecStart binary -> owning package.
    #    systemd resolves display-manager.service to whichever DM is running
    #    (lightdm, gdm3, sddm, ...), so we never hardcode the DM.
    try:
        execstart = subprocess.run(
            ["systemctl", "show", "-p", "ExecStart", "--value",
             "display-manager.service"],
            capture_output=True, text=True, timeout=10, check=False).stdout
    except (subprocess.SubprocessError, OSError):
        execstart = ""
    # systemd prints ExecStart as "{ path=/usr/sbin/lightdm ; argv[]=... }",
    # NOT a bare path, so read the path= field rather than scanning for a
    # leading slash (which silently matched nothing and dropped the DM).
    dm_path = re.search(r"path=(\S+)", execstart)
    if dm_path and (owner := _pkg_owning(dm_path.group(1))):
        live.add(owner)

    # 2. Running desktop session: XDG_*_DESKTOP -> its session .desktop file ->
    #    owning package. "X-Cinnamon"/"cinnamon" -> cinnamon.desktop ->
    #    cinnamon-common. Prefer XDG_SESSION_DESKTOP (a clean single token) over
    #    XDG_CURRENT_DESKTOP (may be colon-joined, e.g. "ubuntu:GNOME").
    desktop = (os.environ.get("XDG_SESSION_DESKTOP")
               or os.environ.get("XDG_CURRENT_DESKTOP", ""))
    desktop = desktop.lower().split(":")[0].removeprefix("x-").strip()
    if desktop:
        for base in ("/usr/share/xsessions", "/usr/share/wayland-sessions"):
            sess = f"{base}/{desktop}.desktop"
            if os.path.exists(sess) and (owner := _pkg_owning(sess)):
                live.add(owner)

    return live


def critical_in(removals: list[str], live: set[str] | None = None) -> list[str]:
    """Session-critical packages inside a removal set (empty == safe to offer).

    Two layers, unioned:
      * the static CRITICAL_PACKAGES / CRITICAL_PREFIXES catalogue below, and
      * `live` -- packages this machine's currently running desktop and login
        manager depend on, as detected by live_critical_packages().
    `live` is injected rather than fetched here so this function stays pure (the
    unit tests rely on that) and the callers probe the system once per open.
    Default None means denylist-only -- the original behaviour.
    """
    live = live or set()
    hits = [p for p in removals
            if p in CRITICAL_PACKAGES
            or p in live
            or any(p.startswith(pre) for pre in CRITICAL_PREFIXES)]
    return sorted(set(hits))


def removal_preview(pkgs: list[str], purge: bool = False) -> list[str]:
    """Every package apt would actually remove -- the true blast radius.

    Runs apt's own simulation, so the cascade is apt's answer rather than our
    guess. The returned set is normally much larger than `pkgs`.
    """
    if not pkgs:
        return []
    validate_names(pkgs)
    verb = "purge" if purge else "remove"
    try:
        out = subprocess.run(
            ["apt-get", "-s", verb, "--", *pkgs],
            capture_output=True, text=True, timeout=60, check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return []
    # apt marks a purge `Purg <name>` and a plain removal `Remv <name>`; accept
    # both. Matching only one prefix yields an EMPTY preview, which reads to the
    # user as "nothing will be removed" immediately before apt removes
    # everything -- see preview_failed(), which makes that unrepresentable.
    removed = []
    for line in out.stdout.splitlines():
        if line.startswith(("Purg ", "Remv ")):
            parts = line.split()
            if len(parts) > 1:
                removed.append(parts[1])
    return sorted(set(removed))


def preview_failed(pkgs: list[str], preview: list[str]) -> bool:
    """True when a preview cannot be trusted, so the caller must not proceed.

    Asking to remove real packages and being told nothing would go means the
    simulation failed (apt missing, timeout, output format changed) rather than
    that the operation is a no-op. Callers must treat this as a hard stop.
    """
    return bool(pkgs) and not preview


def default_backend() -> PackageBackend:
    """Pick the backend for this host. Mint => apt; the seam is the point."""
    if shutil.which("apt-get"):
        return AptBackend()
    raise RuntimeError("No supported package backend found (v1 is apt-only).")
