#!/bin/sh
# Thin wrapper so agents can call one stable path regardless of python location.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$DIR/ensure-project.py" "$@"
fi
exec /usr/bin/python3 "$DIR/ensure-project.py" "$@"
