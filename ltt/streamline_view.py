"""The Streamline view — package-profile export/import.

Mint Mechanic's signature differentiator: export the set of manually-installed
packages to a portable, human-readable manifest (a bill-of-materials that plugs
into a from-scratch rebuild), and import one to see — and install — what's
missing on this machine. Neither Stacer nor Mint ships this.

Export/parse logic lives in ltt.profiles; the missing-package diff and any
install route through the ltt.pkg apt seam; installing elevates via the shared
per-action pkexec runner. The view is just wiring.
"""

from __future__ import annotations

import datetime as _dt

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import profiles  # noqa: E402
from .actions import ActionResult, pkexec_available, run_privileged  # noqa: E402
from .pkg import default_backend, partition_names  # noqa: E402


class StreamlineView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_top(16)
        self.set_margin_bottom(12)
        self.set_margin_start(16)
        self.set_margin_end(16)

        self._backend = default_backend()
        self._missing: list[str] = []

        title = Gtk.Label(xalign=0.0)
        title.set_markup("<span size='large' weight='bold'>Streamline — Package Profiles</span>")
        self.append(title)
        blurb = Gtk.Label(xalign=0.0, wrap=True)
        blurb.add_css_class("dim-label")
        blurb.set_text(
            "Export the packages you installed as a portable profile — a "
            "bill-of-materials for rebuilding this system. Import one to see "
            "and install what's missing here.")
        self.append(blurb)

        # --- export -----------------------------------------------------------
        try:
            manual_count = len(self._backend.list_manual())
        except Exception:  # noqa: BLE001 - never let a probe break the view
            manual_count = 0
        exp_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        exp_lbl = Gtk.Label(xalign=0.0, hexpand=True)
        exp_lbl.set_text(f"{manual_count} packages manually installed on this system.")
        exp_row.append(exp_lbl)
        exp_btn = Gtk.Button(label="Export profile…")
        exp_btn.add_css_class("suggested-action")
        exp_btn.connect("clicked", self._on_export)
        exp_row.append(exp_btn)
        self.append(exp_row)

        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # --- import -----------------------------------------------------------
        imp_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._imp_lbl = Gtk.Label(xalign=0.0, hexpand=True)
        self._imp_lbl.set_text("Import a profile to compare against this system.")
        imp_row.append(self._imp_lbl)
        imp_btn = Gtk.Button(label="Open profile…")
        imp_btn.connect("clicked", self._on_import)
        imp_row.append(imp_btn)
        self.append(imp_row)

        # missing-package list
        self._list = Gtk.ListBox()
        self._list.add_css_class("boxed-list")
        self._list.set_selection_mode(Gtk.SelectionMode.NONE)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self._list)
        self.append(scroller)

        self._install_btn = Gtk.Button(label="Install missing")
        self._install_btn.add_css_class("suggested-action")
        self._install_btn.set_halign(Gtk.Align.END)
        self._install_btn.set_sensitive(False)
        self._install_btn.connect("clicked", self._on_install_missing)
        self.append(self._install_btn)

        self._status = Gtk.Label(xalign=0.0)
        self._status.add_css_class("dim-label")
        self.append(self._status)

    # -------------------------------------------------------------- export
    def _on_export(self, _btn) -> None:
        dlg = Gtk.FileDialog()
        dlg.set_title("Export package profile")
        stamp = _dt.date.today().isoformat()
        dlg.set_initial_name(f"mint-mechanic-profile-{stamp}.txt")
        dlg.save(self.get_root(), None, self._export_done)

    def _export_done(self, dlg, result) -> None:
        try:
            gfile = dlg.save_finish(result)
        except GLib.Error:
            return  # cancelled
        try:
            out = profiles.export_profile(gfile.get_path(), self._backend)
        except OSError as exc:
            self._flash(f"Export failed: {exc}")
            return
        self._flash(f"Exported profile to {out.name}")

    # -------------------------------------------------------------- import
    def _on_import(self, _btn) -> None:
        dlg = Gtk.FileDialog()
        dlg.set_title("Open package profile")
        dlg.open(self.get_root(), None, self._import_done)

    def _import_done(self, dlg, result) -> None:
        try:
            gfile = dlg.open_finish(result)
        except GLib.Error:
            return  # cancelled
        try:
            wanted = profiles.read_profile(gfile.get_path())
        except OSError as exc:
            self._flash(f"Could not read profile: {exc}")
            return
        # A profile is portable and hand-editable, so treat it as untrusted:
        # anything that isn't a valid package name is dropped before it can
        # reach the elevated apt call, and the user is told what was dropped.
        wanted, rejected = partition_names(wanted)
        installed = self._backend.installed_set()
        self._missing = [p for p in wanted if p not in installed]
        summary = (f"{gfile.get_basename()}: {len(wanted)} packages, "
                   f"{len(self._missing)} not installed here.")
        if rejected:
            summary += f"  ({len(rejected)} invalid entries ignored)"
        self._imp_lbl.set_text(summary)
        if rejected:
            shown = ", ".join(rejected[:3])
            more = f" (+{len(rejected) - 3} more)" if len(rejected) > 3 else ""
            self._flash(f"Ignored invalid entries in profile: {shown}{more}")
        self._populate_missing()

    def _populate_missing(self) -> None:
        self._list.remove_all()
        for name in self._missing:
            r = Gtk.ListBoxRow()
            r.set_activatable(False)
            lbl = Gtk.Label(label=name, xalign=0.0)
            lbl.set_margin_start(10)
            lbl.set_margin_end(10)
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            r.set_child(lbl)
            self._list.append(r)
        can = bool(self._missing) and pkexec_available()
        self._install_btn.set_sensitive(can)
        self._install_btn.set_label(
            f"Install missing ({len(self._missing)})" if self._missing
            else "Install missing")

    def _on_install_missing(self, _btn) -> None:
        if not self._missing:
            return
        self._install_btn.set_sensitive(False)
        self._flash(f"Authorizing install of {len(self._missing)} packages…")
        run_privileged(self._backend.install_argv(self._missing), self._install_done)

    def _install_done(self, res: ActionResult) -> None:
        if res.ok:
            self._flash(f"Installed {len(self._missing)} packages.")
            self._missing = []
            self._populate_missing()
        elif res.cancelled:
            self._flash("Install cancelled.")
            self._install_btn.set_sensitive(True)
        else:
            tail = (res.stderr or "unknown error").strip().splitlines()
            self._flash(f"Install failed: {tail[-1] if tail else 'unknown error'}")
            self._install_btn.set_sensitive(True)

    def _flash(self, message: str) -> None:
        self._status.set_text(message)
