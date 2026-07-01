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
from gi.repository import Gdk, Gio, Gtk  # noqa: E402

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

        # Sibling-tool launches — enabled only when the tool is installed (P2:
        # integrate by launch, never by merge).
        self._add_launch_action("launch-drt", tools.drt_command)
        self._add_launch_action("launch-dashboard", tools.dashboard_command)

    def _add_launch_action(self, name, resolver) -> None:
        action = Gio.SimpleAction.new(name, None)
        command = resolver()
        action.set_enabled(command is not None)
        action.connect("activate", lambda _a, _p, c=command: tools.launch(c))
        self.add_action(action)

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
