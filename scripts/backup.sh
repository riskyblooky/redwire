#!/usr/bin/env bash
# RedWire backup — database, MinIO objects and backend/uploads.
#
# Usage (from the install dir, next to docker-compose.yml):
#   ./backup.sh                 full backup into backups/<timestamp>/
#   ./backup.sh --db-only       database dump only
#   ./backup.sh --verify [dir]  restore drill on a backup (default: the newest
#                               full one) — see Verify
#   ./backup.sh --install-cron  install the daily 03:30 backup and the weekly
#                               Sunday 04:30 drill (/etc/cron.d)
#   ./backup.sh --restore-db <db.dump>
#                               replace the database with a dump (see Restore)
#
# Settings (environment variables, or the same names in .env):
#   BACKUP_DIR          where backups go          (default: ./backups)
#   BACKUP_KEEP         how many to keep          (default: 7)
#   BACKUP_REMOTE       optional rsync target, e.g. user@host:/srv/redwire-backups
#   BACKUP_INCLUDE_ENV  1 = also copy .env into the backup (see Keys)
#
# Keys: VAULT_ENCRYPTION_KEY / TOTP_ENCRYPTION_KEY in .env decrypt the vault
# and users' 2FA secrets; a database restored without them is unreadable
# there. Keep them in a secret store, NOT with the database backups — a
# backup holding both hands over every vault secret to whoever gets a copy.
# So .env is not copied by default; each backup records keys.sha256
# (fingerprints only) so --verify and --restore-db can tell whether the keys
# in today's .env still match the backup. BACKUP_INCLUDE_ENV=1 restores the
# old behaviour (the backup is then itself a secret).
#
# A run writes into <stamp>.partial/ and renames it only when every part
# was written and checked, so a failed run never counts toward BACKUP_KEEP.
# MinIO is stopped while its volume is archived, for a consistent copy, and
# started again right after (uploads fail for those seconds). Not paused:
# Docker stops running a paused container's health checks for good, so it
# would stay "unhealthy" after the unpause.
#
# Verify: --verify restores the dump into a scratch database
# (redwire_verify), checks its migration revision, decrypts a vault and a
# TOTP value from it with the current .env keys, tests the archives, and
# drops the scratch database. Exit status 0 = restorable.
#
# Restore:
#   ./backup.sh --restore-db backups/<stamp>/db.dump
#       Stops the app containers, recreates the database empty and restores
#       the dump into it. Start the stack afterwards with images of the
#       dump's version or newer (newer ones migrate it forward on start).
#       Don't pg_restore --clean over the live database instead: tables the
#       dump doesn't know survive it, and the backend then crash-loops
#       re-running migrations that created them.
#   docker compose stop minio
#   docker run --rm --volumes-from redwire-minio -v "$PWD":/in alpine \
#       sh -c 'rm -rf /data/* && tar xzf /in/minio.tar.gz -C /data'
#   tar xzf uploads.tar.gz -C backend/
set -euo pipefail

# This script's absolute path, before the cd below (the cron line runs it
# from wherever it lives: the install root, or scripts/ in a git clone).
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$(dirname "$0")"
# Works both from the install root (deploy package) and from scripts/ (git clone).
[ -f docker-compose.yml ] || cd ..
[ -f docker-compose.yml ] || { echo "backup.sh: no docker-compose.yml here or in the parent dir" >&2; exit 1; }
ROOT="$PWD"

envval() { grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//' || true; }
# BACKUP_* settings: the environment wins, then .env (so the cron job, which
# deploy_server.sh rewrites on every deploy, needs no edits).
for v in BACKUP_DIR BACKUP_KEEP BACKUP_REMOTE BACKUP_INCLUDE_ENV; do
    [ -n "${!v:-}" ] || printf -v "$v" '%s' "$(envval "$v")"
done

MODE=full
case "${1:-}" in
    "") ;;
    --db-only) MODE=db ;;
    --verify) MODE=verify; VDIR="${2:-}" ;;
    --restore-db) MODE=restore; DUMP="${2:-}" ;;
    --install-cron)
        LOGF="${BACKUP_DIR:-$ROOT/backups}/backup.log"
        cat > /etc/cron.d/redwire-backup <<EOF
# RedWire daily backup + weekly restore drill (installed by backup.sh --install-cron)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
30 3 * * * root cd "$ROOT" && bash "$SELF" >> "$LOGF" 2>&1
30 4 * * 0 root cd "$ROOT" && bash "$SELF" --verify >> "$LOGF" 2>&1
EOF
        chmod 644 /etc/cron.d/redwire-backup
        mkdir -p "${BACKUP_DIR:-$ROOT/backups}" && chmod 700 "${BACKUP_DIR:-$ROOT/backups}"
        echo "Installed /etc/cron.d/redwire-backup (daily 03:30 backup, Sunday 04:30 restore drill)."
        exit 0 ;;
    *) echo "usage: $0 [--db-only|--verify [dir]|--install-cron|--restore-db <db.dump>]" >&2; exit 2 ;;
esac

BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
PGUSER_="$(envval POSTGRES_USER)"; PGUSER_="${PGUSER_:-redwire}"
PGDB_="$(envval POSTGRES_DB)"; PGDB_="${PGDB_:-redwire}"
KEY_VARS="VAULT_ENCRYPTION_KEY TOTP_ENCRYPTION_KEY"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# "<VAR> <sha256>" per key; a key that isn't set gets "-" and the hash never
# reveals the key. With a file argument, the keys in that env file. Without,
# the keys the running backend actually uses (compose can supply them from
# outside .env), else the ones in ./.env.
key_fingerprints() {
    local f="${1:-}" v live=""
    [ -z "$f" ] && docker inspect -f '{{.State.Running}}' redwire-backend 2>/dev/null | grep -q true && live=1
    for k in $KEY_VARS; do
        if [ -n "$live" ]; then
            v="$(docker exec redwire-backend printenv "$k" 2>/dev/null || true)"
        else
            v="$(grep -E "^$k=" "${f:-.env}" 2>/dev/null | tail -1 | cut -d= -f2- | sed -e 's/^["'\'']//' -e 's/["'\'']$//' || true)"
        fi
        v="$(printf '%s' "$v" | tr -d '[:space:]')"
        if [ -n "$v" ]; then echo "$k $(printf '%s' "$v" | sha256sum | cut -d' ' -f1)"; else echo "$k -"; fi
    done
}

# Compare a backup dir's recorded keys with today's (see key_fingerprints).
# 0 = match, 1 = mismatch, 2 = the backup recorded nothing to compare.
check_keys() {
    local dir="$1" recorded
    if [ -f "$dir/keys.sha256" ]; then recorded="$(cat "$dir/keys.sha256")"
    elif [ -f "$dir/env" ]; then recorded="$(key_fingerprints "$dir/env")"
    else return 2; fi
    [ "$recorded" = "$(key_fingerprints)" ]
}

docker inspect -f '{{.State.Running}}' redwire-db 2>/dev/null | grep -q true \
    || { log "redwire-db is not running — nothing to back up"; exit 1; }

if [ "$MODE" = restore ]; then
    case "$DUMP" in /*) ;; *) DUMP="$ROOT/$DUMP" ;; esac
    [ -s "$DUMP" ] || { log "no dump at '$DUMP'"; exit 2; }
    rc=0; check_keys "$(dirname "$DUMP")" || rc=$?
    if [ "$rc" = 1 ] && [ "${RESTORE_IGNORE_KEYS:-0}" != 1 ]; then
        log "ABORT: the encryption keys in use now differ from the ones this backup was taken with."
        log "Restoring it would leave vault items and 2FA secrets undecryptable. Put the original"
        log "VAULT_ENCRYPTION_KEY / TOTP_ENCRYPTION_KEY back in .env, or set RESTORE_IGNORE_KEYS=1."
        exit 4
    fi
    [ "$rc" = 2 ] && log "note: this backup has no key fingerprints; can't check the .env keys match"
    log "stopping the app containers"
    docker compose stop backend frontend mcp-server
    log "recreating database $PGDB_"
    docker exec redwire-db psql -v ON_ERROR_STOP=1 -U "$PGUSER_" -d postgres \
        -c "DROP DATABASE IF EXISTS \"$PGDB_\" WITH (FORCE)" \
        -c "CREATE DATABASE \"$PGDB_\" OWNER \"$PGUSER_\""
    log "restoring $DUMP"
    docker exec -i redwire-db pg_restore -U "$PGUSER_" -d "$PGDB_" --exit-on-error < "$DUMP"
    rev=$(docker exec redwire-db psql -U "$PGUSER_" -d "$PGDB_" -Atc "select string_agg(version_num, ',') from alembic_version" 2>/dev/null || true)
    log "restored (alembic revision: ${rev:-unknown}). Start the stack: docker compose up -d --wait"
    exit 0
fi

if [ "$MODE" = verify ]; then
    if [ -z "$VDIR" ]; then
        VDIR="$(ls -1d "$BACKUP_DIR"/2*Z 2>/dev/null | sort | tail -1 || true)"
        [ -n "$VDIR" ] || { log "verify: no full backup in $BACKUP_DIR"; exit 2; }
    fi
    case "$VDIR" in /*) ;; *) VDIR="$ROOT/$VDIR" ;; esac
    [ -s "$VDIR/db.dump" ] || { log "verify: no db.dump in $VDIR"; exit 2; }
    SCRATCH=redwire_verify
    drop_scratch() { docker exec redwire-db psql -q -U "$PGUSER_" -d postgres -c "DROP DATABASE IF EXISTS $SCRATCH WITH (FORCE)" >/dev/null 2>&1 || true; }
    trap drop_scratch EXIT
    fail=0; bad() { log "verify FAIL: $*"; fail=1; }
    log "verify: $VDIR"

    drop_scratch
    docker exec redwire-db psql -q -v ON_ERROR_STOP=1 -U "$PGUSER_" -d postgres -c "CREATE DATABASE $SCRATCH OWNER \"$PGUSER_\"" >/dev/null
    if docker exec -i redwire-db pg_restore -U "$PGUSER_" -d "$SCRATCH" --exit-on-error --no-owner < "$VDIR/db.dump"; then
        q() { docker exec redwire-db psql -U "$PGUSER_" -d "$SCRATCH" -Atc "$1" 2>/dev/null || true; }
        rev="$(q "select string_agg(version_num, ',') from alembic_version")"
        want="$(tr -d '[:space:]' < "$VDIR/alembic_version.txt" 2>/dev/null || true)"
        users="$(q "select count(*) from users")"
        log "  database restored: revision ${rev:-?}, ${users:-?} users"
        [ -n "$want" ] && [ "$rev" != "$want" ] && bad "revision $rev, backup recorded $want"
        [ "${users:-0}" -gt 0 ] 2>/dev/null || bad "no users in the restored database"

        # Decrypt one sample of each encrypted kind with today's keys. Run in
        # the backend container (it has the keys and cryptography); skipped
        # when the backend isn't running or nothing is encrypted.
        for spec in "VAULT_ENCRYPTION_KEY|select v from (select password v from vault_items union all select username from vault_items union all select note from vault_items) x where coalesce(v, '') <> '' limit 1|vault item" \
                    "TOTP_ENCRYPTION_KEY|select totp_secret from users where coalesce(totp_secret, '') <> '' limit 1|2FA secret"; do
            IFS='|' read -r kvar sql what <<< "$spec"
            tok="$(q "$sql")"
            if [ -z "$tok" ]; then log "  $what: none stored, nothing to decrypt"; continue; fi
            if ! docker inspect -f '{{.State.Running}}' redwire-backend 2>/dev/null | grep -q true; then
                log "  $what: backend not running, decrypt check skipped"; continue
            fi
            if printf '%s' "$tok" | docker exec -i -e KVAR="$kvar" redwire-backend python -c \
                'import os,sys; from cryptography.fernet import Fernet; Fernet(os.environ[os.environ["KVAR"]].strip().encode()).decrypt(sys.stdin.read().strip().encode())' \
                >/dev/null 2>&1; then
                log "  $what: decrypts with the current $kvar"
            else
                bad "$what does not decrypt with the current $kvar"
            fi
        done
    else
        bad "pg_restore failed"
    fi

    for a in minio.tar.gz uploads.tar.gz; do
        [ -f "$VDIR/$a" ] || continue
        if gzip -t "$VDIR/$a" 2>/dev/null; then log "  $a: ok"; else bad "$a is corrupt"; fi
    done
    rc=0; check_keys "$VDIR" || rc=$?
    case "$rc" in
        0) log "  encryption keys match the ones in use now" ;;
        1) bad "the encryption keys in use now differ from the ones this backup was taken with" ;;
        2) log "  no key fingerprints recorded (older backup)" ;;
    esac
    if [ "$fail" = 0 ]; then log "verify OK: $VDIR"; else log "verify FAILED: $VDIR"; fi
    exit "$fail"
fi

# ── One run at a time; clear leftovers of runs that died (reboot, kill -9)
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
exec 9>"$BACKUP_DIR/.lock"
flock -n 9 || { log "another backup.sh is running — skipping"; exit 0; }
find "$BACKUP_DIR" -maxdepth 1 -name '*.partial' -type d -exec rm -rf {} + 2>/dev/null || true

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
free=$(( $(df -Pk "$BACKUP_DIR" | awk 'NR==2 {print $4}') * 1024 ))
if [ "$free" -lt "$need" ]; then
    log "ABORT: $(( free / 1048576 )) MB free in $BACKUP_DIR, need ~$(( need / 1048576 )) MB"
    exit 3
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SUFFIX=""; [ "$MODE" = db ] && SUFFIX="-predeploy"
FINAL="$BACKUP_DIR/$STAMP$SUFFIX"
OUT="$FINAL.partial"
MINIO_STOPPED=""
on_exit() {
    [ -n "$MINIO_STOPPED" ] && docker start redwire-minio >/dev/null 2>&1 || true
    [ -n "$OUT" ] && [ -d "$OUT" ] && { log "backup failed — removing $OUT"; rm -rf "$OUT"; }
}
trap on_exit EXIT
mkdir -p "$OUT" && chmod 700 "$OUT"
umask 077

log "database → db.dump"
docker exec redwire-db pg_dump -U "$PGUSER_" -d "$PGDB_" -Fc > "$OUT/db.dump"
docker exec -i redwire-db pg_restore -l < "$OUT/db.dump" > /dev/null \
    || { log "db.dump does not read back"; exit 5; }
docker exec redwire-db psql -U "$PGUSER_" -d "$PGDB_" -Atc "select version_num from alembic_version" \
    > "$OUT/alembic_version.txt" 2>/dev/null || true
key_fingerprints > "$OUT/keys.sha256"

if [ "$MODE" = full ]; then
    if docker inspect redwire-minio >/dev/null 2>&1; then
        log "minio → minio.tar.gz (MinIO stopped meanwhile)"
        if docker inspect -f '{{.State.Running}}' redwire-minio 2>/dev/null | grep -q true; then
            MINIO_STOPPED=1; docker stop -t 30 redwire-minio >/dev/null
        fi
        # Stream to the host so the file gets our umask/owner (written
        # inside the container it would be root-owned and 0644).
        docker run --rm --volumes-from redwire-minio:ro alpine \
            tar czf - -C /data . > "$OUT/minio.tar.gz"
        if [ -n "$MINIO_STOPPED" ]; then docker start redwire-minio >/dev/null; MINIO_STOPPED=""; fi
        gzip -t "$OUT/minio.tar.gz" || { log "minio.tar.gz does not read back"; exit 5; }
    fi
    if [ -d backend/uploads ]; then
        log "uploads → uploads.tar.gz"
        tar czf "$OUT/uploads.tar.gz" -C backend uploads
        gzip -t "$OUT/uploads.tar.gz" || { log "uploads.tar.gz does not read back"; exit 5; }
    fi
    if [ "${BACKUP_INCLUDE_ENV:-0}" = 1 ] && [ -f .env ]; then
        install -m 600 .env "$OUT/env" && log ".env → env (BACKUP_INCLUDE_ENV=1: this backup holds the encryption keys)"
    fi
fi
chmod -R go-rwx "$OUT"
mv "$OUT" "$FINAL"; OUT=""

# ── Retention: keep the newest $BACKUP_KEEP complete backups of this kind
ls -1d "$BACKUP_DIR"/2*Z"$SUFFIX" 2>/dev/null | sort | head -n -"$BACKUP_KEEP" | while read -r old; do
    log "pruning $old"; rm -rf "$old"
done

if [ -n "${BACKUP_REMOTE:-}" ]; then
    log "rsync → $BACKUP_REMOTE"
    rsync -a "$FINAL" "$BACKUP_REMOTE/"
fi

log "done: $FINAL ($(du -sh "$FINAL" | cut -f1))"
