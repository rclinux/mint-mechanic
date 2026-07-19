"""Streamline profile export/import round trip.

A profile is the signature feature and an explicitly portable artifact — it is
meant to be carried to another machine and hand-edited — so these tests pin
both the format and the fact that parsing hands hostile lines onward intact
(the validation that stops them lives in ltt.pkg, and the view applies it at
import; profiles.py itself is a faithful parser by design).
"""

from ltt import config
from ltt.pkg import partition_names
from ltt.profiles import export_profile, read_profile


class FakeBackend:
    name = "fake"

    def __init__(self, pkgs):
        self._pkgs = pkgs

    def list_manual(self):
        return sorted(self._pkgs)


def test_round_trip_preserves_the_package_set(tmp_path):
    pkgs = ["htop", "vim", "python3-gi", "gir1.2-gtk-4.0"]
    path = export_profile(tmp_path / "profile.txt", FakeBackend(pkgs))
    assert read_profile(path) == sorted(pkgs)


def test_export_writes_a_readable_header(tmp_path):
    path = export_profile(tmp_path / "p.txt", FakeBackend(["htop"]))
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Mint Mechanic")
    assert f"v{config.APP_VERSION}" in text
    assert "backend: fake" in text
    assert "# count: 1" in text


def test_read_ignores_comments_blanks_and_indentation(tmp_path):
    p = tmp_path / "p.txt"
    p.write_text(
        "# header\n"
        "\n"
        "htop\n"
        "   \n"
        "   # indented comment\n"
        "  vim  \n",
        encoding="utf-8",
    )
    assert read_profile(p) == ["htop", "vim"]


def test_empty_profile_reads_as_empty_list(tmp_path):
    path = export_profile(tmp_path / "p.txt", FakeBackend([]))
    assert read_profile(path) == []


def test_hostile_profile_is_filtered_before_install(tmp_path):
    """End-to-end shape of the import path: parse faithfully, then partition.

    This is what StreamlineView does — the malicious lines are dropped and
    reported, and only real package names survive to the elevated call.
    """
    p = tmp_path / "evil.txt"
    p.write_text(
        "# Mint Mechanic — Streamline package profile\n"
        "htop\n"
        "-o\n"
        "APT::Update::Pre-Invoke::=touch /tmp/OWNED\n"
        "vim\n",
        encoding="utf-8",
    )
    good, bad = partition_names(read_profile(p))
    assert good == ["htop", "vim"]
    assert bad == ["-o", "APT::Update::Pre-Invoke::=touch /tmp/OWNED"]


def test_export_handles_a_path_with_spaces(tmp_path):
    d = tmp_path / "my profiles"
    d.mkdir()
    path = export_profile(d / "week one.txt", FakeBackend(["htop"]))
    assert read_profile(path) == ["htop"]
