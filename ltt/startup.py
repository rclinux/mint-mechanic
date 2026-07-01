"""Startup applications — read/toggle/remove ~/.config/autostart entries.

All user-level (no root): these are the per-user autostart .desktop files. Parsing
and editing go through GLib.KeyFile, which is built for the .desktop format and
preserves the file structure on write. An entry counts as enabled unless it is
explicitly disabled (X-GNOME-Autostart-enabled=false) or hidden (Hidden=true).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from gi.repository import GLib

_DIR = os.path.join(GLib.get_user_config_dir(), "autostart")
_GROUP = "Desktop Entry"


@dataclass(frozen=True)
class AutostartEntry:
    path: str
    name: str
    comment: str
    enabled: bool


def _load(path: str) -> GLib.KeyFile | None:
    kf = GLib.KeyFile()
    try:
        kf.load_from_file(path, GLib.KeyFileFlags.KEEP_COMMENTS
                          | GLib.KeyFileFlags.KEEP_TRANSLATIONS)
    except GLib.Error:
        return None
    return kf


def _get_bool(kf: GLib.KeyFile, key: str, default: bool) -> bool:
    try:
        return kf.get_boolean(_GROUP, key)
    except GLib.Error:
        return default


def _get_str(kf: GLib.KeyFile, key: str, default: str = "") -> str:
    try:
        return kf.get_string(_GROUP, key)
    except GLib.Error:
        return default


def list_entries() -> list[AutostartEntry]:
    if not os.path.isdir(_DIR):
        return []
    out: list[AutostartEntry] = []
    for fn in sorted(os.listdir(_DIR)):
        if not fn.endswith(".desktop"):
            continue
        path = os.path.join(_DIR, fn)
        kf = _load(path)
        if kf is None:
            continue
        enabled = (_get_bool(kf, "X-GNOME-Autostart-enabled", True)
                   and not _get_bool(kf, "Hidden", False))
        out.append(AutostartEntry(
            path=path,
            name=_get_str(kf, "Name", fn[:-len(".desktop")]),
            comment=_get_str(kf, "Comment"),
            enabled=enabled,
        ))
    return out


def set_enabled(entry: AutostartEntry, enabled: bool) -> bool:
    kf = _load(entry.path)
    if kf is None:
        return False
    kf.set_boolean(_GROUP, "X-GNOME-Autostart-enabled", enabled)
    if enabled:
        try:
            kf.remove_key(_GROUP, "Hidden")   # some toolkits disable via Hidden
        except GLib.Error:
            pass
    try:
        kf.save_to_file(entry.path)
    except GLib.Error:
        return False
    return True


def remove(entry: AutostartEntry) -> bool:
    try:
        os.remove(entry.path)
        return True
    except OSError:
        return False
