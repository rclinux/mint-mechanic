"""The Services view — enable/disable systemd services (the GUI Mint lacks).

Every row is built from a registry.ServiceRow dict by one generic builder
(design principle P4): adding a service is adding a data row, not new UI code.
Reading state needs no root; toggling elevates per-action via pkexec (--now, so
the switch both enables-at-boot and starts/stops right now). A dismissed polkit
prompt cleanly reverts the switch.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from . import registry, services  # noqa: E402
from .actions import ActionResult, pkexec_available, run_privileged  # noqa: E402


class _ServiceRowUI:
    """Holds the widgets + wiring for one service row."""

    def __init__(self, view: ServicesView, row: registry.ServiceRow) -> None:
        self.view = view
        self.row = row

        self.widget = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.widget.set_margin_top(8)
        self.widget.set_margin_bottom(8)
        self.widget.set_margin_start(10)
        self.widget.set_margin_end(10)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        text.set_hexpand(True)
        name = Gtk.Label(label=row.label, xalign=0.0)
        name.add_css_class("heading")
        desc = Gtk.Label(label=row.description, xalign=0.0)
        desc.add_css_class("dim-label")
        text.append(name)
        text.append(desc)
        self.widget.append(text)

        self.status = Gtk.Label(label="…", xalign=1.0)
        self.status.add_css_class("dim-label")
        self.widget.append(self.status)

        self.switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self._handler = self.switch.connect("state-set", self._on_toggle)
        self.widget.append(self.switch)

    def refresh(self) -> None:
        st = services.state(self.row.unit)
        # set the switch without firing the toggle handler
        self.switch.handler_block(self._handler)
        self.switch.set_active(st.enabled)
        self.switch.set_state(st.enabled)
        self.switch.handler_unblock(self._handler)

        can_toggle = st.available and pkexec_available()
        self.switch.set_sensitive(can_toggle)
        if not st.available:
            self.status.set_text("not installed")
        else:
            self.status.set_text("running" if st.active else "stopped")

    def _on_toggle(self, switch: Gtk.Switch, requested: bool) -> bool:
        # Keep the visual state until the action actually succeeds.
        switch.set_sensitive(False)
        self.status.set_text("authorizing…")
        argv = (services.enable_argv(self.row.unit) if requested
                else services.disable_argv(self.row.unit))
        run_privileged(argv, on_done=self._after)
        return True  # we drive set_state() ourselves in _after()

    def _after(self, res: ActionResult) -> None:
        if res.ok:
            self.view.flash(f"{self.row.label}: done.")
        elif res.cancelled:
            self.view.flash(f"{self.row.label}: cancelled.")
        else:
            self.view.flash(f"{self.row.label}: failed — "
                            f"{(res.stderr or 'unknown error').strip().splitlines()[-1]}")
        self.switch.set_sensitive(True)
        self.refresh()


class ServicesView(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._rows: list[_ServiceRowUI] = []

        # header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(14)
        header.set_margin_bottom(6)
        header.set_margin_start(12)
        header.set_margin_end(12)
        title = Gtk.Label(xalign=0.0, hexpand=True)
        title.set_markup("<span size='large' weight='bold'>System Services</span>")
        header.append(title)
        refresh = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh.set_tooltip_text("Refresh service states")
        refresh.connect("clicked", lambda _b: self._refresh_all())
        header.append(refresh)
        self.append(header)

        if not pkexec_available():
            warn = Gtk.Label(xalign=0.0)
            warn.set_margin_start(12)
            warn.add_css_class("dim-label")
            warn.set_text("pkexec not found — toggles are read-only.")
            self.append(warn)

        listbox = Gtk.ListBox()
        listbox.add_css_class("boxed-list")
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.set_margin_start(12)
        listbox.set_margin_end(12)
        for row in registry.services():
            ui = _ServiceRowUI(self, row)
            self._rows.append(ui)
            lb_row = Gtk.ListBoxRow()
            lb_row.set_activatable(False)
            lb_row.set_child(ui.widget)
            listbox.append(lb_row)
        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(listbox)
        self.append(scroller)

        self._status = Gtk.Label(xalign=0.0)
        self._status.add_css_class("dim-label")
        self._status.set_margin_start(14)
        self._status.set_margin_top(4)
        self._status.set_margin_bottom(8)
        self.append(self._status)

        self.connect("map", lambda _w: self._refresh_all())

    def _refresh_all(self) -> None:
        for ui in self._rows:
            ui.refresh()

    def flash(self, message: str) -> None:
        self._status.set_text(message)
