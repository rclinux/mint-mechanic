"""Streamline package profiles — Mint Mechanic's signature differentiator.

Export the set of manually-installed packages to a timestamped, human-readable
manifest = a portable bill-of-materials that plugs straight into Ron's
EMERGENCY.md from-scratch rebuild story. Import turns a manifest back into an
install plan. Neither Stacer nor Mint ships this.

All package operations go through ltt.pkg (principle P5) — this module never
shells out to apt directly. Phase 0 establishes the format + export; Phase 3
wires import/apply and the UI.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

from . import config
from .pkg import PackageBackend, default_backend

_HEADER = "# Mint Mechanic — Streamline package profile"


def export_profile(path: str | Path, backend: PackageBackend | None = None) -> Path:
    """Write the manually-installed set to `path` as a commented manifest."""
    backend = backend or default_backend()
    pkgs = backend.list_manual()
    stamp = _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    path = Path(path)
    lines = [
        _HEADER,
        f"# generated: {stamp}",
        f"# tool: {config.APP_NAME} v{config.APP_VERSION}   backend: {backend.name}",
        f"# count: {len(pkgs)}",
        "#",
        "# One package per line. Edit freely; lines starting with # are ignored.",
        "",
        *pkgs,
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def read_profile(path: str | Path) -> list[str]:
    """Parse a manifest back into a package list (ignores blanks/comments)."""
    text = Path(path).read_text(encoding="utf-8")
    return [ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]
