"""Tests for the single apt seam — above all, that nothing unvalidated can
reach an elevated apt-get call.

These are the regression tests for the profile-import injection: apt-get parses
options wherever they appear, including in the package-name position, so a
manifest line of `-o` followed by `APT::Update::Pre-Invoke::=<cmd>` used to
become arbitrary root command execution behind an ordinary-looking polkit
prompt.
"""

import pytest

from ltt.pkg import (
    AptBackend,
    InvalidPackageName,
    partition_names,
    validate_names,
)


@pytest.fixture
def apt():
    return AptBackend()


# --------------------------------------------------------------- name rules
@pytest.mark.parametrize("name", [
    "htop",
    "python3",
    "python3-gi",
    "gir1.2-gtk-4.0",
    "libgtk-4-1",
    "g++",
    "0ad",
])
def test_accepts_real_package_names(name):
    assert validate_names([name]) == [name]


@pytest.mark.parametrize("name", [
    "-o",                                   # bare option
    "--option=x",                           # long option
    "-oAPT::Update::Pre-Invoke::=touch /x",  # attached-value option
    "APT::Update::Pre-Invoke::=touch /x",   # the payload half
    "pkg; rm -rf /",                        # shell metacharacters
    "pkg name",                             # embedded space
    "Uppercase",                            # not lowercase
    ".hidden",                              # must start alphanumeric
    "a",                                    # policy minimum is 2 chars
    "",                                     # empty line
])
def test_rejects_non_package_names(name):
    with pytest.raises(InvalidPackageName):
        validate_names([name])


def test_error_lists_the_offending_names():
    with pytest.raises(InvalidPackageName) as excinfo:
        validate_names(["htop", "-o", "--force"])
    assert excinfo.value.names == ["-o", "--force"]


# ------------------------------------------------------------ argv building
def test_install_argv_terminates_options(apt):
    argv = apt.install_argv(["htop", "vim"])
    assert argv == ["pkexec", "apt-get", "install", "-y", "--", "htop", "vim"]
    # `--` must precede every package name, or a name could still be re-read
    # as an option by apt-get.
    assert argv.index("--") < argv.index("htop")


def test_remove_argv_terminates_options(apt):
    assert apt.remove_argv(["htop"]) == [
        "pkexec", "apt-get", "remove", "-y", "--", "htop"]
    assert apt.remove_argv(["htop"], purge=True) == [
        "pkexec", "apt-get", "purge", "-y", "--", "htop"]


def test_install_argv_refuses_injected_option(apt):
    """The exact payload from the original finding."""
    evil = ["htop", "-o", "APT::Update::Pre-Invoke::=touch /tmp/OWNED"]
    with pytest.raises(InvalidPackageName):
        apt.install_argv(evil)


def test_remove_argv_refuses_injected_option(apt):
    with pytest.raises(InvalidPackageName):
        apt.remove_argv(["-o", "APT::Update::Pre-Invoke::=touch /tmp/OWNED"])


def test_mutating_argv_always_elevates(apt):
    """Mutations go through pkexec; the app itself never runs as root."""
    for argv in (apt.install_argv(["htop"]), apt.remove_argv(["htop"])):
        assert argv[0] == "pkexec"


# -------------------------------------------------------------- partitioning
def test_partition_splits_good_from_bad():
    good, bad = partition_names(["htop", "-o", "vim", "pkg; rm -rf /"])
    assert good == ["htop", "vim"]
    assert bad == ["-o", "pkg; rm -rf /"]


def test_partition_preserves_order():
    good, _ = partition_names(["zsh", "apache2", "htop"])
    assert good == ["zsh", "apache2", "htop"]


def test_partition_never_raises_on_hostile_input():
    good, bad = partition_names(["--force-yes", "-o", ""])
    assert good == []
    assert len(bad) == 3


# ----------------------------------------------------------------- parsing
def test_installed_set_parses_dpkg_status(monkeypatch):
    fixture = (
        "installed htop\n"
        "config-files removed-pkg\n"
        "installed vim\n"
        "not-installed never-here\n"
    )
    monkeypatch.setattr(
        "ltt.pkg.subprocess.run",
        lambda *a, **k: type("P", (), {"stdout": fixture, "returncode": 0})(),
    )
    assert AptBackend().installed_set() == {"htop", "vim"}


def test_is_installed_requires_clean_status(monkeypatch):
    def fake(stdout, rc):
        return lambda *a, **k: type("P", (), {"stdout": stdout, "returncode": rc})()

    monkeypatch.setattr("ltt.pkg.subprocess.run", fake("installed", 0))
    assert AptBackend().is_installed("htop") is True

    monkeypatch.setattr("ltt.pkg.subprocess.run", fake("config-files", 0))
    assert AptBackend().is_installed("htop") is False

    monkeypatch.setattr("ltt.pkg.subprocess.run", fake("", 1))
    assert AptBackend().is_installed("nope") is False


def test_list_manual_is_sorted_and_dropped_blanks(monkeypatch):
    monkeypatch.setattr(
        "ltt.pkg.subprocess.run",
        lambda *a, **k: type("P", (), {"stdout": "vim\nhtop\n\nzsh\n", "returncode": 0})(),
    )
    assert AptBackend().list_manual() == ["htop", "vim", "zsh"]
