#!/bin/sh
# Replace the database and raw files with a backup: scripts/restore.sh backups/<timestamp>
set -eu
cd "$(dirname "$0")/.."
source="${1:-}"
if [ ! -f "$source/db.dump" ] || [ ! -f "$source/raw.tar" ]; then
  echo "Usage: scripts/restore.sh backups/<timestamp>" >&2
  exit 1
fi

docker compose up -d --wait db
docker compose stop backend worker frontend
docker compose exec -T db sh -c '
  cat > /tmp/restore.dump
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --exit-on-error /tmp/restore.dump
  rm /tmp/restore.dump' < "$source/db.dump"
docker compose run --rm -T --no-deps backend sh -c 'find /data/raw -mindepth 1 -delete && tar -C /data/raw -xf -' < "$source/raw.tar"
docker compose up -d --wait
echo "Restored from $source"
