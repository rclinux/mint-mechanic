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
#   ./build-source.sh --sign       # signed; refuses unless clean, tagged and pushed
#   ./build-source.sh --sign --force   # upload anyway (deliberate divergence)
#   ./build-source.sh --sign --series jammy
#
# Output: ../mint-mechanic_<version>_source.changes  (plus .dsc and .tar.xz)
# Upload: dput ppa:rclinux/mint-mechanic ../mint-mechanic_<version>_source.changes
#
set -euo pipefail

SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SRC"

SIGN=0
FORCE=0
SERIES=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sign)   SIGN=1 ;;
    --force)  FORCE=1 ;;
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

# --- keep the PPA and GitHub honest ---------------------------------------- #
#
# The source package is built from the WORKING TREE, not from git. Nothing about
# `dput` consults GitHub. So the only thing keeping the published package and the
# public repository in step is that this is run from a clean tree at a pushed
# tag -- and that is exactly the kind of discipline that quietly fails.
#
# It already did: 0.5.0 shipped to the PPA with a build-source.sh that differed
# from tag v0.5.0, because a fix landed after the tag but before the upload. The
# runtime code matched, so nobody got the wrong app -- but "nobody noticed" is
# not a guarantee. These checks make it structural. --force overrides for a
# deliberate exception.
if [[ $SIGN -eq 1 && $FORCE -eq 0 ]]; then
  fail=0
  if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
    echo "REFUSING: working tree has uncommitted changes." >&2
    git status --short >&2
    fail=1
  fi
  head_sha="$(git rev-parse HEAD 2>/dev/null || true)"
  tag_sha="$(git rev-parse "v${VERSION}^{commit}" 2>/dev/null || true)"
  if [[ -z "$tag_sha" ]]; then
    echo "REFUSING: no tag v${VERSION} — tag the release before uploading." >&2
    fail=1
  elif [[ "$tag_sha" != "$head_sha" ]]; then
    echo "REFUSING: HEAD is not tag v${VERSION} (HEAD=${head_sha:0:7}, tag=${tag_sha:0:7})." >&2
    fail=1
  fi
  if ! git merge-base --is-ancestor HEAD "@{upstream}" 2>/dev/null; then
    echo "REFUSING: HEAD is not pushed — GitHub would not have what you upload." >&2
    fail=1
  fi
  if [[ $fail -ne 0 ]]; then
    echo "" >&2
    echo "The PPA would publish code that github.com/rclinux/mint-mechanic does not have." >&2
    echo "Fix the above, or pass --force if this divergence is deliberate." >&2
    exit 1
  fi
  echo "==> Tree is clean, at tag v${VERSION}, and pushed — PPA will match GitHub."
fi

# Keep build artefacts and VCS state out of the uploaded tarball.
EXCLUDES=(-I.git -I.github/workflows/__pycache__ -Idist -I.pytest_cache
          -I.ruff_cache -I__pycache__ -I'*.pyc' -I'*.deb')

if [[ $SIGN -eq 1 ]]; then
  # Select the signing key explicitly.
  #
  # By default dpkg-buildpackage asks gpg for a key whose user ID equals the
  # changelog's whole Maintainer string ("Ron Craig (rclinux) <a@b>"). That only
  # works if the GPG uid happens to carry the same display name, which is rarely
  # true -- a key created as "rcraig <a@b>" fails with "No secret key" even
  # though the right key is sitting in the keyring. Match on the email instead,
  # which is the part that actually identifies the uploader.
  MAINT_EMAIL="$(dpkg-parsechangelog -S Maintainer | sed -n 's/.*<\(.*\)>.*/\1/p')"
  KEY="${MINT_MECHANIC_SIGNING_KEY:-}"
  if [[ -z "$KEY" ]]; then
    KEY="$(gpg --list-secret-keys --with-colons "$MAINT_EMAIL" 2>/dev/null \
           | awk -F: '/^fpr:/ {print $10; exit}')"
  fi
  if [[ -z "$KEY" ]]; then
    echo "No secret key found for <$MAINT_EMAIL>." >&2
    echo "Set MINT_MECHANIC_SIGNING_KEY=<fingerprint> or import the key." >&2
    exit 1
  fi
  echo "==> Signing with $KEY"
  dpkg-buildpackage -S "-k$KEY" "${EXCLUDES[@]}"
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
