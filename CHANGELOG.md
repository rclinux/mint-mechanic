# Changelog

All notable changes to **Mint Mechanic** are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Phase 4 — the action set (Cleaner, Startup, Uninstaller).**
  - **Cleaner** (`ltt/cleaner.py` + view): pick reclaimable items — APT package
    cache, orphaned packages (deborphan), thumbnail cache, Trash, old system
    logs — each with a best-effort size measured off the UI thread. User-level
    tasks run as you; selected root tasks are batched into a single pkexec call.
    Commands are fixed/audited (no interpolation). Arch-only maintenance omitted.
  - **Startup** (`ltt/startup.py` + view): toggle or remove `~/.config/autostart`
    entries via `GLib.KeyFile` (user-level, no root).
  - **Uninstaller** (`ltt/uninstaller_view.py`): search the manually-installed
    set (from the apt seam) and remove/purge a selection via pkexec; search-
    filtered for responsiveness with selection that persists across searches.
  - `ltt/actions.py` gained `run_local()` (unprivileged async runner) alongside
    `run_privileged()`.
- **App icon.** A Mint-green tachometer-gauge icon (scalable SVG + 48/128/256
  PNG raster sizes under `data/icons/hicolor/…`), echoing the Dashboard gauges.
  The app registers the dev-tree icon path and sets it as the default window /
  About-dialog icon, so it shows even before install.
- **Phase 3 — the Streamline view (v1 core complete).** Export the
  manually-installed package set to a portable, timestamped manifest, and import
  one to diff against this machine — listing what's missing and offering to
  install it (`ltt/streamline_view.py`). Uses GTK4 `Gtk.FileDialog` for
  save/open; the diff is one `dpkg-query` via the new `pkg.installed_set()`; any
  install routes through the apt seam and elevates via the shared pkexec runner.
  This closes the minimum-lovable v1 trio (Dashboard + Services + Streamline).
- **Phase 2 — the Services view.** Enable/disable systemd services with live
  status — the GUI Mint doesn't ship (`ltt/services_view.py`). Each row is built
  from a `registry.ServiceRow` by one generic builder (adding a service is
  adding a data row). State reads run as the user; a toggle elevates per-action
  via **pkexec** with `--now` (enables at boot *and* starts/stops now), and a
  dismissed polkit prompt cleanly reverts the switch. Unavailable units show
  "not installed" with the toggle disabled. New shared `ltt/actions.py` runs
  privileged commands off the UI thread (worker thread → `GLib.idle_add`), the
  single elevation seam the package operations will reuse.
- **Phase 1 — the Dashboard (signature screen).** Live animated **analog
  gauges** for CPU, RAM, Disk, and the **GPU dial** Stacer never had, drawn on
  Cairo (`ltt/gauges.py`): a 270° dial with tick marks, a load-colored value arc
  (green→amber→red), and a swinging needle that *eases* toward each reading —
  the animation timer only runs while the needle moves, so a steady system costs
  nothing. Theme-aware (needle/text/ticks follow the Cinnamon light/dark
  foreground). Below the gauges, a compact readouts strip: network throughput,
  load average, and uptime (`ltt/dashboard.py`). Polled once per second via a
  single GLib timeout that tears down with the view. The GPU dial is added only
  when a GPU reader is present (graceful degradation). `ltt/metrics.py` gained
  network-rate, load-average, and uptime readers.
- **Phase 0 — skeleton.** Runnable GTK4 app shell: main window with a sidebar
  and a stack of the three v1 views (Dashboard, Services, Streamline) as
  placeholders, plus an About dialog. Establishes the architecture seams with
  no features yet:
  - `ltt/pkg.py` — the single apt abstraction every package op routes through
    (the anti-ATT chokepoint); read-only paths (`list_manual`, `is_installed`)
    are live.
  - `ltt/metrics.py` — psutil + NVIDIA GPU reader behind a stable `Gauge` API,
    with graceful degradation (feeds the Phase 1 gauges).
  - `ltt/services.py` — systemctl status reads + elevated-toggle argv builders.
  - `ltt/profiles.py` — Streamline profile export/read (the recovery-story
    differentiator).
  - `ltt/registry.py` — data-driven feature rows (one dict per service).
  - `bin/ltt` launcher (dev-tree + system-install aware); `.desktop` entry.
- GPL-3.0 license; project scaffolding (README, this changelog, `.gitignore`).
