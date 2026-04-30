#!/bin/bash
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
