# Shared helpers — sourced by login.sh and logout.sh, not executed directly.

LOG_FILE="${HOME}/.aws/swiftbar-sso-login.log"
ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

_HELPERS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ICON_PNG="${_HELPERS_DIR}/icon.png"

resolve_alerter() {
  [[ -n "${ALERTER:-}" && -x "${ALERTER}" ]] && { echo "$ALERTER"; return; }
  local c; c=$(command -v alerter 2>/dev/null) || true
  [[ -n "$c" ]] && { echo "$c"; return; }
  for p in /opt/homebrew/bin/alerter /usr/local/bin/alerter; do
    [[ -x "$p" ]] && { echo "$p"; return; }
  done
  echo ""
}

ALERTER_BIN="$(resolve_alerter)"

notify() {
  local title="$1" msg="$2"
  logmsg "$title — $msg"
  if [[ -n "$ALERTER_BIN" ]]; then
    local cmd=("$ALERTER_BIN" --title "$title" --message "$msg" --sound Glass --group aws-sso-status --timeout 30)
    [[ -f "$ICON_PNG" ]] && cmd+=(--app-icon "$ICON_PNG")
    "${cmd[@]}" >/dev/null 2>>"$LOG_FILE" &
    disown
    return
  fi
  if ! osascript -e "display notification \"${msg//\"/\\\"}\" with title \"${title//\"/\\\"}\"" 2>>"$LOG_FILE"; then
    osascript -e "display alert \"${title//\"/\\\"}\" message \"${msg//\"/\\\"}\"" 2>>"$LOG_FILE" || true
  fi
}

resolve_aws() {
  if [[ -n "${AWS:-}" && -x "${AWS}" ]]; then echo "$AWS"; return; fi
  local c; c=$(command -v aws 2>/dev/null) || true
  [[ -n "$c" ]] && { echo "$c"; return; }
  for p in /opt/homebrew/bin/aws /usr/local/bin/aws; do
    [[ -x "$p" ]] && { echo "$p"; return; }
  done
  echo ""
}

read_profile() {
  local script="${_HELPERS_DIR}/run.py"
  [[ -f "$script" ]] || { echo ""; return; }
  python3 -B "$script" --get-profile 2>/dev/null || true
}
