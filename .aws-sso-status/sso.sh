#!/bin/bash
# AWS SSO login / logout for SwiftBar.
#
# Usage:
#   sso.sh login [sso-session-name] [profile]
#   sso.sh logout [profile]

set -uo pipefail

# shellcheck source=common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

ACTION="${1:-}"

case "$ACTION" in
  login)
    logmsg() { printf '%s login: %s\n' "$(ts)" "$*" >>"$LOG_FILE"; }

    alert() {
      local msg="$1"
      logmsg "ALERT: $msg"
      osascript -e "display alert \"AWS SSO\" message \"${msg//\"/\\\"}\" as warning" 2>/dev/null || true
    }

    SSO_SESSION="${2:-}"
    PROFILE="${3:-}"
    [[ -z "$PROFILE" ]] && PROFILE="$(read_profile)"

    AWS_BIN="$(resolve_aws)"
    if [[ -z "$AWS_BIN" ]]; then
      alert "aws CLI not found. Install AWS CLI v2 or set AWS=/path/to/aws"
      exit 0
    fi

    logmsg "Checking STS for profile: $PROFILE"
    if "$AWS_BIN" sts get-caller-identity --profile "$PROFILE" >/dev/null 2>&1; then
      notify "AWS SSO" "Already authenticated"
      exit 0
    fi

    notify "AWS SSO" "Opening browser to sign in for $PROFILE…"
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
      notify "AWS SSO" "Signed in"
    else
      ec=$?
      { echo "$(ts) sso login failed (exit $ec)"; cat "$TMP"; echo; } >>"$LOG_FILE"
      rm -f "$TMP"
      alert "aws sso login failed (exit $ec). See: ${LOG_FILE}"
    fi
    ;;

  logout)
    logmsg() { printf '%s logout: %s\n' "$(ts)" "$*" >>"$LOG_FILE"; }

    PROFILE="${2:-}"
    [[ -z "$PROFILE" ]] && PROFILE="$(read_profile)"

    AWS_BIN="$(resolve_aws)"
    if [[ -z "$AWS_BIN" ]]; then
      notify "AWS SSO" "aws CLI not found"
      exit 0
    fi

    logmsg "Running: $AWS_BIN sso logout"
    "$AWS_BIN" sso logout >/dev/null 2>&1 || true
    printf 'expired' >"${HOME}/.aws/swiftbar-sso-state" 2>/dev/null || true
    notify "AWS SSO" "Logged out"
    ;;

  *)
    echo "Usage: sso.sh login [sso-session] [profile]" >&2
    echo "       sso.sh logout [profile]" >&2
    exit 1
    ;;
esac
exit 0
