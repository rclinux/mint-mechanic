"""The Startup view — toggle or remove per-user autostart entries.

All actions are user-level (no pkexec): a switch edits the entry's
X-GNOME-Autostart-enabled key; the remove button deletes the .desktop file.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Pango  # noqa: E402

from . import startup  # noqa: E402


class StartupView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(14)
        header.set_margin_bottom(6)
        header.set_margin_start(12)
        header.set_margin_end(12)
        title = Gtk.Label(xalign=0.0, hexpand=True)
        title.set_markup("<span size='large' weight='bold'>Startup Applications</span>")
        header.append(title)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.set_tooltip_text("Reload")
        refresh.connect("clicked", lambda _b: self._reload())
        header.append(refresh)
        self.append(header)

        self._listbox = Gtk.ListBox()
        self._listbox.add_css_class("boxed-list")
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.set_margin_start(12)
        self._listbox.set_margin_end(12)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self._listbox)
        self.append(scroller)

        self._status = Gtk.Label(xalign=0.0)
        self._status.set_wrap(True)
        self._status.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._status.set_max_width_chars(1)
        self._status.add_css_class("dim-label")
        self._status.set_margin_start(14)
        self._status.set_margin_top(4)
        self._status.set_margin_bottom(8)
        self.append(self._status)

        self.connect("map", lambda _w: self._reload())

    def _reload(self) -> None:
        self._listbox.remove_all()
        entries = startup.list_entries()
        if not entries:
            self._status.set_text("No per-user startup entries in ~/.config/autostart.")
        else:
            self._status.set_text(f"{len(entries)} startup entries.")
        for entry in entries:
            self._listbox.append(self._build_row(entry))

    def _build_row(self, entry: startup.AutostartEntry) -> Gtk.ListBoxRow:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(10)
        box.set_margin_end(10)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1, hexpand=True)
        name = Gtk.Label(label=entry.name, xalign=0.0)
        name.add_css_class("heading")
        text.append(name)
        if entry.comment:
            desc = Gtk.Label(label=entry.comment, xalign=0.0)
            desc.add_css_class("dim-label")
            desc.set_ellipsize(3)  # END
            text.append(desc)
        box.append(text)

        remove = Gtk.Button(icon_name="user-trash-symbolic")
        remove.set_valign(Gtk.Align.CENTER)
        remove.set_tooltip_text("Remove this startup entry")
        remove.add_css_class("flat")
        remove.connect("clicked", self._on_remove, entry)
        box.append(remove)

        switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        switch.set_active(entry.enabled)
        switch.connect("state-set", self._on_toggle, entry)
        box.append(switch)

        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row.set_child(box)
        return row

    def _on_toggle(self, switch: Gtk.Switch, requested: bool,
                   entry: startup.AutostartEntry) -> bool:
        if startup.set_enabled(entry, requested):
            self._status.set_text(
                f"{entry.name}: {'enabled' if requested else 'disabled'}.")
            switch.set_state(requested)
        else:
            self._status.set_text(f"{entry.name}: could not update.")
            switch.set_state(not requested)
        return True

    def _on_remove(self, _btn, entry: startup.AutostartEntry) -> None:
        if startup.remove(entry):
            self._status.set_text(f"Removed {entry.name}.")
            self._reload()
        else:
            self._status.set_text(f"Could not remove {entry.name}.")
