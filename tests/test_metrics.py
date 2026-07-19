"""Metrics readers — mainly the graceful-degradation contract.

A missing GPU tool or a missing psutil must hide a gauge, never crash the
Dashboard. The GPU reader is also the seam for the planned NVIDIA->AMD swap, so
its parsing is pinned here.
"""

import pytest

from ltt.metrics import MetricsReader


@pytest.fixture
def reader():
    return MetricsReader()


# ------------------------------------------------------------------- GPU
def fake_nvidia(monkeypatch, reader, stdout, *, fails=False):
    reader._nvidia_smi = "/usr/bin/nvidia-smi"

    def run(*a, **k):
        if fails:
            raise OSError("nvidia-smi exploded")
        return type("P", (), {"stdout": stdout, "returncode": 0})()

    monkeypatch.setattr("ltt.metrics.subprocess.run", run)


def test_gpu_parses_a_normal_reading(monkeypatch, reader):
    fake_nvidia(monkeypatch, reader, "42, 61, 2048, 16384\n")
    g = reader.gpu()
    assert g.percent == 42.0
    assert "61 °C" in g.detail
    assert "2.0/16.0 GiB" in g.detail


def test_gpu_uses_the_first_of_several_cards(monkeypatch, reader):
    fake_nvidia(monkeypatch, reader, "10, 50, 1024, 8192\n90, 70, 4096, 8192\n")
    assert reader.gpu().percent == 10.0


def test_gpu_absent_when_no_tool(reader):
    reader._nvidia_smi = None
    assert reader.gpu().percent is None


def test_gpu_absent_when_tool_fails(monkeypatch, reader):
    fake_nvidia(monkeypatch, reader, "", fails=True)
    assert reader.gpu().percent is None


@pytest.mark.parametrize("junk", ["", "\n", "garbage\n", "1, 2\n", "a, b, c, d\n"])
def test_gpu_absent_on_unparseable_output(monkeypatch, reader, junk):
    fake_nvidia(monkeypatch, reader, junk)
    assert reader.gpu().percent is None


# ---------------------------------------------------------------- no psutil
def test_all_gauges_degrade_without_psutil(reader):
    reader._have_psutil = False
    for gauge in (reader.cpu(), reader.ram(), reader.disk()):
        assert gauge.percent is None
        assert gauge.label  # still labelled, so the UI can dim it


def test_extras_degrade_without_psutil(reader):
    reader._have_psutil = False
    e = reader.extras()
    assert (e.net_down_bps, e.net_up_bps) == (0.0, 0.0)


# ------------------------------------------------------------------- rates
def test_net_rates_start_at_zero(reader):
    """First sample has no previous reading to difference against."""
    assert reader._net_rates() == (0.0, 0.0)


def test_net_rates_are_never_negative(monkeypatch, reader):
    """Counters reset (interface down/up); a rate must not go negative."""
    if not reader._have_psutil:
        pytest.skip("psutil not installed")
    counters = iter([(10_000, 5_000), (100, 50)])

    def io(*a, **k):
        recv, sent = next(counters)
        return type("C", (), {"bytes_recv": recv, "bytes_sent": sent})()

    monkeypatch.setattr("ltt.metrics.psutil.net_io_counters", io)
    reader._net_last = None
    reader._net_rates()          # prime
    down, up = reader._net_rates()  # counters went backwards
    assert down >= 0.0 and up >= 0.0


# ------------------------------------------------------------------ uptime
@pytest.mark.parametrize("secs,expected", [
    (45, "0m"),
    (90, "1m"),
    (3_600, "1h 0m"),
    (7_320, "2h 2m"),
    (90_000, "1d 1h 0m"),
])
def test_uptime_formatting(monkeypatch, reader, secs, expected):
    monkeypatch.setattr("ltt.metrics.time.time", lambda: 1_000_000.0)
    if reader._have_psutil:
        monkeypatch.setattr("ltt.metrics.psutil.boot_time",
                            lambda: 1_000_000.0 - secs)
    else:
        pytest.skip("psutil not installed")
    assert reader._uptime() == expected


def test_live_reads_are_sane():
    """One unmocked pass: whatever this machine reports must be in range."""
    r = MetricsReader()
    for gauge in (r.cpu(), r.ram(), r.disk()):
        if gauge.percent is not None:
            assert 0.0 <= gauge.percent <= 100.0
