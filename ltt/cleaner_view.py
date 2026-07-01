"""The System Cleaner view — pick reclaimable items and clear them.

Each row is a cleaner.CleanTask (data-driven). User-level tasks run as you;
selected root-level tasks are batched into a single pkexec call so you're asked
for a password at most once. Size measurements run on a worker thread so opening
the tab never blocks.
"""

from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import cleaner  # noqa: E402
from .actions import ActionResult, pkexec_available, run_local, run_privileged  # noqa: E402


class _TaskRow:
    def __init__(self, task: cleaner.CleanTask) -> None:
        self.task = task
        self.widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.widget.set_margin_top(8)
        self.widget.set_margin_bottom(8)
        self.widget.set_margin_start(10)
        self.widget.set_margin_end(10)

        self.check = Gtk.CheckButton()
        self.check.set_valign(Gtk.Align.CENTER)
        self.widget.append(self.check)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        name = Gtk.Label(label=task.label, xalign=0.0)
        name.add_css_class("heading")
        desc = Gtk.Label(label=task.description, xalign=0.0)
        desc.add_css_class("dim-label")
        text.append(name)
        text.append(desc)
        self.widget.append(text)

        self.size = Gtk.Label(label="…", xalign=1.0)
        self.size.add_css_class("dim-label")
        self.widget.append(self.size)

        if not task.available:
            self.check.set_sensitive(False)
            self.size.set_text("unavailable")


class CleanerView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._rows: list[_TaskRow] = []
        self._busy = False

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(14)
        header.set_margin_bottom(6)
        header.set_margin_start(12)
        header.set_margin_end(12)
        title = Gtk.Label(xalign=0.0, hexpand=True)
        title.set_markup("<span size='large' weight='bold'>System Cleaner</span>")
        header.append(title)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.set_tooltip_text("Re-measure")
        refresh.connect("clicked", lambda _b: self._measure_async())
        header.append(refresh)
        self.append(header)

        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.set_margin_start(12)
        listbox.set_margin_end(12)
        for task in cleaner.tasks():
            row = _TaskRow(task)
            self._rows.append(row)
            lb = Gtk.ListBoxRow()
            lb.set_activatable(False)
            lb.set_child(row.widget)
            listbox.append(lb)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(listbox)
        self.append(scroller)

        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        footer.set_margin_start(14)
        footer.set_margin_end(14)
        footer.set_margin_top(8)
        footer.set_margin_bottom(10)
        self._status = Gtk.Label(xalign=0.0, hexpand=True)
        self._status.add_css_class("dim-label")
        footer.append(self._status)
        self._clean_btn = Gtk.Button(label="Clean selected")
        self._clean_btn.add_css_class("destructive-action")
        self._clean_btn.connect("clicked", self._on_clean)
        footer.append(self._clean_btn)
        self.append(footer)

        self.connect("map", lambda _w: self._measure_async())

    # ------------------------------------------------------------- measuring
    def _measure_async(self) -> None:
        rows = [r for r in self._rows if r.task.available]
        for r in rows:
            r.size.set_text("…")

        def work() -> None:
            for r in rows:
                text = r.task.measure()
                GLib.idle_add(r.size.set_text, text or "—")

        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- cleaning
    def _on_clean(self, _btn) -> None:
        if self._busy:
            return
        selected = [r.task for r in self._rows
                    if r.task.available and r.check.get_active()]
        if not selected:
            self._status.set_text("Nothing selected.")
            return
        if any(t.root for t in selected) and not pkexec_available():
            self._status.set_text("pkexec not found — cannot run root cleanups.")
            return
        self._busy = True
        self._clean_btn.set_sensitive(False)
        self._status.set_text("Cleaning…")

        user_cmds = [t.command for t in selected if not t.root]
        self._root_cmds = [t.command for t in selected if t.root]
        if user_cmds:
            run_local(["bash", "-c", "; ".join(user_cmds)], self._after_user)
        else:
            self._run_root()

    def _after_user(self, _res: ActionResult) -> None:
        self._run_root()

    def _run_root(self) -> None:
        if self._root_cmds:
            run_privileged(["pkexec", "bash", "-c", "; ".join(self._root_cmds)],
                           self._after_root)
        else:
            self._finish(cancelled=False, ok=True)

    def _after_root(self, res: ActionResult) -> None:
        self._finish(cancelled=res.cancelled, ok=res.ok)

    def _finish(self, cancelled: bool, ok: bool) -> None:
        self._busy = False
        self._clean_btn.set_sensitive(True)
        for r in self._rows:
            r.check.set_active(False)
        if cancelled:
            self._status.set_text("Cancelled.")
        elif ok:
            self._status.set_text("Done.")
        else:
            self._status.set_text("Some cleanups reported an error.")
        self._measure_async()
