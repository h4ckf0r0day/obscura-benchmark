#!/usr/bin/env bash
set -euo pipefail

# Clone the web-platform-tests checkout and drop the Obscura report overlay on top.
# The full WPT tree is large (several GB once the manifest is built). It is meant
# to live on the high-performance VPS, not a laptop.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

WPT_REPO="${WPT_REPO:-https://github.com/web-platform-tests/wpt.git}"
WPT_REF="${WPT_REF:-master}"
WPT_DIR="${WPT_DIR:-$SCRIPT_DIR/wpt}"

OVERLAY="$SCRIPT_DIR/wpt-overlay/resources/testharnessreport.js"
TARGET="$WPT_DIR/resources/testharnessreport.js"

echo "[setup-wpt] base dir: $SCRIPT_DIR"
echo "[setup-wpt] wpt dir:  $WPT_DIR"

if [ ! -d "$WPT_DIR" ]; then
  echo "[setup-wpt] cloning $WPT_REPO (ref $WPT_REF, shallow)"
  git clone -b "$WPT_REF" --depth 1 "$WPT_REPO" "$WPT_DIR"
else
  echo "[setup-wpt] wpt checkout already present, skipping clone"
fi

if [ ! -f "$OVERLAY" ]; then
  echo "[setup-wpt] error: overlay not found at $OVERLAY" >&2
  exit 1
fi

# Back up the upstream report script once, then install our overlay.
if [ -f "$TARGET" ] && [ ! -f "$TARGET.orig" ]; then
  echo "[setup-wpt] backing up original report script to $TARGET.orig"
  cp "$TARGET" "$TARGET.orig"
fi

echo "[setup-wpt] installing overlay -> $TARGET"
cp "$OVERLAY" "$TARGET"

# Hosts file. The WPT server serves on web-platform.test and a set of subdomains.
# We do not edit /etc/hosts ourselves because that needs sudo. Tell the user what
# to run, unless it already resolves.
if grep -q "web-platform.test" /etc/hosts 2>/dev/null; then
  echo "[setup-wpt] web-platform.test already present in /etc/hosts, skipping hosts step"
else
  echo "[setup-wpt] web-platform.test is not in /etc/hosts yet."
  echo "[setup-wpt] run this once, from inside $WPT_DIR, to add the WPT hostnames:"
  echo ""
  echo "    ./wpt make-hosts-file | sudo tee -a /etc/hosts"
  echo ""
fi

echo "[setup-wpt] building the WPT manifest (this can take a while)"
( cd "$WPT_DIR" && ./wpt manifest )

echo ""
echo "[setup-wpt] done."
echo "[setup-wpt] next steps:"
echo "  1) if you have not added the hosts entries yet, run the make-hosts-file line above."
echo "  2) run a test pass with: $SCRIPT_DIR/scripts/run-wpt.sh"
