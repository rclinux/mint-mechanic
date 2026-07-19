"""Run a privileged action off the UI thread (the per-action pkexec seam).

Mutating operations (toggle a service, install/remove a package) elevate one at
a time via pkexec — never a blanket-root app. pkexec pops the polkit dialog, so
the call must not block the GTK main loop: we run it on a worker thread and hand
the result back on the main loop via GLib.idle_add.

This is shared by the Services view now and the package operations later, so the
elevation pattern lives in exactly one place.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from dataclasses import dataclass
from collections.abc import Callable

from gi.repository import GLib


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    argv: list[str]
    stdout: str = ""
    stderr: str = ""
    cancelled: bool = False  # user dismissed the polkit prompt


def pkexec_available() -> bool:
    return shutil.which("pkexec") is not None


def _run_async(argv: list[str], elevated: bool,
               on_done: Callable[[ActionResult], None] | None) -> None:
    def worker() -> None:
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, check=False)
            res = ActionResult(
                ok=proc.returncode == 0,
                argv=argv,
                stdout=proc.stdout,
                stderr=proc.stderr,
                # pkexec exit 126 = the polkit dialog was dismissed/denied
                cancelled=elevated and proc.returncode == 126,
            )
        except OSError as exc:
            res = ActionResult(False, argv, stderr=str(exc))
        if on_done is not None:
            GLib.idle_add(on_done, res)

    threading.Thread(target=worker, daemon=True).start()


def run_privileged(argv: list[str],
                   on_done: Callable[[ActionResult], None] | None = None) -> None:
    """Run `argv` (expected to start with pkexec) on a worker thread.

    `on_done` is invoked on the GTK main loop with the ActionResult.
    """
    _run_async(argv, elevated=True, on_done=on_done)


def run_local(argv: list[str],
              on_done: Callable[[ActionResult], None] | None = None) -> None:
    """Run an unprivileged `argv` off the UI thread (same result contract)."""
    _run_async(argv, elevated=False, on_done=on_done)
