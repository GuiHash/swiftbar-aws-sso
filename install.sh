#!/bin/bash
# Install the SwiftBar AWS SSO Status plugin into your SwiftBar plugins folder.
#
# Two install modes:
#   --symlink   symlinks the entry script (recommended: `git pull` updates the live plugin)
#   --copy      copies a snapshot (independent of this repo)
#
# Usage:
#   ./install.sh                       # interactive (prompts for mode + plugins dir)
#   ./install.sh --symlink             # non-interactive symlink install
#   ./install.sh --copy                # non-interactive copy install
#   ./install.sh --plugins-dir <path>  # override SwiftBar plugins dir
#   ./install.sh --yes                 # accept defaults (symlink + auto-detected dir)

set -euo pipefail

REPO="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRY_NAME="aws-sso-status.1m.sh"
ENTRY_SRC="$REPO/$ENTRY_NAME"
HELPERS_DIRNAME=".aws-sso-status"

MODE=""
PLUGIN_DIR=""
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --symlink) MODE="symlink"; shift ;;
    --copy)    MODE="copy";    shift ;;
    --plugins-dir) PLUGIN_DIR="${2:-}"; shift 2 ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help)
      sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

err()  { printf '\033[31m✗\033[0m %s\n' "$*" >&2; }
info() { printf '\033[36m›\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

if [[ ! -f "$ENTRY_SRC" ]]; then
  err "Cannot find $ENTRY_SRC. Run install.sh from the repo root."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  err "python3 not found in PATH (required by the plugin)."
  exit 1
fi

if ! command -v aws >/dev/null 2>&1; then
  warn "aws CLI not found in PATH. Install AWS CLI v2: brew install awscli"
fi

if [[ ! -d "/Applications/SwiftBar.app" ]]; then
  warn "SwiftBar.app not found in /Applications. Install it: brew install --cask swiftbar"
fi

# ---------------------------------------------------------------------------
# Resolve plugin directory
# ---------------------------------------------------------------------------

if [[ -z "$PLUGIN_DIR" ]]; then
  if [[ -n "${SWIFTBAR_PLUGINS_DIR:-}" ]]; then
    PLUGIN_DIR="$SWIFTBAR_PLUGINS_DIR"
  elif PLUGIN_DIR_DETECTED="$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null)"; then
    PLUGIN_DIR="$PLUGIN_DIR_DETECTED"
  else
    PLUGIN_DIR="${HOME}/.swiftbar-plugins"
  fi
fi

# Expand ~ if user passed it
PLUGIN_DIR="${PLUGIN_DIR/#\~/$HOME}"

if [[ "$ASSUME_YES" -eq 0 && -t 0 ]]; then
  printf 'SwiftBar plugins directory [%s]: ' "$PLUGIN_DIR"
  read -r answer || true
  if [[ -n "${answer:-}" ]]; then
    PLUGIN_DIR="${answer/#\~/$HOME}"
  fi
fi

mkdir -p "$PLUGIN_DIR"
info "Plugins dir: $PLUGIN_DIR"

# ---------------------------------------------------------------------------
# Resolve install mode
# ---------------------------------------------------------------------------

if [[ -z "$MODE" ]]; then
  if [[ "$ASSUME_YES" -eq 1 || ! -t 0 ]]; then
    MODE="symlink"
  else
    echo
    echo "Install mode:"
    echo "  1) symlink — recommended; \`git pull\` in this repo updates the live plugin"
    echo "  2) copy    — snapshot copied to the plugins folder (no live updates)"
    printf 'Choose [1]: '
    read -r choice || true
    case "${choice:-1}" in
      2|copy|c|C) MODE="copy" ;;
      *) MODE="symlink" ;;
    esac
  fi
fi
info "Install mode: $MODE"

# ---------------------------------------------------------------------------
# Make sources executable
# ---------------------------------------------------------------------------

chmod +x "$ENTRY_SRC"
chmod +x "$REPO/$HELPERS_DIRNAME/sso.sh"
# run.py is NOT chmod +x — SwiftBar would otherwise list it as a separate plugin.
chmod -x "$REPO/$HELPERS_DIRNAME/run.py" 2>/dev/null || true

# ---------------------------------------------------------------------------
# Write/refresh .swiftbarignore in the plugins directory
# ---------------------------------------------------------------------------

IGNORE_DST="$PLUGIN_DIR/.swiftbarignore"
add_ignore_entry() {
  local entry="$1"
  if ! grep -qxF "$entry" "$IGNORE_DST" 2>/dev/null; then
    printf '%s\n' "$entry" >>"$IGNORE_DST"
  fi
}
touch "$IGNORE_DST"
add_ignore_entry ".aws-sso-status/"
add_ignore_entry "__pycache__/"
add_ignore_entry "*.pyc"
add_ignore_entry ".DS_Store"

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

ENTRY_DST="$PLUGIN_DIR/$ENTRY_NAME"
HELPERS_DST="$PLUGIN_DIR/$HELPERS_DIRNAME"

backup_existing() {
  local target="$1"
  [[ -e "$target" || -L "$target" ]] || return 0
  local bk="${target}.bak.$(date +%s)"
  mv -- "$target" "$bk"
  warn "Existing $target moved to $bk"
}

case "$MODE" in
  symlink)
    backup_existing "$ENTRY_DST"
    ln -s "$ENTRY_SRC" "$ENTRY_DST"
    ok "Linked $ENTRY_DST → $ENTRY_SRC"
    # symlink-aware entry resolves $ROOT to the repo, so helpers stay in the repo.
    if [[ -e "$HELPERS_DST" || -L "$HELPERS_DST" ]]; then
      info "$HELPERS_DST already exists — leaving it untouched (entry resolves helpers from repo)."
    fi
    ;;
  copy)
    backup_existing "$ENTRY_DST"
    cp -p "$ENTRY_SRC" "$ENTRY_DST"
    chmod +x "$ENTRY_DST"
    ok "Copied $ENTRY_SRC → $ENTRY_DST"

    backup_existing "$HELPERS_DST"
    mkdir -p "$HELPERS_DST"
    cp -p "$REPO/$HELPERS_DIRNAME/run.py"    "$HELPERS_DST/"
    cp -p "$REPO/$HELPERS_DIRNAME/sso.sh"    "$HELPERS_DST/"
    cp -p "$REPO/$HELPERS_DIRNAME/common.sh" "$HELPERS_DST/"
    cp -p "$REPO/$HELPERS_DIRNAME/icon.png"  "$HELPERS_DST/" 2>/dev/null || true
    chmod +x "$HELPERS_DST/sso.sh"
    chmod -x "$HELPERS_DST/run.py" 2>/dev/null || true
    ok "Copied helpers to $HELPERS_DST/"
    ;;
  *)
    err "Unknown mode: $MODE"
    exit 2
    ;;
esac

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------

echo
ok "Installation complete."
echo
echo "Next steps:"
echo "  1. Open SwiftBar (if not running):  open -a SwiftBar"
echo "  2. SwiftBar menu → Refresh All  (or wait for the next 1-minute tick)"
echo
echo "Notes:"
echo "  • The plugin reads ~/.aws/config to list SSO profiles."
echo "  • Override the default profile with env var SWIFTBAR_AWS_PROFILE."
echo "  • Logs:        ~/.aws/swiftbar-sso-login.log"
echo "  • State files: ~/.aws/swiftbar-{profile,sso-state,sso-just-switched}"
