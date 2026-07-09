#!/bin/bash
set -e

# Deployment Script for RedWire Platform
#
# Usage:
#   ./deploy_server.sh                # online: docker compose build (pulls + builds)
#   ./deploy_server.sh --offline      # offline: docker load redwire_images.tar, no build

# Parse flags
OFFLINE=0
for arg in "$@"; do
    case "$arg" in
        --offline) OFFLINE=1 ;;
        -h|--help)
            sed -n '4,9p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            exit 2
            ;;
    esac
done

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== RedWire Platform Deployment ===${NC}"
if [ "$OFFLINE" -eq 1 ]; then
    echo -e "${BLUE}Mode: OFFLINE (loading images from redwire_images.tar, no build)${NC}"
fi

# 1. Prerequisites Check
echo -e "\n${BLUE}[1/8] Checking Prerequisites...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed and/or available in PATH.${NC}"
    echo "Please install Docker manually (e.g., curl -fsSL https://get.docker.com | sh) and try again."
    exit 1
fi
echo "Docker is installed."

# 2. Environment Setup
echo -e "\n${BLUE}[2/8] Configuring Environment...${NC}"

# Fernet keys must be 32 url-safe-base64 bytes — NOT hex. Generate with the
# stdlib so no extra Python package is required on the deploy host.
FERNET_GEN='import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
# Set when we generate an at-rest key on an EXISTING install, so existing data
# (still under the legacy JWT_SECRET-derived key) gets re-keyed after startup.
NEEDS_ROTATION=0

if [ -f .env ]; then
    echo ".env file already exists. Loading configuration..."
    export $(grep -v '^#' .env | xargs)

    # The backend fails closed if either at-rest encryption key is missing
    # (GHSA-pg99). For an existing .env from before these keys existed, generate
    # them now AND flag a re-key: existing vault/TOTP data is still encrypted
    # under the legacy JWT-derived key, so generating without rotating would
    # silently corrupt it. The rotation step (post-startup) migrates the data.
    if [ -z "${VAULT_ENCRYPTION_KEY:-}" ]; then
        VAULT_ENCRYPTION_KEY=$(python3 -c "$FERNET_GEN")
        echo "VAULT_ENCRYPTION_KEY=${VAULT_ENCRYPTION_KEY}" >> .env
        export VAULT_ENCRYPTION_KEY
        echo -e "${BLUE}Generated a new VAULT_ENCRYPTION_KEY and added it to .env.${NC}"
        NEEDS_ROTATION=1
    fi
    if [ -z "${TOTP_ENCRYPTION_KEY:-}" ]; then
        TOTP_ENCRYPTION_KEY=$(python3 -c "$FERNET_GEN")
        echo "TOTP_ENCRYPTION_KEY=${TOTP_ENCRYPTION_KEY}" >> .env
        export TOTP_ENCRYPTION_KEY
        echo -e "${BLUE}Generated a new TOTP_ENCRYPTION_KEY and added it to .env.${NC}"
        NEEDS_ROTATION=1
    fi
    if [ "$NEEDS_ROTATION" -eq 1 ]; then
        echo -e "${RED}IMPORTANT: a new encryption key was generated. Back up Postgres + MinIO${NC}"
        echo -e "${RED}and save the new key(s) from .env. Do NOT change JWT_SECRET until the${NC}"
        echo -e "${RED}re-key step below completes, or existing vault/TOTP data is lost.${NC}"
    fi
    # GHSA-f6pp-m653-9r8r #1: enforce owner-only perms whether we appended
    # new keys or not — an existing .env from a prior deploy could have been
    # written before this chmod landed.
    chmod 600 .env
else
    echo "This script will help you create a secure configuration."
    
    read -p "Enter Domain Name (e.g., app.example.com): " DOMAIN_NAME
    
    read -p "Admin email [admin@redwire.local]: " ADMIN_EMAIL
    ADMIN_EMAIL=${ADMIN_EMAIL:-admin@redwire.local}
    read -sp "Admin password (leave blank for random): " ADMIN_PASSWORD
    echo
    ADMIN_PASSWORD=${ADMIN_PASSWORD:-$(openssl rand -hex 16)}
    read -p "Admin username [admin]: " ADMIN_USERNAME
    ADMIN_USERNAME=${ADMIN_USERNAME:-admin}
    
    echo "Generating secure passwords..."
    POSTGRES_PASSWORD=$(openssl rand -hex 32)
    REDIS_PASSWORD=$(openssl rand -hex 32)
    MINIO_PASSWORD=$(openssl rand -hex 32)
    JWT_SECRET=$(openssl rand -hex 32)
    # FERNET_GEN defined above. Fresh install has no data, so no rotation needed.
    VAULT_ENCRYPTION_KEY=$(python3 -c "$FERNET_GEN")
    TOTP_ENCRYPTION_KEY=$(python3 -c "$FERNET_GEN")

    # Save formatted .env
    cat <<EOF > .env
DOMAIN_NAME=${DOMAIN_NAME}
POSTGRES_USER=redwire
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=redwire
REDIS_PASSWORD=${REDIS_PASSWORD}
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=${MINIO_PASSWORD}
JWT_SECRET=${JWT_SECRET}
NEXT_PUBLIC_API_URL=https://${DOMAIN_NAME}/api
CORS_ORIGINS=https://${DOMAIN_NAME}
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
ADMIN_USERNAME=${ADMIN_USERNAME}
VAULT_ENCRYPTION_KEY=${VAULT_ENCRYPTION_KEY}
TOTP_ENCRYPTION_KEY=${TOTP_ENCRYPTION_KEY}
EOF

    # Save credentials for the user
    cat <<EOF > credentials_DO_NOT_SHARE.txt
=== RedWire Platform Credentials ===
Domain: ${DOMAIN_NAME}
Date: $(date)

Admin Username:       ${ADMIN_USERNAME}
Admin Email:          ${ADMIN_EMAIL}
Admin Password:       ${ADMIN_PASSWORD}

Postgres DB Password: ${POSTGRES_PASSWORD}
Redis Password:       ${REDIS_PASSWORD}
MinIO Root Password:  ${MINIO_PASSWORD}
JWT Secret:           ${JWT_SECRET}
Vault Encryption Key: ${VAULT_ENCRYPTION_KEY}
TOTP Encryption Key:  ${TOTP_ENCRYPTION_KEY}

KEEP THIS FILE SAFE!
EOF

    # GHSA-f6pp-m653-9r8r #1: restrict both secret-bearing files to owner-only
    # BEFORE printing the "created successfully" banner so any operator
    # reading the output sees the perm state that shipped. Default umask
    # (022) would otherwise leave both world-readable.
    chmod 600 .env credentials_DO_NOT_SHARE.txt

    echo -e "${GREEN}.env file created successfully!${NC}"
    echo -e "${GREEN}Credentials saved to 'credentials_DO_NOT_SHARE.txt'.${NC}"
fi

# 3 & 4. Source files.
#
# Two supported layouts:
#   (a) Zip-based migration/upgrade — a redwire_migration_package.zip is
#       present next to this script. Old source dirs get wiped so the
#       zip overlay can't leave deleted files behind, then the zip is
#       extracted. This is what the export_system.ps1 flow produces.
#   (b) Fresh install from a git clone — no zip present. Source is
#       already in place; skip the wipe (it would delete the tree the
#       user just cloned) and the extract (nothing to extract).
if [ -f redwire_migration_package.zip ]; then
    echo -e "\n${BLUE}[3/8] Cleaning stale source files...${NC}"
    for dir in frontend/src frontend/public backend/app backend/alembic; do
        if [ -d "$dir" ]; then
            echo "  Removing old $dir/"
            rm -rf "$dir"
        fi
    done
    for f in frontend/tailwind.config.ts frontend/tailwind.config.js; do
        if [ -f "$f" ]; then
            echo "  Removing stale $f"
            rm -f "$f"
        fi
    done
    echo -e "${GREEN}Source directories cleaned.${NC}"

    # Handle Windows-created zips that may contain backslash path separators.
    echo -e "\n${BLUE}[4/8] Re-extracting fresh source...${NC}"
    python3 -c "
import zipfile, os
z = zipfile.ZipFile('redwire_migration_package.zip')
for info in z.infolist():
    info.filename = info.filename.replace(chr(92), '/')
    if info.filename.startswith('.env'):
        continue
    z.extract(info, '.')
z.close()
"
    echo -e "${GREEN}Source files extracted.${NC}"

    # Compose-file rename cleanup (2026-07): the previous convention was
    # docker-compose.yml=dev + docker-compose.prod.yml=prod. New shape is
    # docker-compose.yml=prod + docker-compose.dev.yml=dev, so a host that
    # upgraded FROM the old zip has a stale docker-compose.prod.yml on
    # disk (the extract step above overwrites docker-compose.yml with the
    # new prod content but doesn't touch the legacy prod filename). Remove
    # it explicitly so `docker compose down` / `up` operators aren't
    # accidentally pointing at a stale file.
    if [ -f docker-compose.prod.yml ]; then
        echo "  Removing stale docker-compose.prod.yml (superseded by docker-compose.yml)"
        rm -f docker-compose.prod.yml
    fi
else
    echo -e "\n${BLUE}[3/8] No migration zip found — using in-place source (git clone install).${NC}"
    if [ ! -d backend ] || [ ! -d frontend ] || [ ! -f docker-compose.yml ]; then
        echo -e "${RED}Error: No redwire_migration_package.zip and no source tree in the current directory.${NC}"
        echo "Run this script from the root of a git clone of RedWire, or"
        echo "place redwire_migration_package.zip next to it."
        exit 1
    fi
    echo -e "${GREEN}Source tree present; nothing to extract.${NC}"
    echo -e "\n${BLUE}[4/8] Skipping extract step (no zip).${NC}"
fi

# 5. SSL Bootstrap
echo -e "\n${BLUE}[5/8] Preparing SSL Certificates...${NC}"
mkdir -p nginx/certbot/conf/live/${DOMAIN_NAME}
mkdir -p nginx/certbot/www
chmod -R 755 nginx/certbot/www

if [ ! -f nginx/certbot/conf/live/${DOMAIN_NAME}/fullchain.pem ]; then
    echo "Generating temporary self-signed certificate for Nginx..."
    openssl req -x509 -nodes -days 1 -newkey rsa:2048 \
        -keyout nginx/certbot/conf/live/${DOMAIN_NAME}/privkey.pem \
        -out nginx/certbot/conf/live/${DOMAIN_NAME}/fullchain.pem \
        -subj "/CN=${DOMAIN_NAME}"
fi

# Uploads volume migration: prior to the uploads_data named volume
# landing in docker-compose.yml, backend/uploads/ (profile photos,
# wordlists) lived on the container's writable layer and got wiped on
# every rebuild. The new volume mount fixes that going forward, but a
# host upgrading past this line still has photos/wordlists inside the
# OLD container's writable layer that would be destroyed the instant
# the container is recreated below. Copy them into the new volume
# first so the upgrade preserves the data.
#
# Idempotent: skipped when the volume already exists (fresh install
# or already-migrated host). Best-effort: cp failure is logged and
# doesn't abort the deploy.
if docker inspect redwire-backend >/dev/null 2>&1; then
    if ! docker volume inspect redwire_uploads_data >/dev/null 2>&1; then
        echo -e "\n${BLUE}[Uploads migration] Preserving profile photos + wordlists into the new uploads_data volume...${NC}"
        docker volume create redwire_uploads_data >/dev/null || true
        docker run --rm \
            --volumes-from redwire-backend \
            -v redwire_uploads_data:/dest \
            alpine:3 sh -c '
                if [ -d /app/uploads ] && [ -n "$(ls -A /app/uploads 2>/dev/null)" ]; then
                    cp -a /app/uploads/. /dest/ && echo "  Copied $(find /dest -type f | wc -l) file(s) into uploads_data."
                else
                    echo "  No pre-existing uploads to preserve."
                fi
            ' 2>&1 || echo -e "${RED}  Warning: upload migration step failed. Check manually before rebuild.${NC}"
    fi
fi

# 6. Start Services
echo -e "\n${BLUE}[6/8] Starting Services...${NC}"
if [ "$OFFLINE" -eq 1 ]; then
    if [ ! -f redwire_images.tar ]; then
        echo -e "${RED}Error: --offline requires redwire_images.tar in the working directory.${NC}"
        echo "Generate one on a connected machine via:  ./export_system.ps1 -IncludeImages"
        exit 1
    fi
    echo "Loading Docker images from redwire_images.tar..."
    docker load -i redwire_images.tar
    echo "Bringing services up (no build)..."
    docker compose up -d --no-build
else
    echo "Building images (requires internet)..."
    # Bake build metadata into the image so /health can report exactly
    # what's live. GIT_COMMIT falls back to "unknown" when the deploy
    # tree isn't a git clone (zip-based install); BUILD_TIME is always
    # captured. Backend Dockerfile picks these up via ARG.
    export GIT_COMMIT=$(git rev-parse --short=12 HEAD 2>/dev/null || echo "unknown")
    export BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    docker compose build \
        --build-arg GIT_COMMIT="$GIT_COMMIT" \
        --build-arg BUILD_TIME="$BUILD_TIME"
    docker compose up -d
fi

echo "Waiting for services to be healthy..."
sleep 15 # Give DB time to initialize

# 7. Database Migration (Safe)
echo -e "\n${BLUE}[7/8] Running Database Migrations...${NC}"
echo "Applying alembic migrations to update schema without data loss..."
docker compose run --rm backend python migrate.py upgrade heads
echo -e "${GREEN}Migrations applied successfully!${NC}"

# 7b. Re-key at-rest data onto freshly generated encryption key(s) (GHSA-pg99).
# Only runs when a key was generated for an existing install above. The script
# is idempotent: it reads legacy data via the JWT-derived key and re-encrypts it
# under the new dedicated key; rows already on the new key are skipped.
if [ "${NEEDS_ROTATION:-0}" -eq 1 ]; then
    echo -e "\n${BLUE}[7b] Re-keying existing vault/TOTP data onto the new encryption key(s)...${NC}"
    docker compose run --rm backend python3 rotate_encryption_keys.py
    echo -e "${GREEN}Encryption key rotation complete.${NC}"
fi

# Legacy Import Check (Skipped by default for safety as requested)
if [ -f redwire_backup.sql ]; then
    echo -e "\n${BLUE}[NOTICE] redwire_backup.sql found but SKIPPING auto-import.${NC}"
    echo "To import and OVERWRITE data, run: cat redwire_backup.sql | docker exec -i redwire-db psql -U redwire -d redwire"
fi

# 8. SSL Certification (Certbot)
echo -e "\n${BLUE}[8/8] SSL Certificate Configuration${NC}"
if [ "$OFFLINE" -eq 1 ]; then
    echo "  Offline mode - Let's Encrypt requires internet, so the temporary self-signed"
    echo "  certificate will be retained. Browsers will show a warning until you replace"
    echo "  it with an internal CA-signed cert at nginx/certbot/conf/live/${DOMAIN_NAME}/."
    SETUP_CERTBOT=n
else
    echo ""
    echo "  Your platform is currently running with a temporary self-signed certificate."
    echo "  If this server is publicly accessible with DNS pointing to it, you can request"
    echo "  a free Let's Encrypt certificate now."
    echo ""
    echo "  For on-prem / internal deployments, skip this step - the self-signed cert will"
    echo "  keep HTTPS working (browsers will show a warning, which you can accept)."
    echo ""
    read -p "Request a Let's Encrypt certificate? (y/N): " SETUP_CERTBOT
    SETUP_CERTBOT=${SETUP_CERTBOT:-n}
fi

if [[ "$SETUP_CERTBOT" =~ ^[Yy]$ ]]; then
    read -p "Email for Let's Encrypt notifications [admin@${DOMAIN_NAME}]: " CERTBOT_EMAIL
    CERTBOT_EMAIL=${CERTBOT_EMAIL:-admin@${DOMAIN_NAME}}

    echo "Requesting certificate for $DOMAIN_NAME..."

    # Register account (if needed)
    docker compose run --rm --entrypoint certbot certbot register \
        --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email --non-interactive || true

    # Request cert (using webroot)
    docker compose run --rm --entrypoint certbot certbot certonly \
        --webroot --webroot-path /var/www/certbot -d "$DOMAIN_NAME" --non-interactive --force-renewal

    echo "Reloading Nginx with new certificate..."
    docker compose restart nginx
    echo -e "${GREEN}Let's Encrypt certificate installed!${NC}"
else
    echo -e "${BLUE}Skipping Certbot - using self-signed certificate.${NC}"
    echo "You can request a certificate later by running:"
    echo "  docker compose run --rm --entrypoint certbot certbot certonly \\"
    echo "    --webroot --webroot-path /var/www/certbot -d $DOMAIN_NAME --non-interactive"
    echo "  docker compose restart nginx"
fi

echo -e "\n${GREEN}=== Deployment Complete! ===${NC}"
echo -e "Access your platform at: https://${DOMAIN_NAME}"
