#!/bin/sh
# Dump Postgres and the raw files volume into backups/<timestamp>.
set -eu
cd "$(dirname "$0")/.."
name="$(date -u +%Y%m%dT%H%M%SZ)"
target="backups/$name"
mkdir -p "$target"
chmod 700 backups "$target"

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$target/db.dump"
docker compose exec -T backend tar -C /data/raw -cf - . > "$target/raw.tar"

# A dump that cannot be listed is not a backup.
docker compose exec -T db sh -c 'cat > /tmp/check.dump && pg_restore -l /tmp/check.dump > /dev/null && rm /tmp/check.dump' < "$target/db.dump"
echo "Backup written to $target"
