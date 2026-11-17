#!/usr/bin/env bash
# Re-render the marketplace images from icon.html / cover.html.
#
# Headless Chrome rather than a converter on purpose: the covers contain Chinese
# text, and the only reliable way to get the same glyphs a reviewer sees is to
# let a real browser shape them. Sizes are exact pixels, so nothing gets cropped
# on the way out.
#
#   ./brand/build.sh          # from the repo root or from brand/
#   CHROME=/path/to/chrome ./brand/build.sh
set -euo pipefail
cd "$(dirname "$0")"

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [ ! -x "$CHROME" ]; then
  echo "Chrome not found at: $CHROME" >&2
  echo "Install Chrome, or run: CHROME=/path/to/chrome ./brand/build.sh" >&2
  exit 1
fi

shot() {
  # Chrome logs harmless display-link noise on macOS; filtering it keeps the
  # output honest about what actually happened.
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-sandbox "$@" \
    2>&1 | grep -vE 'CVDisplayLink|allocator|Trying to load|net/cert|normalizing|Failed parsing' || true
}

shot --window-size=512,512 --default-background-color=00000000 \
     --screenshot=agent-memory-icon-512.png "file://$PWD/icon.html"
shot --window-size=512,512 --default-background-color=00000000 \
     --force-device-scale-factor=2 --screenshot=agent-memory-icon-1024.png "file://$PWD/icon.html"
shot --window-size=1280,720 --screenshot=agent-memory-cover-1280.png "file://$PWD/cover.html"
shot --window-size=1280,720 --force-device-scale-factor=2 \
     --screenshot=agent-memory-cover-2560.png "file://$PWD/cover.html"

for f in agent-memory-icon-512.png agent-memory-icon-1024.png \
         agent-memory-cover-1280.png agent-memory-cover-2560.png; do
  [ -s "$f" ] || { echo "missing: $f" >&2; exit 1; }
  printf '%-32s %s\n' "$f" "$(sips -g pixelWidth -g pixelHeight "$f" | tail -2 | awk '{print $2}' | paste -sd'x' -)"
done
