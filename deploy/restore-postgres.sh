#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 BACKUP.dump.gz.age" >&2
  exit 2
fi

: "${AGE_IDENTITY_FILE:?Set AGE_IDENTITY_FILE}"
: "${POSTGRES_USER:?Set POSTGRES_USER}"
: "${POSTGRES_DB:?Set POSTGRES_DB}"

age --decrypt --identity "$AGE_IDENTITY_FILE" "$1" \
  | gzip --decompress \
  | docker compose -f compose.production.yaml exec -T db \
      pg_restore --clean --if-exists --no-owner --no-acl \
      --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"

echo "Restore completed. Run application checks before reopening traffic."
