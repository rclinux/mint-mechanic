"""The Uninstaller view — search manually-installed packages and remove them.

Lists come from the apt seam (`pkg.list_manual`); removal routes through the same
seam and elevates via pkexec. To stay responsive on a system with ~2000 manual
packages, the list is search-filtered rather than rendering every row at once,
and the selection persists across searches.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from .actions import ActionResult, pkexec_available, run_privileged  # noqa: E402
from .pkg import (  # noqa: E402
    critical_in,
    default_backend,
    preview_failed,
    removal_preview,
)

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
        purge = self._purge.get_active()
        self._status.set_text("Checking what would be removed…")
        self._begin_preview(pkgs, purge)

    # ------------------------------------------------------- blast radius first
    def _begin_preview(self, pkgs: list[str], purge: bool) -> None:
        """Never remove what the user hasn't seen in full.

        Selecting a package does not mean selecting only that package: apt also
        removes everything depending on it. `cinnamon` alone pulls out
        mint-meta-cinnamon and more. The cascade is computed off-thread with
        apt's own dry run (see ltt.pkg.removal_preview).
        """
        def work() -> None:
            preview = removal_preview(pkgs, purge=purge)
            failed = preview_failed(pkgs, preview)
            critical = critical_in(preview)
            GLib.idle_add(self._previewed, pkgs, purge, preview, critical, failed)

        threading.Thread(target=work, daemon=True).start()

    def _previewed(self, pkgs: list[str], purge: bool, preview: list[str],
                   critical: list[str], failed: bool) -> None:
        if failed:
            # An empty preview for a real request means the simulation failed,
            # not that there is nothing to do. Never proceed on that.
            self._abort("Could not determine what would be removed — "
                        "nothing was removed.")
            return
        if critical:
            shown = ", ".join(critical[:4])
            more = f" and {len(critical) - 4} more" if len(critical) > 4 else ""
            self._abort(
                f"Refused: this would also remove {shown}{more} — your desktop "
                f"or graphics stack. Nothing was removed.")
            return
        self._confirm(pkgs, purge, preview)

    def _confirm(self, pkgs: list[str], purge: bool, preview: list[str]) -> None:
        extra = len(preview) - len(pkgs)
        verb = "purge" if purge else "remove"
        detail = (f"You selected {len(pkgs)}, but apt would {verb} "
                  f"{len(preview)} packages in total"
                  + (f" ({extra} additional through dependencies)" if extra > 0
                     else "") + ".\n\n"
                  + ", ".join(preview[:40])
                  + (f"\n\n…and {len(preview) - 40} more."
                     if len(preview) > 40 else ""))
        dlg = Gtk.AlertDialog()
        dlg.set_modal(True)
        dlg.set_message(f"{verb.capitalize()} {len(preview)} packages?")
        dlg.set_detail(detail)
        dlg.set_buttons(["Cancel", f"{verb.capitalize()} them"])
        dlg.set_default_button(0)
        dlg.set_cancel_button(0)
        dlg.choose(self.get_root(), None,
                   lambda d, r: self._on_choice(d, r, pkgs, purge))

    def _on_choice(self, dlg, result, pkgs: list[str], purge: bool) -> None:
        try:
            choice = dlg.choose_finish(result)
        except GLib.Error:
            choice = 0
        if choice != 1:
            self._abort("Cancelled — nothing was removed.")
            return
        self._status.set_text(f"Authorizing removal of {len(pkgs)} packages…")
        run_privileged(self._backend.remove_argv(pkgs, purge=purge), self._done)

    def _abort(self, message: str) -> None:
        self._busy = False
        self._status.set_text(message)
        self._sync_button()

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
