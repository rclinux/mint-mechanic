#!/usr/bin/env bash
#
# build-source.sh — build (and optionally sign) a source package for the PPA.
#
# Launchpad builds the binaries itself; you upload SOURCE only. That is the
# point of a PPA over hand-published .debs: your signing key never leaves this
# machine, and Launchpad's builders produce and sign the repository.
#
# Usage:
#   ./build-source.sh              # unsigned, for inspection
#   ./build-source.sh --sign       # signed with the key in debian/changelog
#   ./build-source.sh --sign --series jammy
#
# Output: ../mint-mechanic_<version>_source.changes  (plus .dsc and .tar.xz)
# Upload: dput ppa:rclinux/mint-mechanic ../mint-mechanic_<version>_source.changes
#
set -euo pipefail

SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SRC"

SIGN=0
SERIES=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sign)   SIGN=1 ;;
    --series) SERIES="${2:?--series needs a value}"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
  shift
done

command -v dpkg-buildpackage >/dev/null || {
  echo "Install the packaging tools first:" >&2
  echo "  sudo apt install dpkg-dev debhelper devscripts dput" >&2
  exit 1
}

# Retarget the changelog at another Ubuntu series if asked. A given version can
# only be uploaded to a PPA once, so per-series builds also need distinct
# versions (e.g. 0.4.0~jammy1) -- handled by the caller via dch.
if [[ -n "$SERIES" ]]; then
  command -v dch >/dev/null || { echo "dch not found (install devscripts)." >&2; exit 1; }
  dch --force-distribution --distribution "$SERIES" ""
fi

VERSION="$(dpkg-parsechangelog -S Version)"
TARGET="$(dpkg-parsechangelog -S Distribution)"
echo "==> Building source package mint-mechanic ${VERSION} for ${TARGET}"

# Keep build artefacts and VCS state out of the uploaded tarball.
EXCLUDES=(-I.git -I.github/workflows/__pycache__ -Idist -I.pytest_cache
          -I.ruff_cache -I__pycache__ -I'*.pyc' -I'*.deb')

if [[ $SIGN -eq 1 ]]; then
  dpkg-buildpackage -S "${EXCLUDES[@]}"
else
  dpkg-buildpackage -S -us -uc "${EXCLUDES[@]}"
fi

CHANGES="../mint-mechanic_${VERSION}_source.changes"
echo "==> Built $CHANGES"

if command -v lintian >/dev/null; then
  echo "==> lintian (source)"
  lintian --tag-display-limit 0 "$CHANGES" || true
fi

cat <<EOF

Next:
  dput ppa:rclinux/mint-mechanic $CHANGES

Launchpad will build the binaries and publish them. Watch progress at:
  https://launchpad.net/~rclinux/+archive/ubuntu/mint-mechanic/+packages
EOF
