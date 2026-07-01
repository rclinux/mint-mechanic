# Mint Mechanic

**The maintained tune-up tool for Linux Mint.** A modern, Cinnamon-native
successor to [Stacer](https://github.com/oguzhaninan/Stacer) (GPL-3.0, abandoned
since 2019): a live system dashboard with animated **CPU / RAM / Disk gauges
plus the GPU dial Stacer never had**, married to the *action* features Mint
doesn't ship — and topped with package-profile export tied to disaster recovery.

> Status: **Phase 0 (skeleton).** The app runs as a three-view shell; features
> land phase by phase. Command: `ltt`.

## Why

- **Stacer is abandoned** (last release May 2019, Qt/C++) — a clear succession
  opening, and its beloved analog-gauge dashboard deserves a maintained heir.
- **Mint 22.3 "Zena" owns system *info*** (its read-only System Information
  tool). Mint Mechanic deliberately does **not** compete there — it lives in the
  **action / optimization** lane Mint leaves open.
- Differentiators neither Stacer nor Mint has: **Streamline** package profiles
  (a portable bill-of-materials for from-scratch rebuilds), a GO/NO-GO health
  read, and one-click launch into the sibling
  [disk-recovery-tool](https://github.com/rcraig57/disk-recovery-tool).

## v1 scope (minimum-lovable)

1. **Dashboard** — live analog gauges: CPU, RAM, Disk, **GPU** (NVIDIA now; the
   reader is behind a seam for a future AMD swap).
2. **Services** — enable/disable systemd services with live status (the GUI Mint
   lacks).
3. **Streamline** — export/import your manually-installed package set.

Later phases add Cleaner, Startup manager, Uninstaller, a health strip, and
DRT/Dashboard launch integration.

## Design principles

- **Compete in the gap, not the overlap.** Actions + gauges; ignore system info.
- **One package-manager abstraction** (`ltt/pkg.py`) from day one — every
  install/remove/query routes through it. (v1 is apt/Mint-only; the seam lets a
  dnf/pacman backend drop in later.) This is the lesson learned from the Arch
  Linux Tweak Tool, which hardcodes pacman ~115× across 44 files.
- **Data-driven features** — a toggle/app is a dict consumed by one generic row
  builder; adding a feature is adding a data row.
- **No blanket root.** Reads run as the user; mutating actions elevate
  per-action via pkexec.
- **Independent sibling, not a monolith.** Mint Mechanic does not absorb
  disk-recovery-tool or workstation-dashboard — it launches/links to them.

## Requirements

Python 3, GTK 4 + PyGObject, `psutil`. Optional: `nvidia-smi` for the GPU dial
(absent → the dial simply hides). Linux Mint 22.x / Cinnamon.

## Run (dev tree)

```bash
./bin/ltt
```

## License

GPL-3.0-or-later. © Ron Craig (rclinux).
