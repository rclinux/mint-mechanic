"""The Uninstaller view — search manually-installed packages and remove them.

Lists come from the apt seam (`pkg.list_manual`); removal routes through the same
seam and elevates via pkexec. To stay responsive on a system with ~2000 manual
packages, the list is search-filtered rather than rendering every row at once,
and the selection persists across searches.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .actions import ActionResult, pkexec_available, run_privileged  # noqa: E402
from .pkg import default_backend  # noqa: E402

_MAX_RESULTS = 400


class UninstallerView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._backend = default_backend()
        self._manual: list[str] = []
        self._selected: set[str] = set()
        self._busy = False

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(14)
        header.set_margin_bottom(6)
        header.set_margin_start(12)
        header.set_margin_end(12)
        title = Gtk.Label(xalign=0.0)
        title.set_markup("<span size='large' weight='bold'>Uninstall Applications</span>")
        header.append(title)
        self.append(header)

        self._search = Gtk.SearchEntry(hexpand=True)
        self._search.set_placeholder_text("Search installed packages…")
        self._search.set_margin_start(12)
        self._search.set_margin_end(12)
        self._search.connect("search-changed", lambda _e: self._refilter())
        self.append(self._search)

        self._listbox = Gtk.ListBox()
        self._listbox.add_css_class("boxed-list")
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.set_margin_start(12)
        self._listbox.set_margin_end(12)
        self._listbox.set_margin_top(6)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self._listbox)
        self.append(scroller)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer.set_margin_start(14)
        footer.set_margin_end(14)
        footer.set_margin_top(8)
        footer.set_margin_bottom(10)
        self._status = Gtk.Label(xalign=0.0, hexpand=True)
        self._status.add_css_class("dim-label")
        footer.append(self._status)
        self._purge = Gtk.CheckButton(label="Also remove config (purge)")
        footer.append(self._purge)
        self._remove_btn = Gtk.Button(label="Remove selected")
        self._remove_btn.add_css_class("destructive-action")
        self._remove_btn.set_sensitive(False)
        self._remove_btn.connect("clicked", self._on_remove)
        footer.append(self._remove_btn)
        self.append(footer)

        self.connect("map", lambda _w: self._reload())

    def _reload(self) -> None:
        self._manual = sorted(self._backend.list_manual())
        self._selected.clear()
        self._search.set_text("")
        self._refilter()

    def _refilter(self) -> None:
        q = self._search.get_text().strip().lower()
        self._listbox.remove_all()
        if not q:
            self._status.set_text(f"Type to filter {len(self._manual)} packages "
                                  f"({len(self._selected)} selected).")
            self._sync_button()
            return
        matches = [p for p in self._manual if q in p.lower()]
        shown = matches[:_MAX_RESULTS]
        for name in shown:
            self._listbox.append(self._row(name))
        extra = len(matches) - len(shown)
        note = f" (+{extra} more, refine search)" if extra else ""
        self._status.set_text(f"{len(matches)} matches{note} — "
                              f"{len(self._selected)} selected.")
        self._sync_button()

    def _row(self, name: str) -> Gtk.ListBoxRow:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(10)
        box.set_margin_end(10)
        check = Gtk.CheckButton()
        check.set_active(name in self._selected)
        check.connect("toggled", self._on_check, name)
        box.append(check)
        lbl = Gtk.Label(label=name, xalign=0.0, hexpand=True)
        box.append(lbl)
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row.set_child(box)
        return row

    def _on_check(self, check: Gtk.CheckButton, name: str) -> None:
        if check.get_active():
            self._selected.add(name)
        else:
            self._selected.discard(name)
        self._sync_button()

    def _sync_button(self) -> None:
        n = len(self._selected)
        self._remove_btn.set_label(f"Remove selected ({n})" if n else "Remove selected")
        self._remove_btn.set_sensitive(
            n > 0 and pkexec_available() and not self._busy)

    def _on_remove(self, _btn) -> None:
        if self._busy or not self._selected:
            return
        self._busy = True
        self._remove_btn.set_sensitive(False)
        pkgs = sorted(self._selected)
        self._status.set_text(f"Authorizing removal of {len(pkgs)} packages…")
        argv = self._backend.remove_argv(pkgs, purge=self._purge.get_active())
        run_privileged(argv, self._done)

    def _done(self, res: ActionResult) -> None:
        self._busy = False
        if res.ok:
            self._status.set_text("Removed. Reloading…")
            self._reload()
        elif res.cancelled:
            self._status.set_text("Removal cancelled.")
            self._sync_button()
        else:
            tail = (res.stderr or "unknown error").strip().splitlines()
            self._status.set_text(f"Removal failed: {tail[-1] if tail else 'error'}")
            self._sync_button()
