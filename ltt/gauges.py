"""Cairo analog gauge widget — the emotional hook Stacer got right.

A faithful-analog dial (270° sweep, ticks, a swinging needle) with a subtle
modern finish: a load-colored value arc over the track, and theme-aware text /
needle so it reads on light or dark Cinnamon themes. Values animate — the needle
eases toward each new reading rather than snapping — and the animation timer only
runs while the needle is actually moving, so a steady system costs nothing.
"""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

_START_DEG = 135.0      # 0% sits at lower-left ...
_SWEEP_DEG = 270.0      # ... sweeping clockwise over the top to lower-right.

# Load palette (GNOME-ish): calm -> warm -> hot.
_GREEN = (0.20, 0.82, 0.48)
_AMBER = (0.90, 0.65, 0.04)
_RED = (0.88, 0.11, 0.14)


def _load_color(pct: float) -> tuple[float, float, float]:
    if pct >= 85:
        return _RED
    if pct >= 60:
        return _AMBER
    return _GREEN


class GaugeWidget(Gtk.DrawingArea):
    """One dial. Call set_reading(percent, detail); None percent => unavailable."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self._label = label
        self._detail = ""
        self._target = 0.0
        self._displayed = 0.0
        self._available = True
        self._anim_id: int | None = None
        self.set_content_width(170)
        self.set_content_height(180)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def set_reading(self, percent: float | None, detail: str = "") -> None:
        self._detail = detail
        if percent is None:
            self._available = False
            self.queue_draw()
            return
        self._available = True
        self._target = max(0.0, min(100.0, percent))
        if self._anim_id is None:
            self._anim_id = GLib.timeout_add(16, self._animate)

    def _animate(self) -> bool:
        # Ease the displayed value toward the target; stop when settled.
        self._displayed += (self._target - self._displayed) * 0.22
        if abs(self._target - self._displayed) < 0.15:
            self._displayed = self._target
            self.queue_draw()
            self._anim_id = None
            return False
        self.queue_draw()
        return True

    # ------------------------------------------------------------------ drawing
    def _draw(self, _area, ctx, width, height, *_) -> None:
        fg = self.get_color()          # theme foreground (GTK4) -> Gdk.RGBA
        size = min(width, height)
        cx, cy = width / 2.0, height * 0.52
        r = size * 0.40
        lw = r * 0.16

        a0 = math.radians(_START_DEG)
        a1 = math.radians(_START_DEG + _SWEEP_DEG)

        # Track.
        ctx.set_line_width(lw)
        ctx.set_line_cap(1)  # ROUND
        ctx.set_source_rgba(fg.red, fg.green, fg.blue, 0.14)
        ctx.arc(cx, cy, r, a0, a1)
        ctx.stroke()

        # Ticks (every 10%).
        ctx.set_source_rgba(fg.red, fg.green, fg.blue, 0.35)
        ctx.set_line_width(max(1.0, r * 0.02))
        for i in range(11):
            a = math.radians(_START_DEG + _SWEEP_DEG * i / 10.0)
            ca, sa = math.cos(a), math.sin(a)
            ctx.move_to(cx + (r - lw * 0.7) * ca, cy + (r - lw * 0.7) * sa)
            ctx.line_to(cx + (r + lw * 0.7) * ca, cy + (r + lw * 0.7) * sa)
            ctx.stroke()

        if self._available:
            self._draw_value_arc(ctx, cx, cy, r, lw, a0)
            self._draw_needle(ctx, cx, cy, r, fg)

        self._draw_text(ctx, cx, cy, r, fg)

    def _draw_value_arc(self, ctx, cx, cy, r, lw, a0) -> None:
        col = _load_color(self._displayed)
        av = math.radians(_START_DEG + _SWEEP_DEG * self._displayed / 100.0)
        ctx.set_line_width(lw)
        ctx.set_source_rgba(*col, 0.95)
        ctx.arc(cx, cy, r, a0, av)
        ctx.stroke()

    def _draw_needle(self, ctx, cx, cy, r, fg) -> None:
        a = math.radians(_START_DEG + _SWEEP_DEG * self._displayed / 100.0)
        ca, sa = math.cos(a), math.sin(a)
        # perpendicular for the needle base width
        pa = a + math.pi / 2.0
        pca, psa = math.cos(pa), math.sin(pa)
        bw = r * 0.06
        tipx, tipy = cx + r * 0.80 * ca, cy + r * 0.80 * sa
        ctx.move_to(cx + bw * pca, cy + bw * psa)
        ctx.line_to(tipx, tipy)
        ctx.line_to(cx - bw * pca, cy - bw * psa)
        ctx.close_path()
        ctx.set_source_rgba(fg.red, fg.green, fg.blue, 0.92)
        ctx.fill()
        # hub
        ctx.arc(cx, cy, r * 0.10, 0, 2 * math.pi)
        ctx.fill()

    def _draw_text(self, ctx, cx, cy, r, fg) -> None:
        ctx.select_font_face("Sans", 0, 0)
        # big value (or n/a)
        val = f"{self._displayed:.0f}%" if self._available else "n/a"
        ctx.set_font_size(r * 0.44)
        ext = ctx.text_extents(val)
        ctx.move_to(cx - ext.width / 2 - ext.x_bearing, cy + r * 0.55)
        ctx.set_source_rgba(fg.red, fg.green, fg.blue, 0.95 if self._available else 0.4)
        ctx.show_text(val)
        # label above the dial
        ctx.set_font_size(r * 0.24)
        ext = ctx.text_extents(self._label)
        ctx.move_to(cx - ext.width / 2 - ext.x_bearing, cy - r * 1.02)
        ctx.set_source_rgba(fg.red, fg.green, fg.blue, 0.85)
        ctx.show_text(self._label)
        # detail below the value
        if self._detail:
            ctx.set_font_size(r * 0.155)
            ext = ctx.text_extents(self._detail)
            ctx.move_to(cx - ext.width / 2 - ext.x_bearing, cy + r * 0.86)
            ctx.set_source_rgba(fg.red, fg.green, fg.blue, 0.55)
            ctx.show_text(self._detail)
