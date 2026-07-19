"""Mint Mechanic (LTT) — a maintained, Cinnamon-native successor to Stacer.

Package layout (the seams are established in Phase 0; features fill them later):
    config.py    — identity/version constants
    app.py       — Gtk.Application entry point
    window.py    — main window: sidebar + stack of views
    metrics.py   — psutil + GPU reader behind a stable API (Dashboard)
    services.py  — systemctl wrappers (Services)
    profiles.py  — Streamline package-profile export/import
    pkg.py       — THE single apt abstraction; every package op routes here
    registry.py  — data-driven feature rows + one generic row builder
"""

from .config import APP_VERSION

__version__ = APP_VERSION
