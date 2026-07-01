"""Gtk.Application entry point for Mint Mechanic.

The dashboard and all reads run as the user; mutating actions elevate
per-action via pkexec (never a blanket-root app). Phase 0 is read-only shell.
"""

from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

from . import config  # noqa: E402
from .window import MintMechanicWindow  # noqa: E402


class MintMechanicApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=config.APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._window: MintMechanicWindow | None = None

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", self._on_about)
        self.add_action(about)

    def do_activate(self) -> None:
        if self._window is None:
            self._window = MintMechanicWindow(self)
        self._window.present()

    def _on_about(self, _action, _param) -> None:
        dlg = Gtk.AboutDialog(transient_for=self._window, modal=True)
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
