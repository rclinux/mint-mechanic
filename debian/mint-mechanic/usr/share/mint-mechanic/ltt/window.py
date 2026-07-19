"""Main window: a sidebar + a stack of the three v1 views.

Dashboard (live gauges), Services (systemctl toggles), and Streamline (package
profiles) are all live. Later phases add more views to the same stack without
touching this shell.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

from . import config, tools  # noqa: E402
from .cleaner_view import CleanerView  # noqa: E402
from .dashboard import DashboardView  # noqa: E402
from .health_strip import HealthStrip  # noqa: E402
from .services_view import ServicesView  # noqa: E402
from .startup_view import StartupView  # noqa: E402
from .streamline_view import StreamlineView  # noqa: E402
from .uninstaller_view import UninstallerView  # noqa: E402


class MintMechanicWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title=config.APP_NAME)
        self.set_default_size(880, 600)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_btn.set_menu_model(_build_menu())
        header.pack_end(menu_btn)

        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        sidebar = Gtk.StackSidebar(stack=stack)
        sidebar.set_size_request(180, -1)

        stack.add_titled(DashboardView(), "dashboard", "Dashboard")
        stack.add_titled(ServicesView(), "services", "Services")
        stack.add_titled(StartupView(), "startup", "Startup")
        stack.add_titled(CleanerView(), "cleaner", "Cleaner")
        stack.add_titled(UninstallerView(), "uninstaller", "Uninstaller")
        stack.add_titled(StreamlineView(), "streamline", "Streamline")

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        content.append(sidebar)
        content.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        stack.set_hexpand(True)
        content.append(stack)

        # Outer: content over a persistent GO/NO-GO health strip.
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.append(content)
        outer.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        outer.append(HealthStrip())
        self.set_child(outer)


def _build_menu() -> Gio.Menu:
    """Primary menu. Sibling items read 'Launch …' when installed, 'Get …' when
    not, so the capability is always discoverable."""
    menu = Gio.Menu()

    siblings = Gio.Menu()
    for tool in tools.SIBLINGS:
        installed = tool.installed_command() is not None
        label = f"Launch {tool.name}" if installed else f"Get {tool.name}…"
        siblings.append(label, f"app.sibling-{tool.key}")
    menu.append_section("Sibling tools", siblings)

    about = Gio.Menu()
    about.append("About Mint Mechanic", "app.about")
    menu.append_section(None, about)
    return menu
