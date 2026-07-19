# Changelog

All notable changes to **Mint Mechanic** are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [0.6.0] - 2026-07-19

### Fixed
- **Long text was cut off at the right edge instead of wrapping.** GTK labels are
  a single unwrapped line by default, so anything longer than the row clipped
  silently — with no ellipsis to even hint text was missing. Reported against the
  Cleaner's "Orphaned packages" description, whose text grew in 0.3.0.

  This mattered beyond appearance: the same unwrapped labels carry the
  **removal-refusal messages**. A refusal that reads "Refused: removing these
  orphans would also remove cinnamon, cinnamon-common," and then stops hides the
  reason the operation was refused. Descriptions and status lines across the
  Cleaner, Services, Uninstaller, Streamline and Startup views now wrap.
- The Cleaner's status read "Nothing done.  Done — re-measured." when the orphan
  step was the only selected task; its message now stands alone.

## [0.5.0] - 2026-07-19

Distribution release. Mint Mechanic now has an update channel — the thing that
turns "maintained" from an intention into a fact.

### Added
- **Published to `ppa:rclinux/mint-mechanic`.** Installing from the PPA means
  fixes arrive through normal system updates. Every release before this one was
  download-only: anyone who installed 0.1.0 had no way to learn about, or
  receive, the security and safety fixes in 0.2.0 through 0.4.0. Launchpad
  builds and signs packages from published source, so the signing key never
  touches a build server.
- **AppStream metainfo** (`data/io.github.rclinux.MintMechanic.metainfo.xml`),
  so the application lists properly in software centres with description,
  screenshots and release notes.
- `build-source.sh` for producing (optionally signed) source uploads.
- Tests asserting the app version, `debian/changelog`, man page, README install
  line and AppStream release entries can never disagree — the version now lives
  in more than one file, so nothing but a test keeps them honest.

### Changed
- **Packaging converted to a standard Debian source package.** `debian/` is now
  the single source of packaging truth and `build-deb.sh` is a thin wrapper
  around `dpkg-buildpackage`, so a local `.deb` and a PPA build are produced
  from identical rules. The previous hand-rolled builder maintained its own
  control file and file list — a second description of the package that could
  drift from the first.
- CI now validates the AppStream metadata, builds **both** the binary and the
  source package, and lints them with `--fail-on warning`. A green binary build
  alone would not have told us a PPA upload would succeed.

## [0.4.0] - 2026-07-19

Closes the last unguarded package-removal path, and moves the guard itself to
where it belongs.

### Security
- **The Uninstaller removed packages with no preview and no confirmation.** It
  went straight from click to `pkexec apt-get remove -y` — the same defect fixed
  in the Cleaner in 0.3.0, in the other view. Selecting a package does not mean
  removing only that package: apt also removes everything depending on it. On a
  live Mint 22.3 desktop, selecting `cinnamon` alone removes 4 packages
  including `mint-meta-cinnamon`.

  The Uninstaller now computes apt's real cascade, refuses selections that would
  take session-critical packages (desktop, login manager, graphics driver,
  systemd, NetworkManager), and otherwise shows the full list — including how
  many extra packages come along through dependencies — for explicit
  confirmation. Purge and remove are previewed with the matching verb.

### Changed
- **The preview/guard machinery moved from `cleaner.py` into `pkg.py`**, the
  project's single package seam (principle P5). `removal_preview()`,
  `critical_in()` and `preview_failed()` now have one implementation shared by
  the Cleaner and the Uninstaller, so the two cannot drift apart in how they
  judge a removal. It no longer shells out through `bash -c` either — the
  simulation runs as a plain argv list, so quoting is not a consideration.

### Added
- `tests/test_removal_preview.py` — 12 tests for the shared guard, independent
  of either view: cascade reporting, remove-vs-purge verbs, `--` termination,
  refusal of session-critical sets, and failing *closed* if apt's output format
  ever changes.

## [0.3.0] - 2026-07-19

An urgent safety release. **Anyone running 0.2.0 or earlier should update before
using the Cleaner's orphaned-packages task.**

### Security
- **The Cleaner's "Orphaned packages" task could destroy your desktop.** It ran
  `deborphan | xargs -r apt-get -y purge` unattended: no preview, no
  confirmation, `-y` auto-approving everything. `deborphan` lists libraries with
  no reverse dependencies, which sounds safe — but purging them *cascades*, and
  apt removes every package depending on them too.

  On a live Mint 22.3 desktop this turned 27 "orphans" into **179 removed
  packages**, including `cinnamon`, `cinnamon-session`, `cinnamon-settings-daemon`,
  `mint-meta-cinnamon`, `mint-meta-core`, `mintupdate`, `nvidia-driver-595-open`
  and `gir1.2-gtk-4.0` — the desktop environment and the graphics stack — from a
  single checkbox and one password prompt. The running session survived only
  because it was already in memory; a reboot would have come up with no desktop.

  The task now computes apt's **real** removal set with `apt-get -s purge`,
  shows it in full, and requires explicit confirmation. If that set contains
  anything session-critical (desktop, login manager, graphics driver, systemd,
  NetworkManager) it is **refused outright** rather than confirmed. A preview
  that cannot be computed is treated as a failure and blocks the purge — never
  as "nothing to remove", which is the same empty result read the dangerous way.

  Note that an Essential/Priority guard would not have helped: `cinnamon` is
  `Priority: optional, Essential: no`. The protection has to be the real
  cascade, not package metadata.

### Added
- 29 regression tests covering the orphan path specifically: cascade reporting,
  the `Purg`/`Remv` prefix distinction, refusal of session-critical removals,
  and the untrustworthy-preview case.

## [0.2.0] - 2026-07-19

A security and hardening release. No new features; two real defects fixed in the
paths that build elevated commands, and the project gains a test suite and CI.

### Security
- **Importing a Streamline profile could execute arbitrary commands as root.**
  Package names parsed from a profile were passed unvalidated into
  `pkexec apt-get install -y …`, and `apt-get` parses options wherever they
  appear — including in the package-name position. A manifest containing a line
  of `-o` followed by `APT::Update::Pre-Invoke::=<command>` therefore ran that
  command as root behind a polkit prompt that looked like an ordinary package
  install. This mattered precisely because a profile is designed to be portable
  and hand-edited, which makes it untrusted input.

  Package names are now validated against Debian policy (`ltt.pkg.validate_names`)
  at the single apt seam every operation passes through, and every mutating argv
  adds a `--` terminator so nothing downstream can be re-read as an option. The
  Streamline view partitions an imported profile up front, dropping invalid
  entries before they can reach an elevated call and reporting what it ignored.

### Fixed
- **Cleaner could delete against a wrong path when `$HOME` contained a space.**
  The fixed shell commands interpolated the home directory unquoted, so a home
  such as `/home/jane doe` word-split `rm -rf $HOME/.cache/thumbnails/*` into an
  `rm -rf` against `/home/jane`. All interpolated paths now go through
  `shlex.quote`; `_du()` no longer relies on Python's `repr`, which is not shell
  quoting and does not survive a path containing a single quote.

### Added
- **Test suite** (`tests/`, 89 tests) covering the backend seams — package-name
  validation and argv construction, profile export/import round trips, cleaner
  quoting and size measurement, systemctl state parsing, and metrics
  degradation. Deliberately GTK-free, so it runs headless with no PyGObject
  stack. Both defects above have explicit regression tests.
- **Continuous integration** (`.github/workflows/ci.yml`): lint (`ruff`), test
  (`pytest`), and a `.deb` build checked with `lintian` on every push and pull
  request.
- `pyproject.toml` carrying the ruff and pytest configuration.

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
