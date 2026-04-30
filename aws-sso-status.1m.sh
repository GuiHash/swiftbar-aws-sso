#!/bin/bash
# <swiftbar.title>AWS SSO Status</swiftbar.title>
# <swiftbar.version>3.3.0</swiftbar.version>
# <swiftbar.author>guihash</swiftbar.author>
# <swiftbar.author.github>guihash</swiftbar.author.github>
# <swiftbar.desc>Cloud icon in the menu bar; STS check in background; OS notification when the session expires.</swiftbar.desc>
# <swiftbar.dependencies>python3,aws</swiftbar.dependencies>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideSwiftBar>true</swiftbar.hideSwiftBar>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
# SwiftBar entry point.
# Helpers and Python live in .aws-sso-status/ (any folder starting with "."
# is hidden from SwiftBar's plugin manager — see SwiftBar README).
#
# This script is symlink-aware so install.sh can symlink it directly into
# the SwiftBar plugins folder while keeping the helpers in the cloned repo.

set -e
export PYTHONDONTWRITEBYTECODE=1

SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
  DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
ROOT="$(cd -P "$(dirname "$SOURCE")" && pwd)"

PY="$ROOT/.aws-sso-status/run.py"
exec /usr/bin/env python3 -B "$PY" "$@"
