"""The app's version and the package's version must never disagree.

`config.APP_VERSION` is what the About dialog shows; `debian/changelog` is what
apt, the PPA and Launchpad consider authoritative. They are edited in different
files by different reflexes, so nothing but a test keeps them honest.

This matters more than it looks: a user reporting a bug reads the About dialog,
while the maintainer reads `dpkg -l`. If those two numbers drift, every bug
report becomes ambiguous about which code is actually running -- which is
exactly the confusion that cost real time when a running 0.2.0 process reported
itself while 0.4.0 was installed on disk.
"""

import re
import subprocess
from pathlib import Path

from ltt import config

REPO = Path(__file__).resolve().parent.parent


def changelog_version() -> str:
    """The version at the top of debian/changelog."""
    changelog = REPO / "debian" / "changelog"
    first = changelog.read_text(encoding="utf-8").splitlines()[0]
    match = re.match(r"^\S+ \(([^)]+)\)", first)
    assert match, f"unparseable changelog header: {first!r}"
    return match.group(1)


def test_app_version_matches_debian_changelog():
    assert config.APP_VERSION == changelog_version(), (
        "ltt/config.py APP_VERSION and debian/changelog disagree — bump both"
    )


def test_manpage_version_matches():
    """The man page header carries the version too."""
    man = (REPO / "data" / "mint-mechanic.1").read_text(encoding="utf-8")
    assert f"Mint Mechanic {config.APP_VERSION}" in man.splitlines()[0], (
        "data/mint-mechanic.1 header version is stale"
    )


def test_readme_install_line_matches():
    """The README's copy-pasteable install command must name a real file."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    expected = f"mint-mechanic_{config.APP_VERSION}_all.deb"
    assert expected in readme, f"README install line does not mention {expected}"


def test_metainfo_has_an_entry_for_this_release():
    """Software centres show the newest <release>; it must exist."""
    meta = (REPO / "data" / "io.github.rclinux.MintMechanic.metainfo.xml")
    assert f'version="{config.APP_VERSION}"' in meta.read_text(encoding="utf-8"), (
        "no <release> entry in the AppStream metainfo for this version"
    )


def test_changelog_targets_a_real_ubuntu_series():
    """A PPA upload is rejected outright if the series is wrong.

    Mint 22.x is built on Ubuntu 24.04 'noble'; UNRELEASED never uploads.
    """
    dist = subprocess.run(
        ["dpkg-parsechangelog", "-S", "Distribution"],
        cwd=REPO, capture_output=True, text=True, check=False,
    ).stdout.strip()
    assert dist in {"noble", "jammy", "oracular", "plucky", "questing"}, (
        f"debian/changelog targets {dist!r}, which is not an Ubuntu series"
    )


def test_package_name_is_consistent():
    src = subprocess.run(
        ["dpkg-parsechangelog", "-S", "Source"],
        cwd=REPO, capture_output=True, text=True, check=False,
    ).stdout.strip()
    assert src == config.APP_COMMAND == "mint-mechanic"
