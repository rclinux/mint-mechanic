# Changelog

All notable changes to **Mint Mechanic** are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims
to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
