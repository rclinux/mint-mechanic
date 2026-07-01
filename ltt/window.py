"""Main window: a sidebar + a stack of the three v1 views.

Dashboard (live gauges), Services (systemctl toggles), and Streamline (package
profiles) are all live. Later phases add more views to the same stack without
touching this shell.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from . import config  # noqa: E402
from .dashboard import DashboardView  # noqa: E402
from .services_view import ServicesView  # noqa: E402
from .streamline_view import StreamlineView  # noqa: E402


class MintMechanicWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title=config.APP_NAME)
        self.set_default_size(880, 600)

        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gtk.Builder.new_from_string(_MENU_XML, -1).get_object("primary-menu")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)

        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        sidebar = Gtk.StackSidebar(stack=stack)
        sidebar.set_size_request(180, -1)

        stack.add_titled(DashboardView(), "dashboard", "Dashboard")
        stack.add_titled(ServicesView(), "services", "Services")
        stack.add_titled(StreamlineView(), "streamline", "Streamline")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.append(sidebar)
        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        stack.set_hexpand(True)
        box.append(stack)
        self.set_child(box)


_MENU_XML = """
<interface>
  <menu id="primary-menu">
    <section>
      <item>
        <attribute name="label">About Mint Mechanic</attribute>
        <attribute name="action">app.about</attribute>
      </item>
    </section>
  </menu>
</interface>
"""
