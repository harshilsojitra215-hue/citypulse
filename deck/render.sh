#!/bin/bash
# Render deck/deck.html to PDF with headless Chrome (same as hackathon/deck_build_v10/render10.sh).
# Usage: deck/render.sh <out.pdf>   Chrome's profile and temp files go to D: because C: is often full.
cd "$(dirname "$0")"
OUT="$(pwd -W)/${1:-CityPulse_deck.pdf}"   # absolute: Chrome may not resolve a relative path from here
TMPD="D:/video-work/tmp/deck-chrome"; mkdir -p "$TMPD"
TMP="$TMPD" TEMP="$TMPD" "/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu \
  --user-data-dir="$TMPD/profile" --no-pdf-header-footer --run-all-compositor-stages-before-draw \
  --virtual-time-budget=15000 --print-to-pdf="$OUT" "file:///$(pwd -W)/deck.html" 2>/dev/null
ls -la "$OUT"
