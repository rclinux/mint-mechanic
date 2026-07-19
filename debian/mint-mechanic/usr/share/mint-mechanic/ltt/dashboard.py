"""The Dashboard view — Mint Mechanic's signature screen.

A row of live analog gauges (CPU, RAM, Disk, and the GPU dial Stacer never had)
over a compact strip of readouts (network throughput, load average, uptime). All
data comes through ltt.metrics behind its stable API, so the GPU dial simply
isn't added when no GPU reader is present — graceful degradation, no crash.

Polling is a single 1 s GLib timeout; it's torn down when the view goes away so
nothing keeps ticking after the window closes.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .gauges import GaugeWidget  # noqa: E402
from .metrics import MetricsReader  # noqa: E402

_POLL_SECONDS = 1


def _fmt_rate(bps: float) -> str:
    """Bytes/sec -> human string."""
    unit = "B/s"
    for u in ("B/s", "KB/s", "MB/s", "GB/s"):
        unit = u
        if bps < 1024:
            break
        bps /= 1024.0
    return f"{bps:.0f} {unit}" if unit == "B/s" else f"{bps:.1f} {unit}"


class DashboardView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(18)
        self.set_margin_bottom(12)
        self.set_margin_start(12)
        self.set_margin_end(12)

        self._metrics = MetricsReader()
        self._poll_id: int | None = None

        # --- gauges row --------------------------------------------------------
        gauges = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                         homogeneous=True)
        gauges.set_vexpand(True)
        self._cpu = GaugeWidget("CPU")
        self._ram = GaugeWidget("RAM")
        self._disk = GaugeWidget("DISK")
        for g in (self._cpu, self._ram, self._disk):
            gauges.append(g)

        # Only show the GPU dial if a reader is actually present.
        self._gpu = None
        if self._metrics.gpu().percent is not None:
            self._gpu = GaugeWidget("GPU")
            gauges.append(self._gpu)
        self.append(gauges)

        # --- readouts strip ----------------------------------------------------
        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        strip.set_halign(Gtk.Align.CENTER)
        strip.set_margin_top(8)
        self._net = self._readout(strip, "Network", "↓ –   ↑ –")
        self._load = self._readout(strip, "Load avg", "–")
        self._uptime = self._readout(strip, "Uptime", "–")
        self.append(strip)

        # Prime immediately, then poll; start/stop with the widget's lifecycle.
        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

    def _readout(self, parent: Gtk.Box, title: str, initial: str) -> Gtk.Label:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        cap = Gtk.Label(label=title)
        cap.add_css_class("dim-label")
        cap.set_xalign(0.5)
        val = Gtk.Label(label=initial)
        val.set_xalign(0.5)
        val.add_css_class("title-4")
        box.append(val)
        box.append(cap)
        parent.append(box)
        return val

    # ---------------------------------------------------------------- lifecycle
    def _on_map(self, _w) -> None:
        self._poll()
        if self._poll_id is None:
            self._poll_id = GLib.timeout_add_seconds(_POLL_SECONDS, self._poll)

    def _on_unmap(self, _w) -> None:
        if self._poll_id is not None:
            GLib.source_remove(self._poll_id)
            self._poll_id = None

    def _poll(self) -> bool:
        m = self._metrics
        c, ram, disk = m.cpu(), m.ram(), m.disk()
        self._cpu.set_reading(c.percent, c.detail)
        self._ram.set_reading(ram.percent, ram.detail)
        self._disk.set_reading(disk.percent, disk.detail)
        if self._gpu is not None:
            g = m.gpu()
            self._gpu.set_reading(g.percent, g.detail)

        x = m.extras()
        self._net.set_text(f"↓ {_fmt_rate(x.net_down_bps)}   ↑ {_fmt_rate(x.net_up_bps)}")
        self._load.set_text(f"{x.load1:.2f}  {x.load5:.2f}  {x.load15:.2f}")
        self._uptime.set_text(x.uptime)
        return True
