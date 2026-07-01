"""Gtk.Application entry point for Mint Mechanic.

The dashboard and all reads run as the user; mutating actions elevate
per-action via pkexec (never a blanket-root app). Phase 0 is read-only shell.
"""

from __future__ import annotations

import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import config, tools  # noqa: E402
from .window import MintMechanicWindow  # noqa: E402


def _register_icons() -> None:
    """Show our app icon even from the dev tree (uninstalled).

    Once installed the icon lives in the system hicolor theme; in the dev tree
    it sits under repo/data/icons, so add that to the theme search path.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icons = os.path.join(repo_root, "data", "icons")
    display = Gdk.Display.get_default()
    if display is not None and os.path.isdir(icons):
        Gtk.IconTheme.get_for_display(display).add_search_path(icons)


class MintMechanicApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=config.APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._window: MintMechanicWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        _register_icons()
        Gtk.Window.set_default_icon_name(config.APP_ICON)
        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", self._on_about)
        self.add_action(about)

        # Sibling-tool items stay enabled: launch when installed, otherwise
        # offer to install (P2: integrate by launch, never by merge).
        for tool in tools.SIBLINGS:
            action = Gio.SimpleAction.new(f"sibling-{tool.key}", None)
            action.connect("activate", lambda _a, _p, t=tool: self._on_sibling(t))
            self.add_action(action)

    def _on_sibling(self, tool: tools.SiblingTool) -> None:
        command = tool.installed_command()
        if command:
            tools.launch(command)
        else:
            self._show_get_dialog(tool)

    def _show_get_dialog(self, tool: tools.SiblingTool) -> None:
        dlg = Gtk.AlertDialog()
        dlg.set_modal(True)
        dlg.set_message(f"{tool.name} isn't installed")
        dlg.set_detail(
            f"{tool.blurb}\n\nIt's a separate companion tool. Open its project "
            f"page for instructions, or copy the install command to a terminal.")
        dlg.set_buttons(["Open project page", "Copy install command", "Close"])
        dlg.set_default_button(0)
        dlg.set_cancel_button(2)
        dlg.choose(self._window, None,
                   lambda d, r, t=tool: self._on_get_response(d, r, t))

    def _on_get_response(self, dlg, result, tool: tools.SiblingTool) -> None:
        try:
            choice = dlg.choose_finish(result)
        except GLib.Error:
            return  # dismissed
        if choice == 0:
            Gtk.UriLauncher.new(tool.repo_url).launch(self._window, None, None)
        elif choice == 1:
            self._window.get_clipboard().set(tool.install_command)

    def do_activate(self) -> None:
        if self._window is None:
            self._window = MintMechanicWindow(self)
        self._window.present()

    def _on_about(self, _action, _param) -> None:
        dlg = Gtk.AboutDialog(transient_for=self._window, modal=True)
        dlg.set_logo_icon_name(config.APP_ICON)
        dlg.set_program_name(config.APP_NAME)
        dlg.set_version(config.APP_VERSION)
        dlg.set_comments(config.APP_TAGLINE)
        dlg.set_website(config.APP_WEBSITE)
        dlg.set_license_type(Gtk.License.GPL_3_0)
        dlg.present()


def main(argv: list[str] | None = None) -> int:
    return MintMechanicApp().run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
