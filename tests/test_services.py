"""systemctl state parsing and the elevated toggle argv."""

import pytest

from ltt import services


def fake_systemctl(monkeypatch, *, active, enabled):
    """Stand in for the two `systemctl` reads `state()` performs."""
    def run(argv, **kwargs):
        verb = argv[1]
        out = active if verb == "is-active" else enabled
        return type("P", (), {"stdout": out + "\n", "stderr": "", "returncode": 0})()
    monkeypatch.setattr(services.subprocess, "run", run)


def test_running_enabled_unit(monkeypatch):
    fake_systemctl(monkeypatch, active="active", enabled="enabled")
    s = services.state("cups.service")
    assert (s.active, s.enabled, s.available) == (True, True, True)


def test_stopped_disabled_unit(monkeypatch):
    fake_systemctl(monkeypatch, active="inactive", enabled="disabled")
    s = services.state("cups.service")
    assert (s.active, s.enabled, s.available) == (False, False, True)


def test_absent_unit_is_unavailable(monkeypatch):
    """`is-enabled` on a missing unit prints nothing to stdout."""
    fake_systemctl(monkeypatch, active="inactive", enabled="")
    s = services.state("ssh.service")
    assert s.available is False


def test_not_found_marker_is_unavailable(monkeypatch):
    fake_systemctl(monkeypatch, active="unknown", enabled="not-found")
    assert services.state("nope.service").available is False


def test_masked_unit_is_available_but_not_enabled(monkeypatch):
    fake_systemctl(monkeypatch, active="inactive", enabled="masked")
    s = services.state("cups.service")
    assert s.available is True
    assert s.enabled is False


@pytest.mark.parametrize("unit", ["cups.service", "bluetooth.service"])
def test_toggle_argv_elevates_and_applies_now(unit):
    assert services.enable_argv(unit) == [
        "pkexec", "systemctl", "enable", "--now", unit]
    assert services.disable_argv(unit) == [
        "pkexec", "systemctl", "disable", "--now", unit]


def test_toggle_argv_can_defer_to_next_boot():
    assert services.enable_argv("cups.service", now=False) == [
        "pkexec", "systemctl", "enable", "cups.service"]
    assert services.disable_argv("cups.service", now=False) == [
        "pkexec", "systemctl", "disable", "cups.service"]


def test_reads_are_unprivileged(monkeypatch):
    """Status reads must never elevate — only toggles do."""
    seen = []
    monkeypatch.setattr(
        services.subprocess, "run",
        lambda argv, **k: seen.append(argv) or type(
            "P", (), {"stdout": "active\n", "stderr": "", "returncode": 0})())
    services.state("cups.service")
    assert all(argv[0] == "systemctl" for argv in seen)
