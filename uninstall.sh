#!/usr/bin/env bash
#
# uninstall.sh — remove the files install.sh placed on the system.
#
# It does NOT remove the dependency packages (GTK 4, psutil, deborphan, …) —
# those may be wanted by other software, so removing them is left to you.
#
set -euo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "Run as root: sudo $0" >&2; exit 1; }

rm -rf /usr/share/mint-mechanic
rm -f  /usr/bin/mint-mechanic
rm -f  /usr/share/applications/mint-mechanic.desktop
rm -f  /usr/share/man/man1/mint-mechanic.1.gz
for size in scalable 48x48 128x128 256x256; do
  case "$size" in scalable) ext=svg ;; *) ext=png ;; esac
  rm -f "/usr/share/icons/hicolor/$size/apps/mint-mechanic.$ext"
done

gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
update-desktop-database -q 2>/dev/null || true

echo "Mint Mechanic removed. (Dependency packages were left installed.)"
