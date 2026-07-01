# Changelog

All notable changes to **Mint Mechanic** are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-07-01

First release. Mint Mechanic ships its full v1 feature set — Dashboard,
Services, Startup, Cleaner, Uninstaller and Streamline views, plus the GO/NO-GO
health strip and sibling-tool launch — together with packaging (a `.deb` build
plus an `install.sh` make-install path), a man page, and an application icon.

### Changed
- **Sibling-tool menu items are now always enabled and self-explaining.** Instead
  of greying out when a companion tool isn't installed, each item reads
  "Launch <tool>" when present and "Get <tool>…" when not. Choosing a "Get" item
  opens a small dialog explaining the tool with **Open project page** (browser to
  the repo) and **Copy install command** (the `git clone … && sudo ./install.sh`
  line) — so the option is discoverable without Mint Mechanic ever downloading or
  running a remote installer itself. (`ltt/tools.py` gained per-tool metadata;
  the menu is now built in code with dynamic labels.)

### Fixed
- **Cleaner sizes now measure contents, not the enclosing directory.** APT cache,
  Trash, and the thumbnail cache read **"empty"** once cleared, instead of the
  leftover KBs of an emptied-but-unshrunk directory inode (an ext4 quirk: a
  directory that once held thousands of files keeps its own allocated size — e.g.
  a cleaned APT `archives/` still `du`'d to 68K, an emptied Trash to 16K). The
  measurements now sum the actual files (`.deb`s, trashed items, thumbnail
  files). (Reported by Ron.)
- **Cleaner: Trash now runs last.** Selected root tasks run first, then user
  tasks with Trash forced last, so an emptied Trash also clears anything
  discarded earlier in the run. The empty command also clears the
  `directorysizes`/`expunged` bookkeeping. Completion status now says
  "re-measured" to make the automatic refresh obvious.

### Added
- **Phase 6 — packaging.** A self-contained `.deb` builder (`build-deb.sh`,
  version read from `config.py`, lintian-clean) and an `install.sh` /
  `uninstall.sh` make-install path, both laying down the same system layout
  (`/usr/share/mint-mechanic`, `/usr/bin/ltt`, the desktop entry and hicolor
  icons). Adds a man page (`ltt(1)`) and README screenshots.
- **Phase 5 — health strip + sibling-tool launch (feature set complete).**
  - A persistent **GO / NO-GO health strip** across the bottom of the window
    (`ltt/health.py` + `ltt/health_strip.py`): quick read-only checks — root
    disk usage, failed systemd units (benign live-ISO units filtered), pending
    updates, and reboot-required — as colored pills rolling up to one verdict,
    refreshed off the UI thread.
  - **Sibling-tool launch** (`ltt/tools.py`): menu items that open
    disk-recovery-tool and workstation-dashboard when installed (detached), and
    are disabled when they aren't — integration by launch, never by merge.
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
