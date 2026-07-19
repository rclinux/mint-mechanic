#!/usr/bin/env bash
#
# build-deb.sh — build a binary .deb for Mint Mechanic.
#
# This is a thin wrapper around dpkg-buildpackage. All packaging metadata lives
# in debian/ and nowhere else, so the locally-built .deb and the PPA build are
# produced from exactly the same rules. (This script used to hand-roll its own
# control file and file list, which meant two descriptions of the package that
# could silently drift apart.)
#
# Output:  dist/mint-mechanic_<version>_all.deb
# Install: sudo apt install ./dist/mint-mechanic_<version>_all.deb
#
# For a source package to upload to the PPA, use build-source.sh instead.
#
set -euo pipefail

SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SRC"

command -v dpkg-buildpackage >/dev/null || {
  echo "dpkg-buildpackage not found. Install it with:" >&2
  echo "  sudo apt install dpkg-dev debhelper" >&2
  exit 1
}

VERSION="$(dpkg-parsechangelog -S Version)"
echo "==> Building mint-mechanic ${VERSION} (binary)"

# -b binary only, -us -uc unsigned (a local build needs no signature).
dpkg-buildpackage -b -us -uc

mkdir -p dist
mv -f ../mint-mechanic_"${VERSION}"_all.deb dist/
rm -f ../mint-mechanic_"${VERSION}"_*.buildinfo ../mint-mechanic_"${VERSION}"_*.changes

DEB="dist/mint-mechanic_${VERSION}_all.deb"
echo "==> Built $DEB"

if command -v lintian >/dev/null; then
  echo "==> lintian"
  lintian --tag-display-limit 0 "$DEB" || true
fi

echo
echo "Install:  sudo apt install ./$DEB"
