"""Regression tests for the orphaned-package purge.

The naive version of this task ran `deborphan | xargs -r apt-get -y purge`
unattended. On a live Mint 22.3 desktop that removed 179 packages -- cinnamon,
cinnamon-session, mint-meta-cinnamon, mint-meta-core, the NVIDIA driver and
gir1.2-gtk-4.0 -- from 27 "orphans", behind a single checkbox.

These tests pin the three properties that make that impossible now:
  1. the preview reports apt's real cascade, not deborphan's shortlist;
  2. a cascade touching the desktop or graphics stack is refused outright;
  3. a preview that cannot be computed is never mistaken for "nothing to do".
"""

import pytest

from ltt import cleaner
from ltt.pkg import InvalidPackageName

# The real cascade observed on the damaged machine, trimmed to the essentials.
REAL_CASCADE = """\
Purg ftp [20230507-2build3]
Purg gir1.2-adw-1 [1.5.0-2mint3+zara]
Purg cinnamon [6.6.7+zena]
Purg cinnamon-session [6.6.3+zena]
Purg mint-meta-cinnamon [2025.12.15+mint22.3]
Purg mint-meta-core [2025.12.15+mint22.3]
Purg nvidia-driver-595-open [595.71.05-0ubuntu0.24.04.1]
Purg gir1.2-gtk-4.0 [4.14.5+ds-0ubuntu0.10]
"""

HARMLESS_CASCADE = """\
Purg ftp [20230507-2build3]
Purg telnet [0.17+2.5-3ubuntu4.2]
Purg p7zip [16.02+transitional.1]
"""


def fake_apt(monkeypatch, output):
    """Stand in for apt's simulation, which runs in ltt.pkg (the one seam)."""
    monkeypatch.setattr(
        "ltt.pkg.subprocess.run",
        lambda *a, **k: type("P", (), {"stdout": output, "returncode": 0})(),
    )


def fake_deborphan(monkeypatch, output):
    """Stand in for deborphan, which the Cleaner still shells out to itself."""
    monkeypatch.setattr(cleaner, "_sh", lambda cmd, timeout=8: output)


# ------------------------------------------------------------------ preview
def test_preview_reports_aptes_full_cascade(monkeypatch):
    """The whole point: 3 candidates, 8 actual removals."""
    fake_apt(monkeypatch, REAL_CASCADE)
    preview = cleaner.purge_preview(["ftp", "gir1.2-adw-1", "telnet"])
    assert len(preview) == 8
    assert "cinnamon" in preview
    assert "mint-meta-core" in preview


def test_preview_accepts_remv_as_well_as_purg(monkeypatch):
    """apt marks purges `Purg` and plain removals `Remv`; both count.

    Matching only one prefix yields an EMPTY preview -- which reads as
    'nothing will be removed' immediately before apt removes everything.
    """
    fake_apt(monkeypatch, "Remv foo [1.0]\nPurg bar [2.0]\n")
    assert cleaner.purge_preview(["foo"]) == ["bar", "foo"]


def test_preview_of_nothing_is_empty(monkeypatch):
    fake_apt(monkeypatch, "")
    assert cleaner.purge_preview([]) == []


def test_preview_validates_names(monkeypatch):
    fake_apt(monkeypatch, "")
    with pytest.raises(InvalidPackageName):
        cleaner.purge_preview(["-o", "APT::Update::Pre-Invoke::=touch /tmp/x"])


# ---------------------------------------------------------- failure detection
def test_empty_preview_for_real_input_is_a_failure():
    """The dangerous case: asked to purge, told nothing would go."""
    assert cleaner.purge_preview_failed(["ftp", "telnet"], []) is True


def test_empty_preview_for_empty_input_is_not_a_failure():
    assert cleaner.purge_preview_failed([], []) is False


def test_populated_preview_is_not_a_failure():
    assert cleaner.purge_preview_failed(["ftp"], ["ftp", "libfoo"]) is False


def test_a_broken_simulation_reads_as_failure_not_as_no_op(monkeypatch):
    """apt missing / timed out / output format changed -> _sh returns ''."""
    fake_apt(monkeypatch, "")
    candidates = ["ftp", "telnet"]
    preview = cleaner.purge_preview(candidates)
    assert cleaner.purge_preview_failed(candidates, preview) is True


# -------------------------------------------------------------- critical guard
@pytest.mark.parametrize("pkg", [
    "cinnamon",
    "cinnamon-session",
    "cinnamon-settings-daemon",
    "mint-meta-cinnamon",
    "mint-meta-core",
    "mint-common",
    "nvidia-driver-595-open",
    "xserver-xorg-core",
    "lightdm",
    "nemo",
    "muffin",
    "systemd",
])
def test_session_critical_packages_are_caught(pkg):
    assert cleaner.critical_in(["ftp", pkg, "telnet"]) == [pkg]


def test_the_actual_disaster_would_be_refused(monkeypatch):
    """End-to-end: the real cascade must trip the guard."""
    fake_apt(monkeypatch, REAL_CASCADE)
    preview = cleaner.purge_preview(["ftp", "gir1.2-adw-1"])
    critical = cleaner.critical_in(preview)
    assert critical, "the guard MUST refuse this cascade"
    assert "cinnamon" in critical
    assert "nvidia-driver-595-open" in critical


def test_a_genuinely_harmless_cascade_is_allowed(monkeypatch):
    """The guard must not refuse everything, or it just gets ignored."""
    fake_apt(monkeypatch, HARMLESS_CASCADE)
    preview = cleaner.purge_preview(["ftp", "telnet", "p7zip"])
    assert cleaner.critical_in(preview) == []


def test_priority_would_not_have_saved_us():
    """Documents why the guard is name-based, not priority-based.

    cinnamon is Priority: optional, Essential: no -- an essential/priority
    check would have permitted the exact removal that broke the machine.
    """
    assert cleaner.critical_in(["cinnamon"]) == ["cinnamon"]


# ------------------------------------------------------------------- plumbing
def test_orphan_list_strips_arch_qualifiers(monkeypatch):
    """deborphan prints `name:arch`, which is not a valid package name."""
    fake_deborphan(monkeypatch, "ftp:all\ngir1.2-adw-1:amd64\ntelnet:all\n")
    assert cleaner.orphan_list() == ["ftp", "gir1.2-adw-1", "telnet"]


def test_orphan_list_drops_unparseable_entries(monkeypatch):
    fake_deborphan(monkeypatch, "ftp:all\n-o\n\nUPPER:amd64\n")
    assert cleaner.orphan_list() == ["ftp"]


def test_orphan_purge_argv_elevates_validates_and_terminates():
    argv = cleaner.orphan_purge_argv(["ftp", "telnet"])
    assert argv == ["pkexec", "apt-get", "purge", "-y", "--", "ftp", "telnet"]


def test_orphan_purge_argv_refuses_injection():
    with pytest.raises(InvalidPackageName):
        cleaner.orphan_purge_argv(["-o", "APT::Update::Pre-Invoke::=touch /tmp/x"])


# ------------------------------------------------------------------ task wiring
def test_orphan_task_requires_confirmation():
    task = next(t for t in cleaner.tasks() if t.key == "orphans")
    assert task.confirm is True
    assert task.command == "", "must not carry a blind runnable command"


def test_no_other_task_removes_packages():
    """Only the orphan task may touch packages, and only with confirmation."""
    for task in cleaner.tasks():
        if task.key == "orphans":
            continue
        assert "purge" not in task.command
        assert "deborphan" not in task.command
