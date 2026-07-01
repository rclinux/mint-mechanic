"""Main window: a sidebar + a stack of views.

Phase 0 ships the shell only — the three v1 views (Dashboard, Services,
Streamline) are placeholders that prove the structure. Each later phase
replaces one placeholder with the real view; the window itself won't change.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from . import config  # noqa: E402
from .dashboard import DashboardView  # noqa: E402
from .services_view import ServicesView  # noqa: E402

# Views still awaiting their real implementation: (name, title, icon, note).
_PLACEHOLDERS = (
    ("streamline", "Streamline", "document-save-symbolic",
     "Export/import your package profile — Phase 3."),
)


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
        for name, title, icon, note in _PLACEHOLDERS:
            stack.add_titled(_placeholder(title, icon, note), name, title)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        box.append(sidebar)
        box.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        stack.set_hexpand(True)
        box.append(stack)
        self.set_child(box)


def _placeholder(title: str, icon: str, note: str) -> Gtk.Widget:
    """A centered icon + title + note — a view's Phase-0 stand-in."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_valign(Gtk.Align.CENTER)
    box.set_halign(Gtk.Align.CENTER)
    box.set_hexpand(True)
    box.set_vexpand(True)

    img = Gtk.Image.new_from_icon_name(icon)
    img.set_pixel_size(64)
    box.append(img)

    heading = Gtk.Label()
    heading.set_markup(f"<span size='x-large' weight='bold'>{title}</span>")
    box.append(heading)

    sub = Gtk.Label(label=note)
    sub.add_css_class("dim-label")
    box.append(sub)
    return box


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
