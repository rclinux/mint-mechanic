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
from gi.repository import GLib, Gtk, Pango  # noqa: E402

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
        # Descriptions wrap rather than run off the edge. A GTK label defaults to
        # a single unwrapped line, so any text longer than the row silently
        # clips at the right margin with no ellipsis to hint at it.
        desc = Gtk.Label(label=task.description, xalign=0.0, wrap=True)
        desc.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        desc.set_max_width_chars(1)   # wrap to the allocated width, don't demand it
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
        self._orphan_note = ""
        self._did_other_work = False

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
        # The status line carries refusal messages ("Refused: this would also
        # remove cinnamon ..."), so it must never be clipped -- a truncated
        # safety message is worse than an ugly one.
        self._status = Gtk.Label(xalign=0.0, hexpand=True, wrap=True)
        self._status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._status.set_max_width_chars(1)
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
        self._ok = True
        self._clean_btn.set_sensitive(False)

        # Run the root batch first, then user tasks with Trash forced LAST, so an
        # emptied Trash also catches anything discarded earlier in the run.
        self._root_cmds = [t.command for t in selected
                           if t.root and not t.confirm and t.command]
        user_tasks = sorted((t for t in selected if not t.root),
                            key=lambda t: t.key == "trash")
        self._user_cmds = [t.command for t in user_tasks]
        self._did_other_work = bool(self._root_cmds or self._user_cmds)

        # Tasks that remove packages must show their real blast radius first.
        confirm_tasks = [t for t in selected if t.confirm]
        if confirm_tasks:
            self._status.set_text("Checking what would be removed…")
            self._begin_orphan_preview()
            return

        self._status.set_text("Cleaning…")
        self._run_root()

    # ------------------------------------------------- previewed package purge
    def _begin_orphan_preview(self) -> None:
        """Compute the true removal set off-thread, then decide (see cleaner.py).

        Never purge from deborphan's list directly: it names ~27 libraries, but
        apt's cascade removed 179 packages including the desktop environment.
        """
        def work() -> None:
            candidates = cleaner.orphan_list()
            preview = cleaner.purge_preview(candidates)
            failed = cleaner.purge_preview_failed(candidates, preview)
            critical = cleaner.critical_in(preview)
            GLib.idle_add(self._orphan_previewed, candidates, preview,
                          critical, failed)

        threading.Thread(target=work, daemon=True).start()

    def _orphan_previewed(self, candidates: list[str], preview: list[str],
                          critical: list[str], failed: bool) -> None:
        if failed:
            # An empty preview for a non-empty request means the simulation
            # failed, not that there is nothing to do. Never proceed on that.
            self._finish_orphans(
                "Could not determine what would be removed — orphan purge "
                "skipped.")
            return
        if not candidates or not preview:
            self._finish_orphans("No orphaned packages to remove.")
            return
        if critical:
            shown = ", ".join(critical[:4])
            more = f" and {len(critical) - 4} more" if len(critical) > 4 else ""
            self._finish_orphans(
                f"Refused: removing these orphans would also remove "
                f"{shown}{more} — your desktop or graphics stack. Nothing done.")
            return
        self._confirm_orphans(candidates, preview)

    def _confirm_orphans(self, candidates: list[str], preview: list[str]) -> None:
        extra = len(preview) - len(candidates)
        detail = (f"{len(candidates)} orphaned packages were found, but removing "
                  f"them would remove {len(preview)} packages in total"
                  + (f" ({extra} additional through dependencies)" if extra > 0
                     else "") + ".\n\n"
                  + ", ".join(preview[:40])
                  + (f"\n\n…and {len(preview) - 40} more."
                     if len(preview) > 40 else ""))
        dlg = Gtk.AlertDialog()
        dlg.set_modal(True)
        dlg.set_message(f"Remove {len(preview)} packages?")
        dlg.set_detail(detail)
        dlg.set_buttons(["Cancel", "Remove them"])
        dlg.set_default_button(0)
        dlg.set_cancel_button(0)
        dlg.choose(self.get_root(), None,
                   lambda d, r: self._on_orphan_choice(d, r, candidates))

    def _on_orphan_choice(self, dlg, result, candidates: list[str]) -> None:
        try:
            choice = dlg.choose_finish(result)
        except GLib.Error:
            choice = 0
        if choice != 1:
            self._finish_orphans("Orphan purge cancelled.")
            return
        self._status.set_text("Removing orphaned packages…")
        run_privileged(cleaner.orphan_purge_argv(candidates),
                       self._after_orphans)

    def _after_orphans(self, res: ActionResult) -> None:
        if res.cancelled:
            self._finish_orphans("Orphan purge cancelled.")
            return
        self._ok = self._ok and res.ok
        self._status.set_text("Cleaning…")
        self._run_root()

    def _finish_orphans(self, message: str) -> None:
        """Report on the orphan step, then continue with the other tasks."""
        self._status.set_text(message)
        self._orphan_note = message
        self._run_root()

    def _run_root(self) -> None:
        if self._root_cmds:
            run_privileged(["pkexec", "bash", "-c", "; ".join(self._root_cmds)],
                           self._after_root)
        else:
            self._run_user()

    def _after_root(self, res: ActionResult) -> None:
        if res.cancelled:
            self._finish(cancelled=True, ok=False)
            return
        self._ok = self._ok and res.ok
        self._run_user()

    def _run_user(self) -> None:
        if self._user_cmds:
            run_local(["bash", "-c", "; ".join(self._user_cmds)], self._after_user)
        else:
            self._finish(cancelled=False, ok=self._ok)

    def _after_user(self, res: ActionResult) -> None:
        self._finish(cancelled=False, ok=self._ok and res.ok)

    def _finish(self, cancelled: bool, ok: bool) -> None:
        self._busy = False
        self._clean_btn.set_sensitive(True)
        for r in self._rows:
            r.check.set_active(False)
        if cancelled:
            msg = "Cancelled."
        elif ok:
            msg = "Done — re-measured."
        else:
            msg = "Completed with some errors — re-measured."
        # A refusal or skip from the orphan step is the most important thing
        # that happened; never let a generic "Done" bury it. When the orphan
        # step was the ONLY thing selected, its message stands alone -- other-
        # wise the line reads "Nothing done.  Done — re-measured."
        if self._orphan_note:
            msg = f"{self._orphan_note}  {msg}" if self._did_other_work else self._orphan_note
            self._orphan_note = ""
        self._status.set_text(msg)
        self._measure_async()
