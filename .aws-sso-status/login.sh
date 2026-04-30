#!/bin/bash
# Smart AWS SSO login for SwiftBar.
# 1. Checks credentials via STS — if already OK, notifies and exits.
# 2. Otherwise opens the browser via aws sso login.
#
# Usage: login.sh [sso-session-name] [profile]
#   $1 — sso-session name (empty = skip, use --profile instead)
#   $2 — AWS profile name (used for STS check and fallback login)

set -uo pipefail

LOG_FILE="${HOME}/.aws/swiftbar-sso-login.log"
ts()     { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
logmsg() { printf '%s login: %s\n' "$(ts)" "$*" >>"$LOG_FILE"; }

notify() {
  local title="$1" msg="$2"
  logmsg "$title — $msg"
  if ! osascript -e "display notification \"${msg//\"/\\\"}\" with title \"${title//\"/\\\"}\"" 2>>"$LOG_FILE"; then
    osascript -e "display alert \"${title//\"/\\\"}\" message \"${msg//\"/\\\"}\"" 2>>"$LOG_FILE" || true
  fi
}

alert() {
  local msg="$1"
  logmsg "ALERT: $msg"
  osascript -e "display alert \"AWS SSO\" message \"${msg//\"/\\\"}\" as warning" 2>/dev/null || true
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

SSO_SESSION="${1:-}"
PROFILE="${2:-}"

if [[ -z "$PROFILE" && -f "${HOME}/.aws/swiftbar-profile" ]]; then
  IFS= read -r PROFILE <"${HOME}/.aws/swiftbar-profile" || true
  PROFILE="${PROFILE//[$'\r\n']/}"
  PROFILE="${PROFILE#"${PROFILE%%[![:space:]]*}"}"
  PROFILE="${PROFILE%"${PROFILE##*[![:space:]]}"}"
fi

AWS_BIN="$(resolve_aws)"
if [[ -z "$AWS_BIN" ]]; then
  alert "aws CLI not found. Install AWS CLI v2 or set AWS=/path/to/aws"
  exit 0
fi

# Step 1 — already authenticated?
logmsg "Checking STS for profile: $PROFILE"
if "$AWS_BIN" sts get-caller-identity --profile "$PROFILE" >/dev/null 2>&1; then
  notify "AWS SSO" "Already authenticated — credentials OK for $PROFILE"
  exit 0
fi

# Step 2 — login via sso-session (preferred) or profile fallback
TMP=$(mktemp)
LOGIN_OK=false

if [[ -n "$SSO_SESSION" ]]; then
  logmsg "Running: $AWS_BIN sso login --sso-session $SSO_SESSION"
  if "$AWS_BIN" sso login --sso-session "$SSO_SESSION" >"$TMP" 2>&1; then
    LOGIN_OK=true
  fi
else
  logmsg "Running: $AWS_BIN sso login --profile $PROFILE"
  if "$AWS_BIN" sso login --profile "$PROFILE" >"$TMP" 2>&1; then
    LOGIN_OK=true
  fi
fi

if [[ "$LOGIN_OK" == true ]]; then
  rm -f "$TMP"
else
  ec=$?
  { echo "$(ts) sso login failed (exit $ec)"; cat "$TMP"; echo; } >>"$LOG_FILE"
  rm -f "$TMP"
  alert "aws sso login failed (exit $ec). See: ${LOG_FILE}"
fi
exit 0
