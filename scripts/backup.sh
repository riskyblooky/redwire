#!/usr/bin/env bash
# RedWire backup — database, MinIO objects, backend/uploads and .env.
#
# Usage (from the install dir, next to docker-compose.yml):
#   ./backup.sh                 full backup into backups/<timestamp>/
#   ./backup.sh --db-only       database dump only (the pre-deploy snapshot)
#   ./backup.sh --install-cron  install a daily 03:30 full backup (/etc/cron.d)
#
# Environment:
#   BACKUP_DIR     where backups go          (default: ./backups)
#   BACKUP_KEEP    how many to keep          (default: 7)
#   BACKUP_REMOTE  optional rsync target, e.g. user@host:/srv/redwire-backups
#
# .env is included because it holds VAULT_ENCRYPTION_KEY / TOTP_ENCRYPTION_KEY:
# a database restored without them can't decrypt the vault. That also makes
# every backup a secret — they are written 0700/0600. A backup on the same
# disk doesn't survive losing the server: set BACKUP_REMOTE or copy them off.
#
# Restore:
#   docker exec -i redwire-db pg_restore -U redwire -d redwire --clean --if-exists < db.dump
#   docker run --rm --volumes-from redwire-minio -v "$PWD":/in alpine \
#       sh -c 'rm -rf /data/* && tar xzf /in/minio.tar.gz -C /data'
#   tar xzf uploads.tar.gz -C backend/
set -euo pipefail

cd "$(dirname "$0")"
# Works both from the install root (deploy package) and from scripts/ (git clone).
[ -f docker-compose.yml ] || cd ..
[ -f docker-compose.yml ] || { echo "backup.sh: no docker-compose.yml here or in the parent dir" >&2; exit 1; }
ROOT="$PWD"

MODE=full
case "${1:-}" in
    "") ;;
    --db-only) MODE=db ;;
    --install-cron)
        cat > /etc/cron.d/redwire-backup <<EOF
# RedWire daily backup (installed by backup.sh --install-cron)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
30 3 * * * root cd "$ROOT" && bash "$ROOT/$(basename "$0")" >> "${BACKUP_DIR:-$ROOT/backups}/backup.log" 2>&1
EOF
        chmod 644 /etc/cron.d/redwire-backup
        mkdir -p "${BACKUP_DIR:-$ROOT/backups}" && chmod 700 "${BACKUP_DIR:-$ROOT/backups}"
        echo "Installed /etc/cron.d/redwire-backup (daily 03:30)."
        exit 0 ;;
    *) echo "usage: $0 [--db-only|--install-cron]" >&2; exit 2 ;;
esac

BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
PGUSER_="$(grep -E '^POSTGRES_USER=' .env 2>/dev/null | cut -d= -f2- || true)"; PGUSER_="${PGUSER_:-redwire}"
PGDB_="$(grep -E '^POSTGRES_DB=' .env 2>/dev/null | cut -d= -f2- || true)"; PGDB_="${PGDB_:-redwire}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

docker inspect -f '{{.State.Running}}' redwire-db 2>/dev/null | grep -q true \
    || { log "redwire-db is not running — nothing to back up"; exit 1; }

# ── Disk check: need the estimated size ×1.5 + 1 GB free ───────────────
db_bytes=$(docker exec redwire-db psql -U "$PGUSER_" -d "$PGDB_" -Atc "select pg_database_size(current_database())")
minio_bytes=0; uploads_bytes=0
if [ "$MODE" = full ]; then
    if docker inspect redwire-minio >/dev/null 2>&1; then
        minio_bytes=$(docker run --rm --volumes-from redwire-minio:ro alpine du -sb /data | cut -f1)
    fi
    [ -d backend/uploads ] && uploads_bytes=$(du -sb backend/uploads | cut -f1)
fi
need=$(( (db_bytes + minio_bytes + uploads_bytes) * 3 / 2 + 1073741824 ))
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
free=$(( $(df -Pk "$BACKUP_DIR" | awk 'NR==2 {print $4}') * 1024 ))
if [ "$free" -lt "$need" ]; then
    log "ABORT: $(( free / 1048576 )) MB free in $BACKUP_DIR, need ~$(( need / 1048576 )) MB"
    exit 3
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SUFFIX=""; [ "$MODE" = db ] && SUFFIX="-predeploy"
OUT="$BACKUP_DIR/$STAMP$SUFFIX"
mkdir -p "$OUT" && chmod 700 "$OUT"
umask 077

log "database → $OUT/db.dump"
docker exec redwire-db pg_dump -U "$PGUSER_" -d "$PGDB_" -Fc > "$OUT/db.dump.partial"
mv "$OUT/db.dump.partial" "$OUT/db.dump"
docker exec redwire-db psql -U "$PGUSER_" -d "$PGDB_" -Atc "select version_num from alembic_version" \
    > "$OUT/alembic_version.txt" 2>/dev/null || true

if [ "$MODE" = full ]; then
    if docker inspect redwire-minio >/dev/null 2>&1; then
        log "minio → $OUT/minio.tar.gz"
        # Stream to the host so the file gets our umask/owner (written
        # inside the container it would be root-owned and 0644).
        docker run --rm --volumes-from redwire-minio:ro alpine \
            tar czf - -C /data . > "$OUT/minio.tar.gz"
    fi
    if [ -d backend/uploads ]; then
        log "uploads → $OUT/uploads.tar.gz"
        tar czf "$OUT/uploads.tar.gz" -C backend uploads
    fi
    [ -f .env ] && install -m 600 .env "$OUT/env" && log ".env → $OUT/env (contains the encryption keys)"
fi
chmod -R go-rwx "$OUT"

# ── Retention: keep the newest $BACKUP_KEEP of this kind (full / predeploy)
ls -1d "$BACKUP_DIR"/2*Z"$SUFFIX" 2>/dev/null | sort | head -n -"$BACKUP_KEEP" | while read -r old; do
    log "pruning $old"; rm -rf "$old"
done

if [ -n "${BACKUP_REMOTE:-}" ]; then
    log "rsync → $BACKUP_REMOTE"
    rsync -a "$OUT" "$BACKUP_REMOTE/"
fi

log "done: $OUT ($(du -sh "$OUT" | cut -f1))"
