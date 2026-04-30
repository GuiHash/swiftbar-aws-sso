#!/bin/bash
# AWS SSO logout for SwiftBar.
# Usage: logout.sh [profile]

set -uo pipefail

LOG_FILE="${HOME}/.aws/swiftbar-sso-login.log"
ts()     { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
logmsg() { printf '%s logout: %s\n' "$(ts)" "$*" >>"$LOG_FILE"; }

notify() {
  local title="$1" msg="$2"
  logmsg "$title — $msg"
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

PROFILE="${1:-}"
if [[ -z "$PROFILE" && -f "${HOME}/.aws/swiftbar-profile" ]]; then
  IFS= read -r PROFILE <"${HOME}/.aws/swiftbar-profile" || true
  PROFILE="${PROFILE//[$'\r\n']/}"
  PROFILE="${PROFILE#"${PROFILE%%[![:space:]]*}"}"
  PROFILE="${PROFILE%"${PROFILE##*[![:space:]]}"}"
fi

AWS_BIN="$(resolve_aws)"
if [[ -z "$AWS_BIN" ]]; then
  notify "AWS SSO" "aws CLI not found"
  exit 0
fi

logmsg "Running: $AWS_BIN sso logout"
"$AWS_BIN" sso logout >/dev/null 2>&1 || true
# Mark state as expired so the next run.py tick does not fire a duplicate "Session expired" notification.
printf 'expired' >"${HOME}/.aws/swiftbar-sso-state" 2>/dev/null || true
notify "AWS SSO" "Logged out"
exit 0
