#!/usr/bin/env bash
#
# build-deb.sh — build a binary .deb for Mint Mechanic.
#
# Self-contained: it stages the same /usr layout install.sh produces into a
# temporary root, writes the DEBIAN control/maintainer scripts, and calls
# dpkg-deb --build. No debhelper or dpkg-dev source-package tooling required.
#
# Output:  dist/mint-mechanic_<version>_all.deb
# Install: sudo apt install ./dist/mint-mechanic_<version>_all.deb
#
set -euo pipefail

SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SRC"

command -v dpkg-deb >/dev/null || { echo "dpkg-deb not found (install dpkg)." >&2; exit 1; }

# Version comes from the single source of truth in config.py.
VERSION="$(sed -n 's/^APP_VERSION *= *"\([^"]*\)".*/\1/p' ltt/config.py)"
[[ -n "$VERSION" ]] || { echo "Could not read APP_VERSION from ltt/config.py." >&2; exit 1; }
ARCH=all
PKG="mint-mechanic"
DEB="dist/${PKG}_${VERSION}_${ARCH}.deb"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
echo "==> Staging ${PKG} ${VERSION} into $STAGE"

# --- Application files (mirror install.sh) --------------------------------- #
install -dm755 "$STAGE/usr/share/mint-mechanic/ltt"
for f in ltt/*.py; do install -m644 "$f" "$STAGE/usr/share/mint-mechanic/ltt/"; done

install -Dm755 bin/mint-mechanic            "$STAGE/usr/bin/mint-mechanic"
install -Dm644 data/mint-mechanic.desktop   "$STAGE/usr/share/applications/mint-mechanic.desktop"

for size in scalable 48x48 128x128 256x256; do
  case "$size" in scalable) ext=svg ;; *) ext=png ;; esac
  icon="data/icons/hicolor/$size/apps/mint-mechanic.$ext"
  [[ -f "$icon" ]] && install -Dm644 "$icon" \
    "$STAGE/usr/share/icons/hicolor/$size/apps/mint-mechanic.$ext"
done

# Man page (gzip -n for a reproducible, timestamp-free archive).
gzip -9nc data/mint-mechanic.1 > "$STAGE/tmp.gz"
install -Dm644 "$STAGE/tmp.gz" "$STAGE/usr/share/man/man1/mint-mechanic.1.gz"
rm -f "$STAGE/tmp.gz"

# --- Documentation --------------------------------------------------------- #
docdir="$STAGE/usr/share/doc/mint-mechanic"
install -Dm644 README.md "$docdir/README.md"

# copyright: point at the system GPL text rather than shipping a full copy.
cat > "$STAGE/copyright.tmp" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: Mint Mechanic
Source: https://github.com/rclinux/mint-mechanic

Files: *
Copyright: 2026 Ron Craig (rclinux)
License: GPL-3.0-or-later
 This program is free software: you can redistribute it and/or modify it under
 the terms of the GNU General Public License as published by the Free Software
 Foundation, either version 3 of the License, or (at your option) any later
 version.
 .
 This program is distributed in the hope that it will be useful, but WITHOUT ANY
 WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
 PARTICULAR PURPOSE. See the GNU General Public License for more details.
 .
 On Debian systems, the complete text of the GNU General Public License version
 3 can be found in /usr/share/common-licenses/GPL-3.
EOF
install -Dm644 "$STAGE/copyright.tmp" "$docdir/copyright"
rm -f "$STAGE/copyright.tmp"

# changelog: a native package's changelog.gz must be in Debian format.
DATE_RFC="$(date -R)"
cat > "$STAGE/changelog.tmp" <<EOF
mint-mechanic ($VERSION) unstable; urgency=medium

  * Initial release: Dashboard, Services, Startup, Cleaner, Uninstaller and
    Streamline views; GO/NO-GO health strip; sibling-tool launch.

 -- Ron Craig (rclinux) <noreply@github.com>  $DATE_RFC
EOF
gzip -9nc "$STAGE/changelog.tmp" > "$STAGE/tmp.gz"
install -Dm644 "$STAGE/tmp.gz" "$docdir/changelog.gz"
rm -f "$STAGE/tmp.gz" "$STAGE/changelog.tmp"

# --- Control metadata ------------------------------------------------------ #
INSTALLED_KB="$(du -sk "$STAGE/usr" | cut -f1)"
install -dm755 "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Architecture: $ARCH
Maintainer: Ron Craig (rclinux) <noreply@github.com>
Installed-Size: $INSTALLED_KB
Section: admin
Priority: optional
Depends: python3, python3-gi, gir1.2-gtk-4.0, libgtk-4-1, python3-psutil, pkexec
Recommends: deborphan
Homepage: https://github.com/rclinux/mint-mechanic
Description: Maintained tune-up tool for Linux Mint
 A modern, Cinnamon-native successor to Stacer: a live system dashboard with
 animated CPU / RAM / Disk gauges plus a GPU dial, married to the action
 features Mint does not ship (services, cleaner, startup manager, uninstaller)
 and a package-profile export tied to disaster recovery.
 .
 Mutating actions elevate per-action via polkit (pkexec); the app itself runs
 as the user and is never run as root.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
  update-desktop-database -q 2>/dev/null || true
fi
EOF

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
  gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
  update-desktop-database -q 2>/dev/null || true
fi
EOF
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

# --- Build ----------------------------------------------------------------- #
mkdir -p dist
echo "==> Building $DEB"
dpkg-deb --root-owner-group --build "$STAGE" "$DEB" >/dev/null
echo "==> Done."
dpkg-deb --info "$DEB" | sed -n '1,20p'
echo
echo "Install:  sudo apt install ./$DEB"
