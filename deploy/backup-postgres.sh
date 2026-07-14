#!/usr/bin/env sh
set -eu

: "${BACKUP_DIR:?Set BACKUP_DIR}"
: "${BACKUP_ENCRYPTION_RECIPIENT:?Set BACKUP_ENCRYPTION_RECIPIENT to an age recipient}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="${BACKUP_DIR%/}/postgres-${timestamp}.dump.gz.age"
mkdir -p "$BACKUP_DIR"

docker compose -f compose.production.yaml exec -T db \
  pg_dump --format=custom --no-owner --no-acl \
  --username="$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip \
  | age --recipient "$BACKUP_ENCRYPTION_RECIPIENT" --output "$destination"

echo "Encrypted database backup written to $destination"
