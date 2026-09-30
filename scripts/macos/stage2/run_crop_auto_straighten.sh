#!/usr/bin/env bash
# Stage 2 Operation 1B: apply the Crop tool's Auto straighten to N consecutive
# photos in Lightroom Classic (Develop module). Manual invocation only.
#
# Usage:
#   run_crop_auto_straighten.sh calibrate   # one-time: record the Auto button position
#   run_crop_auto_straighten.sh run N       # straighten the current photo + next N-1
#   run_crop_auto_straighten.sh test        # shortcut for run 10
#
# Requires cliclick (brew install cliclick) and Accessibility permission for the
# terminal app. Lightroom must stay frontmost: it ignores clicks that do not come
# from the real cursor, and the SDK cannot invoke Crop > Auto (see
# docs/future-work/crop-auto-vs-upright-level-spike.md).

set -euo pipefail

CONF="${HOME}/.lrc-auto-straighten.conf"
APP="Adobe Lightroom Classic"

# Tunable delays (seconds). Raise these if photos are missing "Auto Straighten"
# in the History panel.
DELAY_TOOL="${DELAY_TOOL:-0.6}"    # after opening the Crop tool
DELAY_AUTO="${DELAY_AUTO:-1.2}"    # after clicking Auto (analysis time)
DELAY_NEXT="${DELAY_NEXT:-0.8}"    # after moving to the next photo

CLICK_HOVER_MS="${CLICK_HOVER_MS:-300}"  # hover time (ms) before pressing Auto

die() { echo "error: $*" >&2; exit 1; }

command -v cliclick >/dev/null || die "cliclick not found. Install with: brew install cliclick"

# key code: R=15 Return=36 Right=124
send_key() { osascript -e "tell application \"System Events\" to key code $1"; }
focus_lr() { osascript -e "tell application \"$APP\" to activate"; sleep 0.4; }

calibrate() {
  cat <<'EOF'
Calibration:
  1. In Lightroom Classic, open the Develop module, select any photo, press R
     to open the Crop tool.
  2. Come back here, press Enter, then within 5 seconds hover the mouse over
     the Crop panel's "Auto" button (next to the Angle slider) and leave it there.
EOF
  read -r -p "Press Enter to start the countdown... " _
  for i in 5 4 3 2 1; do printf '%s ' "$i"; sleep 1; done; echo
  pos="$(cliclick p | sed 's/.*: //')"
  [[ "$pos" =~ ^[0-9]+,[0-9]+$ ]] || die "could not read mouse position (got '$pos')"
  echo "AUTO_POS=$pos" > "$CONF"
  echo "Saved Auto button position $pos to $CONF"
}

# Lightroom ignores a click that arrives with the move, so hover first:
# move near, settle, move onto the button, settle, then press and release.
click_auto() {
  local x="${AUTO_POS%,*}" y="${AUTO_POS#*,}"
  local orig; orig="$(cliclick p | sed 's/.*: //')"
  cliclick m:$((x - 4)),$((y - 4)) w:150 m:"$x","$y" w:"$CLICK_HOVER_MS" dd:"$x","$y" w:80 du:"$x","$y"
  [[ "$orig" =~ ^[0-9]+,[0-9]+$ ]] && cliclick m:"$orig"   # give the cursor back
}

straighten_one() {
  send_key 15;  sleep "$DELAY_TOOL"   # Crop tool
  click_auto;   sleep "$DELAY_AUTO"   # Auto button
  send_key 36                         # Return: commit and leave Crop tool
  sleep 0.3
}

run() {
  local n="$1"
  [[ -f "$CONF" ]] || die "no calibration found. Run: $0 calibrate"
  # shellcheck disable=SC1090
  source "$CONF"
  [[ -n "${AUTO_POS:-}" ]] || die "bad config $CONF; re-run calibrate"

  echo "Starting in 3s on $n photo(s). Make sure Lightroom Classic is in Develop with the first photo selected. Ctrl-C to abort."
  sleep 3
  focus_lr

  for ((i = 1; i <= n; i++)); do
    echo "[$i/$n] auto straighten"
    straighten_one
    if (( i < n )); then
      send_key 124; sleep "$DELAY_NEXT"   # Right arrow: next photo
    fi
  done
  echo "Done. Spot-check a few photos for 'Auto Straighten' in the History panel."
}

case "${1:-}" in
  calibrate) calibrate ;;
  test)      run 10 ;;
  run)       [[ "${2:-}" =~ ^[0-9]+$ ]] && (( $2 > 0 )) || die "usage: $0 run N"; run "$2" ;;
  *)         sed -n '2,13p' "$0"; exit 1 ;;
esac
