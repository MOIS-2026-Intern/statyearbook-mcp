#!/bin/sh
set -eu

profile="${APP_PROFILE:-local}"
case "$profile" in
  local|test|main) ;;
  *)
    echo "APP_PROFILE must be one of: local, test, main" >&2
    exit 1
    ;;
esac

profile_file="/opt/statyearbook/profiles/${profile}.env"
while IFS='=' read -r name value; do
  case "$name" in
    ''|'#'*) continue ;;
  esac
  if ! printenv "$name" >/dev/null 2>&1; then
    export "$name=$value"
  fi
done < "$profile_file"

exec docker-entrypoint.sh "$@"
