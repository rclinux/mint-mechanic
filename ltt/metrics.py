"""System metrics behind a stable API (feeds the Dashboard gauges).

The Dashboard reads CPU / RAM / Disk / GPU through this one interface so the
gauge widgets never touch psutil or nvidia-smi directly. That matters twice:
graceful degradation (a missing GPU tool hides the dial instead of crashing),
and the ~2027/28 NVIDIA->AMD swap becomes a one-file change here (swap the GPU
reader; the gauges don't move).

All reads are read-only and need no root.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

try:
    import psutil
except ImportError:  # keep the shell runnable even if psutil is absent
    psutil = None


@dataclass(frozen=True)
class Gauge:
    """A single gauge reading: percent plus an optional human detail line."""
    label: str
    percent: float | None       # None => unavailable, gauge should hide/dim
    detail: str = ""


@dataclass(frozen=True)
class GpuReading:
    percent: float | None
    temp_c: float | None
    mem_used_mb: float | None
    mem_total_mb: float | None


class MetricsReader:
    """One instance polled by the Dashboard's GLib timeout loop."""

    def __init__(self) -> None:
        self._have_psutil = psutil is not None
        self._nvidia_smi = shutil.which("nvidia-smi")

    def cpu(self) -> Gauge:
        if not self._have_psutil:
            return Gauge("CPU", None)
        pct = psutil.cpu_percent(interval=None)
        return Gauge("CPU", pct, f"{psutil.cpu_count(logical=True)} threads")

    def ram(self) -> Gauge:
        if not self._have_psutil:
            return Gauge("RAM", None)
        vm = psutil.virtual_memory()
        return Gauge("RAM", vm.percent,
                     f"{vm.used / 2**30:.1f} / {vm.total / 2**30:.1f} GiB")

    def disk(self, mount: str = "/") -> Gauge:
        if not self._have_psutil:
            return Gauge("Disk", None)
        du = psutil.disk_usage(mount)
        return Gauge("Disk", du.percent,
                     f"{du.used / 2**30:.0f} / {du.total / 2**30:.0f} GiB ({mount})")

    def gpu(self) -> Gauge:
        """NVIDIA now, behind the same Gauge surface. Degrades gracefully."""
        r = self._read_nvidia()
        if r is None or r.percent is None:
            return Gauge("GPU", None)
        detail = ""
        if r.temp_c is not None:
            detail = f"{r.temp_c:.0f} °C"
        if r.mem_used_mb is not None and r.mem_total_mb:
            detail += f"  {r.mem_used_mb/1024:.1f}/{r.mem_total_mb/1024:.1f} GiB"
        return Gauge("GPU", r.percent, detail.strip())

    def _read_nvidia(self) -> GpuReading | None:
        if not self._nvidia_smi:
            return None
        try:
            out = subprocess.run(
                [self._nvidia_smi,
                 "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3, check=True,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        first = out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
        try:
            util, temp, used, total = (x.strip() for x in first.split(","))
            return GpuReading(float(util), float(temp), float(used), float(total))
        except ValueError:
            return None
