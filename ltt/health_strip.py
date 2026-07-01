"""A persistent GO/NO-GO health strip along the bottom of the window.

Shows an overall verdict pill plus one pill per check, colored green/amber/red.
Checks run off the UI thread and refresh on a slow timer (they're cheap but shell
out). Tooltips carry each check's detail line.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import health  # noqa: E402

_REFRESH_SECONDS = 60

_CSS = b"""
.ltt-pill { border-radius: 10px; padding: 2px 10px; margin: 2px 3px;
            color: #ffffff; font-weight: bold; }
.ltt-go      { background-color: #2a9d63; }
.ltt-warn    { background-color: #b5820a; }
.ltt-nogo    { background-color: #c0392b; }
.ltt-unknown { background-color: #7f8c8d; }
"""

_CLASS = {health.GO: "ltt-go", health.WARN: "ltt-warn",
          health.NOGO: "ltt-nogo", health.UNKNOWN: "ltt-unknown"}
_VERDICT = {health.GO: "GO", health.WARN: "CHECK", health.NOGO: "NO-GO",
            health.UNKNOWN: "…"}

_css_installed = False


def _install_css() -> None:
    global _css_installed
    if _css_installed:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(_CSS)
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _css_installed = True


def _pill(text: str, status: str, tooltip: str = "") -> Gtk.Label:
    lbl = Gtk.Label(label=text)
    lbl.add_css_class("ltt-pill")
    lbl.add_css_class(_CLASS.get(status, "ltt-unknown"))
    if tooltip:
        lbl.set_tooltip_text(tooltip)
    return lbl


class HealthStrip(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        _install_css()
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(10)
        self.set_margin_end(10)
        self._timer: int | None = None

        self._verdict = _pill("Health …", health.UNKNOWN)
        self.append(self._verdict)
        self._pills_after = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,
                                    spacing=0, hexpand=True)
        self.append(self._pills_after)

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

    def _on_map(self, _w) -> None:
        self.refresh()
        if self._timer is None:
            self._timer = GLib.timeout_add_seconds(_REFRESH_SECONDS, self._tick)

    def _on_unmap(self, _w) -> None:
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _tick(self) -> bool:
        self.refresh()
        return True

    def refresh(self) -> None:
        def work() -> None:
            checks = health.run_checks()
            GLib.idle_add(self._apply, checks)

        threading.Thread(target=work, daemon=True).start()

    def _apply(self, checks: list[health.Check]) -> None:
        verdict = health.overall(checks)
        self._verdict.set_text(f"Health: {_VERDICT.get(verdict, '…')}")
        for cls in ("ltt-go", "ltt-warn", "ltt-nogo", "ltt-unknown"):
            self._verdict.remove_css_class(cls)
        self._verdict.add_css_class(_CLASS.get(verdict, "ltt-unknown"))

        child = self._pills_after.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._pills_after.remove(child)
            child = nxt
        for c in checks:
            self._pills_after.append(_pill(c.label, c.status, c.detail))
