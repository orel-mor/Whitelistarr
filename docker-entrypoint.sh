#!/bin/sh
# Start as root only long enough to make the /data volume writable, then drop to
# an unprivileged PUID:PGID (default 1000:1000) via setpriv. Set PUID/PGID to
# match your host user if the bind-mounted ./data directory has restrictive
# ownership.
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

mkdir -p /data
chown -R "${PUID}:${PGID}" /data 2>/dev/null || true

exec setpriv --reuid "${PUID}" --regid "${PGID}" --clear-groups --no-new-privs "$@"
