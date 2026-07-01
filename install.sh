#!/usr/bin/env bash
#
# install.sh — installer for Mint Mechanic (the "make install" path).
#
# Mint Mechanic is functionally Mint/Ubuntu (apt) software, so this installer
# targets the debian family. It installs the runtime dependencies with apt and
# copies the application into the system layout the launcher and config already
# expect (/usr/share/mint-mechanic, /usr/bin/ltt, the desktop entry and icons).
#
# For a packaged install instead, build the .deb:   ./build-deb.sh   then
#   sudo apt install ./dist/mint-mechanic_<version>_all.deb
#
# Usage:   sudo ./install.sh
#
set -euo pipefail

# --------------------------------------------------------------------------- #
# Output helpers.
# --------------------------------------------------------------------------- #
if [[ -t 1 ]]; then
  C_RESET=$'\e[0m'; C_BOLD=$'\e[1m'; C_BLUE=$'\e[34m'; C_RED=$'\e[31m'; C_GREEN=$'\e[32m'
else
  C_RESET=""; C_BOLD=""; C_BLUE=""; C_RED=""; C_GREEN=""
fi
msg()  { printf '%s==>%s %s\n' "$C_BLUE$C_BOLD"  "$C_RESET" "$*"; }
ok()   { printf '%s==>%s %s\n' "$C_GREEN$C_BOLD" "$C_RESET" "$*"; }
die()  { printf '%s[x]%s %s\n' "$C_RED$C_BOLD"   "$C_RESET" "$*" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# 0. Must be root (writes under /usr and installs packages).
# --------------------------------------------------------------------------- #
[[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo $0"

# Locate the source tree (this script lives at the repo root).
SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ -d "$SRC/ltt" && -f "$SRC/bin/ltt" ]] \
  || die "Run this from the project root (ltt/ and bin/ltt not found)."

# --------------------------------------------------------------------------- #
# 1. Confirm the debian family. Mint, Ubuntu and Debian all qualify.
# --------------------------------------------------------------------------- #
[[ -r /etc/os-release ]] || die "/etc/os-release not found — cannot detect distro."
# shellcheck source=/dev/null
. /etc/os-release
haystack=" ${ID:-} ${ID_LIKE:-} "
case "$haystack" in
  *" debian "*|*" ubuntu "*|*" linuxmint "*) : ;;
  *) die "Mint Mechanic targets the debian/apt family (Mint, Ubuntu, Debian). Detected ID='${ID:-?}' ID_LIKE='${ID_LIKE:-?}'." ;;
esac
msg "Detected: ${PRETTY_NAME:-$ID}"

# --------------------------------------------------------------------------- #
# 2. Runtime dependencies.
#    Required: Python 3, PyGObject, GTK 4, psutil, and polkit (pkexec) for the
#    per-action elevation. Recommended: deborphan (the Cleaner's orphaned-
#    package task; it hides itself when deborphan is absent). nvidia-smi is NOT
#    installed here — it ships with the NVIDIA driver and the GPU dial simply
#    hides without it.
# --------------------------------------------------------------------------- #
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq || true
REQUIRED=(python3 python3-gi gir1.2-gtk-4.0 libgtk-4-1 python3-psutil pkexec)
RECOMMENDED=(deborphan)

msg "Installing required dependencies (${#REQUIRED[@]})..."
apt-get install -y "${REQUIRED[@]}"
msg "Installing recommended dependencies (${#RECOMMENDED[@]})..."
apt-get install -y "${RECOMMENDED[@]}" || msg "Recommended packages skipped (non-fatal)."

# --------------------------------------------------------------------------- #
# 3. Install the application files.
# --------------------------------------------------------------------------- #
SHARE=/usr/share/mint-mechanic

msg "Installing application files..."
# The Python package (skip caches).
install -dm755 "$SHARE/ltt"
for f in "$SRC"/ltt/*.py; do
  install -m644 "$f" "$SHARE/ltt/"
done

# Launcher and desktop entry.
install -Dm755 "$SRC/bin/ltt" /usr/bin/ltt
install -Dm644 "$SRC/data/mint-mechanic.desktop" /usr/share/applications/mint-mechanic.desktop

# Man page.
if [[ -f "$SRC/data/ltt.1" ]]; then
  tmpgz="$(mktemp)"; gzip -9nc "$SRC/data/ltt.1" > "$tmpgz"
  install -Dm644 "$tmpgz" /usr/share/man/man1/ltt.1.gz; rm -f "$tmpgz"
fi

# Icons (scalable SVG + raster sizes), mirroring the source hicolor tree.
for size in scalable 48x48 128x128 256x256; do
  case "$size" in
    scalable) ext=svg ;;
    *)        ext=png ;;
  esac
  src_icon="$SRC/data/icons/hicolor/$size/apps/mint-mechanic.$ext"
  [[ -f "$src_icon" ]] && install -Dm644 "$src_icon" \
    "/usr/share/icons/hicolor/$size/apps/mint-mechanic.$ext"
done

# --------------------------------------------------------------------------- #
# 4. Refresh icon + desktop caches (best-effort).
# --------------------------------------------------------------------------- #
gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
update-desktop-database -q 2>/dev/null || true

ok "Mint Mechanic installed."
echo
echo "  Launch:  ltt   (or 'Mint Mechanic' from your application menu)"
echo "  Do NOT run it as root — mutating actions elevate per-action via pkexec."
echo "  Uninstall:  sudo $SRC/uninstall.sh"
