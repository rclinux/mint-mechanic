"""Central constants for Mint Mechanic (LTT).

One place for identity/version so packaging, the About view, and the window
title never drift. Version bumps follow the DRT convention (+0.1 per major
change: config.py + packaging + CHANGELOG + git tag).
"""

APP_NAME = "Mint Mechanic"
APP_ID = "io.github.rclinux.MintMechanic"
APP_ICON = "mint-mechanic"
APP_COMMAND = "mint-mechanic"
APP_VERSION = "0.7.0"
APP_TAGLINE = "The maintained tune-up tool for Linux Mint"
APP_WEBSITE = "https://github.com/rclinux/mint-mechanic"

# Minimum-lovable v1 scope (settled 2026-07-01). The dashboard/services/
# streamline views are the only ones wired for v1; the rest are later phases.
V1_VIEWS = ("dashboard", "services", "streamline")
