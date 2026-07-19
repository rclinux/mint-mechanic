"""The shared removal-preview guard in ltt.pkg.

Both the Cleaner's orphan purge and the Uninstaller route through this, so it is
tested here once against the properties that matter, independent of either view.

The Uninstaller had the same defect the Cleaner did: it went straight from click
to `pkexec apt-get remove -y` with no preview and no confirmation. Selecting one
package does not mean removing one package -- on a live Mint 22.3 box,
`apt-get -s remove -y cinnamon` removes 4, including mint-meta-cinnamon.
"""

import pytest

from ltt.pkg import (
    CRITICAL_PREFIXES,
    InvalidPackageName,
    critical_in,
    preview_failed,
    removal_preview,
)

# What apt really answers for `remove cinnamon` on Mint 22.3.
CINNAMON_CASCADE = """\
Remv blueman [2.4.4+mint2+xia]
Remv cinnamon-dbg [6.6.7+zena]
Remv mint-meta-cinnamon [2025.12.15+mint22.3]
Remv cinnamon [6.6.7+zena]
"""

HARMLESS = "Remv ftp [1.0]\nRemv telnet [2.0]\n"


def fake_apt(monkeypatch, stdout, *, fails=False):
    def run(*a, **k):
        if fails:
            raise OSError("apt-get missing")
        return type("P", (), {"stdout": stdout, "returncode": 0})()
    monkeypatch.setattr("ltt.pkg.subprocess.run", run)


# ------------------------------------------------------------------- cascade
def test_one_selection_can_mean_several_removals(monkeypatch):
    fake_apt(monkeypatch, CINNAMON_CASCADE)
    preview = removal_preview(["cinnamon"])
    assert len(preview) == 4
    assert "mint-meta-cinnamon" in preview


def test_uninstalling_cinnamon_is_refused(monkeypatch):
    """The Uninstaller's equivalent of the Cleaner disaster."""
    fake_apt(monkeypatch, CINNAMON_CASCADE)
    critical = critical_in(removal_preview(["cinnamon"]))
    assert "cinnamon" in critical
    assert "mint-meta-cinnamon" in critical


def test_purge_and_remove_use_the_right_verb(monkeypatch):
    seen = {}

    def run(argv, **k):
        seen["argv"] = argv
        return type("P", (), {"stdout": HARMLESS, "returncode": 0})()

    monkeypatch.setattr("ltt.pkg.subprocess.run", run)
    removal_preview(["ftp"], purge=False)
    assert seen["argv"][:3] == ["apt-get", "-s", "remove"]
    removal_preview(["ftp"], purge=True)
    assert seen["argv"][:3] == ["apt-get", "-s", "purge"]


def test_preview_terminates_options(monkeypatch):
    seen = {}

    def run(argv, **k):
        seen["argv"] = argv
        return type("P", (), {"stdout": HARMLESS, "returncode": 0})()

    monkeypatch.setattr("ltt.pkg.subprocess.run", run)
    removal_preview(["ftp"])
    assert "--" in seen["argv"]
    assert seen["argv"].index("--") < seen["argv"].index("ftp")


def test_preview_validates_names(monkeypatch):
    fake_apt(monkeypatch, "")
    with pytest.raises(InvalidPackageName):
        removal_preview(["-o", "APT::Update::Pre-Invoke::=touch /tmp/x"])


def test_preview_of_nothing_is_empty(monkeypatch):
    fake_apt(monkeypatch, "")
    assert removal_preview([]) == []


# -------------------------------------------------------------- trustworthiness
def test_apt_blowing_up_yields_a_failed_preview(monkeypatch):
    fake_apt(monkeypatch, "", fails=True)
    pkgs = ["ftp"]
    assert preview_failed(pkgs, removal_preview(pkgs)) is True


def test_unrecognised_output_yields_a_failed_preview(monkeypatch):
    """If apt's output format ever changes, fail closed, not open."""
    fake_apt(monkeypatch, "Removing ftp ...\nDeleting telnet ...\n")
    pkgs = ["ftp", "telnet"]
    assert preview_failed(pkgs, removal_preview(pkgs)) is True


def test_a_good_preview_is_trusted(monkeypatch):
    fake_apt(monkeypatch, HARMLESS)
    pkgs = ["ftp", "telnet"]
    assert preview_failed(pkgs, removal_preview(pkgs)) is False


# --------------------------------------------------------------------- guard
def test_harmless_removals_are_permitted(monkeypatch):
    fake_apt(monkeypatch, HARMLESS)
    assert critical_in(removal_preview(["ftp", "telnet"])) == []


def test_guard_covers_desktop_login_and_graphics():
    """Each prefix must actually match something plausible."""
    samples = {
        "cinnamon": "cinnamon-session",
        "mint-meta-": "mint-meta-core",
        "xserver-xorg": "xserver-xorg-core",
        "lightdm": "lightdm",
        "nvidia-driver": "nvidia-driver-595-open",
        "systemd": "systemd",
        "network-manager": "network-manager",
    }
    for prefix, example in samples.items():
        assert prefix in CRITICAL_PREFIXES
        assert critical_in([example]) == [example]


def test_guard_is_deduplicated_and_sorted():
    assert critical_in(["cinnamon", "cinnamon", "lightdm"]) == [
        "cinnamon", "lightdm"]


# ------------------------------------------------- desktops beyond Cinnamon
#
# The guard started Mint-shaped. The PPA makes it likely someone runs this on
# MATE, XFCE, KDE or GNOME, where the same cascade would be just as fatal.

@pytest.mark.parametrize("pkg", [
    # MATE
    "mate-session-manager", "mate-panel", "mate-settings-daemon",
    "mate-desktop", "mate-desktop-environment", "marco", "caja",
    "ubuntu-mate-desktop",
    # XFCE
    "xfce4", "xfce4-session", "xfce4-panel", "xfce4-settings",
    "xfdesktop4", "xfwm4", "xubuntu-desktop",
    # KDE Plasma
    "plasma-desktop", "plasma-workspace", "kde-plasma-desktop",
    "kubuntu-desktop", "kwin-x11", "kwin-wayland", "kwin-common",
    # GNOME
    "gnome-shell", "gnome-session", "mutter", "ubuntu-desktop",
    # Budgie / LXQt / LXDE
    "budgie-desktop", "lxqt-session", "lxsession", "lubuntu-desktop",
    # Display managers
    "lxdm", "slim", "lightdm", "gdm3", "sddm",
])
def test_other_desktops_are_protected(pkg):
    assert critical_in([pkg]) == [pkg]


@pytest.mark.parametrize("pkg", [
    "libgl1-mesa-dri",      # the actual DRI driver
    "libglx-mesa0",         # the GLX provider
    "mesa-va-drivers",
    "mesa-vulkan-drivers",
    "xserver-xorg-core",
    "nvidia-driver-595-open",
])
def test_graphics_stack_is_protected(pkg):
    """`mesa-` as a prefix used to catch mesa-utils and MISS libgl1-mesa-dri --
    protecting a diagnostic tool while leaving the real driver exposed."""
    assert critical_in([pkg]) == [pkg]


@pytest.mark.parametrize("pkg", [
    # A broad `mate-` / `xfce4` prefix would wrongly catch every one of these.
    "mate-calc", "mate-applets", "mate-backgrounds", "mate-themes",
    "xfce4-eyes-plugin", "xfce4-clipman", "xfce4-terminal",
    "xfce4-taskmanager", "xfce4-screenshooter",
    # nemo is critical; its optional extensions are not.
    "nemo-emblems", "nemo-preview",
    # mesa-utils is a diagnostic, not a driver.
    "mesa-utils",
    # Ordinary applications.
    "gnome-calculator", "vlc", "htop", "thunderbird", "ftp", "telnet",
])
def test_ordinary_packages_are_not_refused(pkg):
    """A guard that cries wolf gets ignored, and an ignored guard protects
    nothing. Refusing to uninstall a calculator is a real cost."""
    assert critical_in([pkg]) == []


def test_every_exact_entry_is_a_valid_package_name():
    """Entries are compared against apt output, so a typo silently never matches."""
    from ltt.pkg import CRITICAL_PACKAGES, _VALID_NAME
    bad = [p for p in CRITICAL_PACKAGES if not _VALID_NAME.match(p)]
    assert bad == []


# =========================================================================
# Live-session guard: protect what is RUNNING, not only what is on the list.
#
# The static CRITICAL_* catalogue can only protect desktops we thought to
# name -- its one residual hole is an exotic desktop that never made the
# list. live_critical_packages() closes that hole by asking the live system
# what is actually drawing the screen. These tests pin BOTH directions: the
# running session is refused however exotic, and the layer never loosens the
# static guard nor cries wolf over ordinary applications.
# =========================================================================

from ltt.pkg import live_critical_packages


# --------------------------------------------------- union logic (pure, no I/O)
def test_live_layer_catches_a_desktop_the_denylist_misses():
    """The whole point: a desktop nobody put on the static list is still
    refused when it is the one running. `enlightenment` is on neither
    CRITICAL_PACKAGES nor CRITICAL_PREFIXES."""
    exotic = "enlightenment"
    assert critical_in([exotic]) == []                       # was a hole...
    assert critical_in([exotic], live={exotic}) == [exotic]  # ...now closed


def test_live_layer_never_loosens_the_denylist():
    """A detection miss (empty or absent live) leaves the static guard intact.
    The layer can only ever refuse MORE, never less."""
    assert critical_in(["cinnamon"], live=set()) == ["cinnamon"]
    assert critical_in(["cinnamon"], live=None) == ["cinnamon"]
    assert critical_in(["cinnamon"]) == ["cinnamon"]


def test_live_layer_does_not_refuse_ordinary_packages():
    """live is only the running session; unrelated apps stay removable even
    while a live set is in force."""
    assert critical_in(["vlc", "htop"],
                       live={"cinnamon-common", "lightdm"}) == []


def test_live_union_is_deduplicated_and_sorted():
    """Names the live layer supplies (here not on the static list) merge, dedupe
    and sort alongside any static hits."""
    result = critical_in(["vlc", "icewm", "awesome", "icewm"],
                         live={"icewm", "awesome"})
    assert result == ["awesome", "icewm"]


# ------------------------------------------------------- the probe (system I/O)
def _fake_system(monkeypatch, *, execstart="", owns=None, exists=()):
    """Simulate the probe's three system touch-points: `systemctl show` for the
    display-manager ExecStart, `dpkg -S` for path ownership (owns: path ->
    package; anything absent answers rc 1 like a real unowned path), and which
    session .desktop files exist."""
    owns = owns or {}

    def run(argv, **k):
        if argv[:2] == ["systemctl", "show"]:
            return type("P", (), {"stdout": execstart, "returncode": 0})()
        if argv[:2] == ["dpkg", "-S"]:
            path = argv[2]
            if path in owns:
                return type("P", (), {
                    "stdout": f"{owns[path]}: {path}\n", "returncode": 0})()
            return type("P", (), {"stdout": "", "returncode": 1})()
        return type("P", (), {"stdout": "", "returncode": 0})()

    monkeypatch.setattr("ltt.pkg.subprocess.run", run)
    monkeypatch.setattr("ltt.pkg.os.path.exists", lambda p: p in exists)


def test_probe_detects_display_manager_and_session(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_DESKTOP", "cinnamon")
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    _fake_system(
        monkeypatch,
        execstart=("{ path=/usr/sbin/lightdm ; argv[]=/usr/sbin/lightdm ; "
                   "ignore_errors=no ; status=0/0 }"),
        owns={"/usr/sbin/lightdm": "lightdm",
              "/usr/share/xsessions/cinnamon.desktop": "cinnamon-common"},
        exists={"/usr/share/xsessions/cinnamon.desktop"},
    )
    assert live_critical_packages() == {"lightdm", "cinnamon-common"}


def test_probe_ignores_a_dkms_driver_dpkg_does_not_own(monkeypatch):
    """A running driver whose .ko belongs to no package contributes nothing --
    it must neither fabricate a name nor raise. (dpkg -S on any path but the DM
    binary answers rc 1 here.)"""
    monkeypatch.delenv("XDG_SESSION_DESKTOP", raising=False)
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    _fake_system(
        monkeypatch,
        execstart="{ path=/usr/sbin/lightdm ; argv[]=/usr/sbin/lightdm }",
        owns={"/usr/sbin/lightdm": "lightdm"},
        exists=set(),
    )
    assert live_critical_packages() == {"lightdm"}


def test_probe_survives_missing_systemctl(monkeypatch):
    """No systemd, or any probe failure, must yield an empty set -- never an
    exception that would crash the preview worker thread."""
    monkeypatch.delenv("XDG_SESSION_DESKTOP", raising=False)
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)

    def boom(*a, **k):
        raise OSError("systemctl missing")

    monkeypatch.setattr("ltt.pkg.subprocess.run", boom)
    monkeypatch.setattr("ltt.pkg.os.path.exists", lambda p: False)
    assert live_critical_packages() == set()


def test_probe_resolves_colon_joined_current_desktop(monkeypatch):
    """XDG_CURRENT_DESKTOP='ubuntu:GNOME' must resolve to the 'ubuntu' session
    (split on ':'), falling back to it when XDG_SESSION_DESKTOP is unset."""
    monkeypatch.delenv("XDG_SESSION_DESKTOP", raising=False)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "ubuntu:GNOME")
    _fake_system(
        monkeypatch,
        execstart="",
        owns={"/usr/share/xsessions/ubuntu.desktop": "gnome-session-common"},
        exists={"/usr/share/xsessions/ubuntu.desktop"},
    )
    assert live_critical_packages() == {"gnome-session-common"}


def test_probe_strips_x_dash_prefix(monkeypatch):
    """The real Cinnamon box reports XDG_CURRENT_DESKTOP='X-Cinnamon'; the
    'X-' vendor prefix must be stripped to find cinnamon.desktop."""
    monkeypatch.delenv("XDG_SESSION_DESKTOP", raising=False)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "X-Cinnamon")
    _fake_system(
        monkeypatch,
        execstart="",
        owns={"/usr/share/xsessions/cinnamon.desktop": "cinnamon-common"},
        exists={"/usr/share/xsessions/cinnamon.desktop"},
    )
    assert live_critical_packages() == {"cinnamon-common"}
