#!/bin/bash
# Install the SwiftBar AWS SSO plugin into your SwiftBar plugins folder.
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
#   ./install.sh --force               # overwrite existing symlink/file without backup
#   ./install.sh --install-deps        # auto-install missing deps (swiftbar, aws, alerter) via Homebrew

set -euo pipefail

REPO="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENTRY_NAME="swiftbar-aws-sso.py"
ENTRY_SRC="$REPO/$ENTRY_NAME"
HELPERS_DIRNAME=".swiftbar-aws-sso"

MODE=""
PLUGIN_DIR=""
ASSUME_YES=0
FORCE=0
INSTALL_DEPS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --symlink) MODE="symlink"; shift ;;
    --copy)    MODE="copy";    shift ;;
    --plugins-dir) PLUGIN_DIR="${2:-}"; shift 2 ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    --force|-f) FORCE=1; shift ;;
    --install-deps) INSTALL_DEPS=1; shift ;;
    -h|--help)
      sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
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

MISSING_DEPS=()
[[ -d "/Applications/SwiftBar.app" ]] || MISSING_DEPS+=("swiftbar")
command -v aws     >/dev/null 2>&1 || MISSING_DEPS+=("awscli")
command -v alerter >/dev/null 2>&1 || MISSING_DEPS+=("alerter")

install_missing_deps() {
  if ! command -v brew >/dev/null 2>&1; then
    err "Homebrew not found. Install it first: https://brew.sh"
    return 1
  fi
  local failed=()
  for dep in "${MISSING_DEPS[@]}"; do
    info "Installing $dep via Homebrew…"
    case "$dep" in
      swiftbar) brew install --cask swiftbar                        || failed+=("$dep") ;;
      awscli)   brew install awscli                                 || failed+=("$dep") ;;
      alerter)  brew install vitorgalvao/tiny-scripts/alerter       || failed+=("$dep") ;;
    esac
  done
  if [[ ${#failed[@]} -gt 0 ]]; then
    warn "Failed to install: ${failed[*]}. Install them manually."
  else
    ok "Dependencies installed."
  fi
}

if [[ ${#MISSING_DEPS[@]} -gt 0 ]]; then
  warn "Missing dependencies: ${MISSING_DEPS[*]}"
  if [[ "$INSTALL_DEPS" -eq 1 ]]; then
    install_missing_deps
  elif [[ "$ASSUME_YES" -eq 0 && -t 0 ]]; then
    printf 'Install missing deps via Homebrew? [y/N] '
    read -r answer || true
    case "$(printf '%s' "${answer:-}" | tr '[:upper:]' '[:lower:]')" in
      y|yes) install_missing_deps ;;
      *)     info "Skipping. Re-run with --install-deps to install later." ;;
    esac
  else
    info "Re-run with --install-deps to install via Homebrew."
  fi
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

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

ENTRY_DST="$PLUGIN_DIR/$ENTRY_NAME"
HELPERS_DST="$PLUGIN_DIR/$HELPERS_DIRNAME"

backup_existing() {
  local target="$1"
  [[ -e "$target" || -L "$target" ]] || return 0
  if [[ "$FORCE" -eq 1 ]]; then
    rm -f -- "$target"
    return 0
  fi
  local bk="${target}.bak.$(date +%s)"
  mv -- "$target" "$bk"
  warn "Existing $target moved to $bk"
}

case "$MODE" in
  symlink)
    backup_existing "$ENTRY_DST"
    ln -s "$ENTRY_SRC" "$ENTRY_DST"
    ok "Linked $ENTRY_DST → $ENTRY_SRC"
    # Path(__file__).resolve() in the entry follows the symlink back to the
    # repo, so the icon (and any future helper) stays in the cloned repo.
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
    cp -p "$REPO/$HELPERS_DIRNAME/icon.png" "$HELPERS_DST/" 2>/dev/null || true
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
echo "  • Logs: ~/Library/Logs/swiftbar-aws-sso/plugin.log"
