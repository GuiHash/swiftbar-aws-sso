#!/bin/bash
# Uninstall the SwiftBar AWS SSO Status plugin.
#
# Removes the entry script (and copied helpers, if any) from the SwiftBar
# plugins folder. Optionally cleans state files and logs in ~/.aws/.
#
# Usage:
#   ./uninstall.sh                       # interactive
#   ./uninstall.sh --plugins-dir <path>  # override SwiftBar plugins dir
#   ./uninstall.sh --purge               # also delete state/logs/profile prefs
#   ./uninstall.sh --yes                 # non-interactive, keep state files

set -euo pipefail

ENTRY_NAME="aws-sso-status.py"
HELPERS_DIRNAME=".aws-sso-status"

PLUGIN_DIR=""
PURGE=0
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plugins-dir) PLUGIN_DIR="${2:-}"; shift 2 ;;
    --purge) PURGE=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help)
      sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

err()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; }
info() { printf '\033[36m›\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }

if [[ -z "$PLUGIN_DIR" ]]; then
  if [[ -n "${SWIFTBAR_PLUGINS_DIR:-}" ]]; then
    PLUGIN_DIR="$SWIFTBAR_PLUGINS_DIR"
  elif PLUGIN_DIR_DETECTED="$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null)"; then
    PLUGIN_DIR="$PLUGIN_DIR_DETECTED"
  else
    PLUGIN_DIR="${HOME}/.swiftbar-plugins"
  fi
fi
PLUGIN_DIR="${PLUGIN_DIR/#\~/$HOME}"
info "Plugins dir: $PLUGIN_DIR"

ENTRY_DST="$PLUGIN_DIR/$ENTRY_NAME"
HELPERS_DST="$PLUGIN_DIR/$HELPERS_DIRNAME"

remove_path() {
  local target="$1"
  if [[ -L "$target" ]]; then
    rm -- "$target"
    ok "Removed symlink: $target"
  elif [[ -d "$target" ]]; then
    rm -rf -- "$target"
    ok "Removed directory: $target"
  elif [[ -e "$target" ]]; then
    rm -- "$target"
    ok "Removed file: $target"
  else
    info "Nothing at: $target"
  fi
}

remove_path "$ENTRY_DST"
remove_path "$HELPERS_DST"

# Cache and log directories
STATE_PATHS=(
  "${HOME}/Library/Caches/swiftbar-aws-sso-status"
  "${HOME}/Library/Logs/swiftbar-aws-sso-status"
)

if [[ "$PURGE" -eq 0 && "$ASSUME_YES" -eq 0 && -t 0 ]]; then
  printf 'Also remove plugin cache and logs (~/Library/Caches and ~/Library/Logs) ? [y/N] '
  read -r answer || true
  case "$(printf '%s' "${answer:-}" | tr '[:upper:]' '[:lower:]')" in
    y|yes) PURGE=1 ;;
  esac
fi

if [[ "$PURGE" -eq 1 ]]; then
  for f in "${STATE_PATHS[@]}"; do
    [[ -e "$f" ]] && rm -rf -- "$f" && ok "Removed: $f" || true
  done
  if [[ -e "${HOME}/.aws/config.swiftbar.bak" ]]; then
    warn "Backup of ~/.aws/config kept at ~/.aws/config.swiftbar.bak (delete manually if no longer needed)."
  fi
else
  info "Cache and logs left in place. Re-run with --purge to delete them."
fi

echo
ok "Uninstall complete."
echo "Tip: SwiftBar → Refresh All to drop the menu bar item."
