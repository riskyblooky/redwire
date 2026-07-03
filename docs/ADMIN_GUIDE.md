# RedWire admin guide

Everything an operator needs to deploy, configure, back up, upgrade, and
keep RedWire running. For the environment-variable reference itself, see
[`.env.example`](../.env.example) at the repo root — every var is
documented inline there.

- [Architecture at a glance](#architecture-at-a-glance)
- [First-time install](#first-time-install)
- [TLS and certificates](#tls-and-certificates)
- [Running behind an existing reverse proxy](#running-behind-an-existing-reverse-proxy)
- [Backups](#backups)
- [Restoring from backup](#restoring-from-backup)
- [Upgrades](#upgrades)
- [Rotating credentials and keys](#rotating-credentials-and-keys)
- [Optional integrations](#optional-integrations)
- [Plugins](#plugins)
- [Troubleshooting](#troubleshooting)

---

## Architecture at a glance

Seven services on one Compose network. Only nginx exposes ports to the
host in prod — everything else is internal to the Docker network.

```
                          ┌────────────────────────┐
     browser ──443/HTTPS──▶│         nginx          │◀── certbot (renewals)
                          │  (server_name = DOMAIN)│
                          └───┬────────────────┬───┘
                              │                │
                    static/HMR│                │/api/*
                              ▼                ▼
                       ┌────────────┐    ┌────────────┐
                       │  frontend  │    │  backend   │
                       │ Next.js 15 │    │  FastAPI   │
                       │   :3000    │    │   :8000    │
                       └────────────┘    └─────┬──────┘
                                                │
       ┌────────────────┬──────────────┬────────┴───┬─────────────┐
       ▼                ▼              ▼            ▼             ▼
  ┌─────────┐    ┌────────────┐   ┌────────┐  ┌───────────┐  ┌─────────┐
  │ postgres│    │   redis    │   │ minio  │  │  mcp-svr  │  │ plugins │
  │  :5432  │    │   :6379    │   │ :9000  │  │  :3001    │  │ (in-svc)│
  └─────────┘    └────────────┘   └────────┘  └───────────┘  └─────────┘
```

**Ports exposed to the host (prod, `docker-compose.prod.yml`):**

| Host port | Service | Purpose |
|---|---|---|
| 80 | nginx | ACME HTTP-01 + 301 redirect to HTTPS |
| 443 | nginx | The one public port. TLS terminated here. |

Everything else (Postgres, Redis, MinIO, MCP, backend, frontend) is
network-internal and unreachable from outside the host. This is by
design — do not add `ports:` mappings for those services in prod.

**Ports exposed in dev (`docker-compose.yml`) for local hacking:**

| Host port | Service | Purpose |
|---|---|---|
| 5432 | postgres | Direct DB access (`psql`, DBeaver) |
| 6379 | redis | Direct Redis access |
| 8000 | backend | Bypass nginx during backend work |
| 9000 / 9001 | minio / minio-console | Bucket admin UI |
| 3001 | mcp-server | MCP SSE endpoint |
| 8080 / 8443 | nginx (dev) | Test the full nginx flow locally |

---

## First-time install

Prerequisites: Docker + Docker Compose, `git`, Python 3, `openssl` (all
present on any modern Linux). ~2 GB RAM minimum; 4 GB recommended.

```bash
git clone <repository-url>
cd redwire
./scripts/deploy_server.sh
```

The script:

1. **Prompts** for `DOMAIN_NAME`, admin username, admin email, and admin
   password (blank → random hex).
2. **Generates** cryptographically-strong random values for every secret
   in `.env`:
   - `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `MINIO_ROOT_PASSWORD`, `JWT_SECRET` — each 32 random bytes as hex.
   - `VAULT_ENCRYPTION_KEY`, `TOTP_ENCRYPTION_KEY` — real **Fernet** keys (44-char base64). Hex values will NOT work for these.
3. **Writes** `.env` and `credentials_DO_NOT_SHARE.txt` at mode `0600`.
4. **Builds and starts** every service via `docker-compose.prod.yml`.
5. **Runs Alembic migrations** (via `backend/migrate.py` — advances every
   plugin branch too, not just core).
6. **Optionally bootstraps** a Let's Encrypt certificate via Certbot.
   Skip it for on-prem / internal-CA setups; the temporary self-signed
   cert continues to work.

When the script exits, the platform is reachable at `https://<your-domain>`
and the admin credentials are in `credentials_DO_NOT_SHARE.txt`. **Move
that file somewhere safe and delete the copy on the server.**

### Fresh install from a git clone vs. an offline zip

The deploy script auto-detects which flow to use:

- **`redwire_migration_package.zip` present** — extracts the zip (upgrade
  path from an older install or export from `scripts/export_system.ps1`).
- **No zip present** — uses the in-place source (git clone case). Skips
  the wipe-and-extract step so it doesn't delete the files you just
  cloned.

Offline installs (air-gapped hosts): generate `redwire_images.tar` on a
connected machine with `pwsh scripts/export_system.ps1 -IncludeImages`,
ship both the zip and tar to the target, run `./deploy_server.sh --offline`.

---

## TLS and certificates

Three supported topologies. Pick the one that matches your deploy.

### 1. Let's Encrypt (public internet, RedWire is the only proxy)

The default when you say yes to the Certbot prompt in `deploy_server.sh`.
The script generates a self-signed placeholder cert so nginx boots, then
uses the webroot challenge on port 80 to swap in a real cert.

Renewal is automatic — the `certbot` container runs `certbot renew`
every 12 hours. As long as ports 80 and 443 stay open in your firewall,
you don't have to think about it.

### 2. Bring your own cert (internal CA, wildcard, corporate PKI)

Skip the Certbot prompt. Drop your fullchain + private key into:

```
nginx/certbot/conf/live/${DOMAIN_NAME}/fullchain.pem
nginx/certbot/conf/live/${DOMAIN_NAME}/privkey.pem
```

Then `docker compose -f docker-compose.prod.yml restart nginx`. Nothing
else changes; the nginx config already reads from that path.

### 3. Behind another reverse proxy (chained nginx / traefik / CDN)

If TLS is terminated **upstream** (in front of RedWire's nginx), then
RedWire's nginx doesn't need to do TLS at all. See the next section for
the full drill.

---

## Running behind an existing reverse proxy

Common in enterprise deploys — RedWire sits behind an outer load
balancer / WAF / corporate proxy that owns the public cert.

### Things that must be right

1. **The outer proxy must terminate TLS and forward plain HTTP** to
   RedWire's nginx. Modify RedWire's `nginx/conf.d/default.conf.template`
   so the `listen 443 ssl;` block becomes `listen 80;` (and drop the
   `ssl_certificate` / `ssl_certificate_key` lines), then point the outer
   proxy at RedWire's port 80 (or whatever port you map that to). If the
   outer proxy forwards plain HTTP to RedWire's HTTPS listener, you get
   `400 Bad Request — The plain HTTP request was sent to HTTPS port`.

2. **The outer proxy must forward these headers accurately**:

   ```
   proxy_set_header Host              $http_host;      # keep the port
   proxy_set_header X-Real-IP         $remote_addr;    # for rate limiting
   proxy_set_header X-Forwarded-For   $remote_addr;    # do NOT append — see below
   proxy_set_header X-Forwarded-Proto https;           # so cookies get Secure flag
   proxy_set_header Origin            $http_origin;    # preserve the port
   ```

   `$host` (without port) breaks CORS behind non-default ports.
   `proxy_add_x_forwarded_for` (which appends the client's own header)
   opens X-Forwarded-For spoofing that lets a caller escape the rate
   limiter (GHSA-xg53-8wgq-w9cw). Use `$remote_addr` alone.

3. **Set `CORS_ORIGINS`** to exactly what the browser sends in `Origin`.
   That's the URL bar's origin — scheme + host + port, no path. If the
   URL bar shows `https://redwire.example.com` (default 443), the port
   is omitted in `Origin` per the CORS spec.

4. **Set `NEXT_PUBLIC_API_URL=/api`** and rebuild the frontend. This
   avoids the class of "the API URL doesn't include the port the users
   are actually visiting" problems entirely — the client uses the
   current page's origin, which is always right.

### If you can't touch the outer proxy configs

Add EVERY origin the browser might send to `CORS_ORIGINS`, port-having
and port-less:

```
CORS_ORIGINS=https://redwire.example.com,https://redwire.example.com:8443
```

---

## Backups

Four things need backup. In priority order:

| # | What | Where | If lost |
|---|---|---|---|
| 1 | `VAULT_ENCRYPTION_KEY` + `TOTP_ENCRYPTION_KEY` | `.env` | Every vault credential + every user's TOTP secret becomes unrecoverable. There is no admin override for lost-key decrypt. |
| 2 | Postgres data | `postgres_data` Docker volume | All engagements, findings, users, audit trail, settings |
| 3 | MinIO evidence bucket | `minio_data` Docker volume | Uploaded evidence files, generated reports, plugin assets |
| 4 | `.env` (rest of it) | Repo root | Config only — you can regenerate on install, but you'll lose custom values |

The encryption keys should live in a DIFFERENT backup than the database.
Backing them up in the same file/vault as the DB means an attacker who
gets the DB backup also gets the keys, and every "encrypted at rest"
value becomes plaintext to them.

### Postgres backup

```bash
docker exec redwire-db pg_dump -U redwire redwire | gzip > redwire-$(date +%F).sql.gz
```

Cron this. Rotate weekly; keep 30 days.

### MinIO backup

```bash
docker exec redwire-minio mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
docker exec redwire-minio mc mirror --overwrite local/redwire-evidence /tmp/evidence-backup
docker cp redwire-minio:/tmp/evidence-backup ./evidence-$(date +%F)
```

For large buckets, prefer `mc mirror` to a remote S3 target instead of
pulling to disk locally.

### `.env` backup

Whatever secret store your team uses. **Not** in the same git repo, not
in the same S3 bucket as the DB backup, not on the same host in an
un-restricted directory.

---

## Restoring from backup

Prerequisites: the Fernet keys from the original install (else the
vault + TOTP data comes back as unreadable ciphertext).

```bash
# 1. Restore .env with the original VAULT_ENCRYPTION_KEY / TOTP_ENCRYPTION_KEY / JWT_SECRET
cp path/to/backup/.env .env
chmod 600 .env

# 2. Start Postgres alone
docker compose -f docker-compose.prod.yml up -d postgres

# 3. Restore the DB
gunzip -c redwire-YYYY-MM-DD.sql.gz | docker exec -i redwire-db psql -U redwire -d redwire

# 4. Restore MinIO
docker compose -f docker-compose.prod.yml up -d minio
docker exec redwire-minio mc alias set local http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
docker cp ./evidence-YYYY-MM-DD redwire-minio:/tmp/evidence-restore
docker exec redwire-minio mc mirror --overwrite /tmp/evidence-restore local/redwire-evidence

# 5. Bring the rest up
docker compose -f docker-compose.prod.yml up -d
```

Verify by logging in as the original admin and opening an engagement
whose vault items you know the plaintext of — if the values decrypt
cleanly you have the right keys.

---

## Upgrades

The canonical upgrade path is a re-run of `deploy_server.sh` from a
newer git clone (or with a newer `redwire_migration_package.zip` in
place):

```bash
cd /path/to/redwire
git pull
./scripts/deploy_server.sh
```

The script:

- Preserves your existing `.env` (does NOT prompt again).
- Adds any newly-required secret keys if they're missing (currently
  `VAULT_ENCRYPTION_KEY` / `TOTP_ENCRYPTION_KEY` — this is what makes
  upgrades from pre-1.2 installs safe; if it generates new keys it also
  runs `rotate_encryption_keys.py` to migrate existing data onto them).
- Rebuilds the images.
- Runs `python migrate.py upgrade heads` (all Alembic branches — core +
  every plugin).
- Restarts the stack.

Downtime during a normal upgrade is ~30–60 seconds while the containers
restart. Postgres data + MinIO buckets are volume-mounted so they
survive the container swap.

### Rolling back

Bring the previous version's images back up:

```bash
docker compose -f docker-compose.prod.yml down
git checkout <previous-tag>
docker compose -f docker-compose.prod.yml up -d --build
```

**Alembic migrations are one-way** in most cases — a rollback of the
images doesn't roll back the DB schema. If the new version added
columns and you go back, the old backend hits columns it doesn't know
about (usually fine — it just ignores them). If the new version dropped
or renamed columns, roll the DB back too:

```bash
python migrate.py downgrade -1
```

---

## Rotating credentials and keys

### Admin password

Log in as the admin and change it from Settings → Profile. No compose
work needed. To do it from the DB shell (lost admin password scenario):

```bash
docker exec -it redwire-backend python -c "
from auth.password import get_password_hash
print(get_password_hash('newpassword'))
"
docker exec -it redwire-db psql -U redwire -d redwire -c \
    "UPDATE users SET hashed_password='<hash from above>' WHERE username='admin';"
```

### Postgres / Redis / MinIO passwords

These are stored in `.env` and read by both Compose (to init the
service) and the backend (to connect). Change one at a time:

```bash
# Example: rotate REDIS_PASSWORD
sed -i 's/^REDIS_PASSWORD=.*/REDIS_PASSWORD=<new-value>/' .env
docker compose -f docker-compose.prod.yml up -d --force-recreate redis backend
```

Both services need to restart together — old backend + new Redis (or
vice versa) means the backend can't authenticate.

### `JWT_SECRET`

Rotating this invalidates every active session — every user gets
logged out on the next request. Do it during a maintenance window.

```bash
sed -i "s/^JWT_SECRET=.*/JWT_SECRET=$(openssl rand -hex 32)/" .env
docker compose -f docker-compose.prod.yml restart backend
```

### `VAULT_ENCRYPTION_KEY` / `TOTP_ENCRYPTION_KEY`

**Do not just change these.** The vault + TOTP tables contain ciphertext
encrypted under the OLD key; changing the key without re-encrypting the
data leaves it undecryptable, exactly like losing the key.

The safe rotation flow:

```bash
# 1. Take a backup FIRST
docker exec redwire-db pg_dump -U redwire redwire | gzip > pre-rotate-$(date +%F).sql.gz

# 2. Add the new key to .env alongside the old one — the rotation script
#    reads both.
echo "VAULT_ENCRYPTION_KEY_NEW=$(python3 -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")" >> .env

# 3. Run the rotation script — decrypts under OLD, re-encrypts under NEW.
docker compose -f docker-compose.prod.yml run --rm backend python rotate_encryption_keys.py

# 4. Promote NEW → active and remove OLD.
# (Edit .env: VAULT_ENCRYPTION_KEY=<new value>, remove _NEW)
docker compose -f docker-compose.prod.yml restart backend
```

Same shape for `TOTP_ENCRYPTION_KEY`.

---

## Optional integrations

RedWire supports three optional identity / notification providers.
**None are configured via env vars** — all three live in the
`auth_settings` DB table and are configured from the admin UI. This
keeps secrets out of `.env` and lets you rotate them without restarts.

### LDAP (Active Directory / OpenLDAP)

Admin → Auth Settings → LDAP:

- Enable the integration.
- Enter `server_url` — `ldap://` for plaintext or `ldap://` with
  StartTLS mode, or `ldaps://` for direct TLS from connect.
- Pick TLS mode: `LDAPS`, `StartTLS`, or `None` (not recommended —
  cleartext bind).
- Toggle "Verify certificate" off ONLY for self-signed servers where you
  can't ship a CA cert (marked "insecure" in the UI).
- Configure `bind_dn`, `bind_password`, `search_base`, and the attribute
  mapping (`username_attribute`, `email_attribute`, etc.).
- Test the connection before saving.

RedWire uses JIT (just-in-time) provisioning — LDAP users show up in
the users table on first successful login.

### SAML 2.0 SSO

Admin → Auth Settings → SAML:

- Provide the IdP metadata: `idp_entity_id`, `idp_sso_url`,
  `idp_slo_url`, `idp_x509_cert`.
- Set your SP entity ID (usually your domain).
- Enable "Require signed messages" if your IdP signs.

Also set `BACKEND_URL` and `FRONTEND_URL` in `.env` — they're used to
construct the AssertionConsumerService callback URL. Get those wrong
and SAML validation fails with cryptic errors.

### SMTP (password reset emails, notification digests)

Admin → Auth Settings → SMTP:

- Standard SMTP fields (host, port, username, password, from address).
- Enable STARTTLS if your server supports it (most do on port 587).
- Test with the "send test email" button before enabling in production.

---

## Plugins

RedWire ships two example plugins (`servicenow_cmdb`, `shodan_enricher`)
in `backend/plugins/`. Third-party or private plugins drop in the same
directory and are discovered on backend startup.

Each plugin can register:

- Backend routes (mounted under `/plugins/<slug>` with `Depends(get_current_user)`).
- Event handlers (subscribe to CRUD events + lifecycle hooks like
  `auth.login.success`, `report.generated`).
- Sidebar nav items (with an icon and per-permission RBAC gate).
- Dashboard widgets.
- Admin settings (encrypted at rest when `type: secret`).
- Alembic migrations on their own branch (`plugin:<slug>`).
- Frontend React pages under `frontend/`.
- Extension slots — plugin components rendered inside core pages via
  `<PluginSlot slot="...">`.

For the full plugin author reference, see
[`backend/plugins/README.md`](../backend/plugins/README.md).

**Operator workflow:**

- **Enable / disable a plugin at runtime:** Admin → Plugins → toggle.
  Routes go 503, event listeners silence, sidebar item disappears. No
  restart needed.
- **Configure plugin settings:** Admin → Plugins → click the plugin.
- **Install a new plugin:** drop the plugin dir into `backend/plugins/<slug>/`,
  restart the backend (`docker compose restart backend`). If the plugin
  ships frontend pages, rebuild the frontend image too:
  ```
  docker compose -f docker-compose.prod.yml build frontend
  docker compose -f docker-compose.prod.yml up -d frontend
  ```
- **Uninstall:** `rm -rf backend/plugins/<slug>/` + restart. Any data the
  plugin persisted stays until you drop its tables (they're on their
  own Alembic branch — see `backend/migrate.py` for the multi-head
  handling).

---

## Troubleshooting

### 502 Bad Gateway from nginx

The service nginx tries to proxy to isn't responding. Usually:

- **Frontend or backend container down.** `docker compose ps` — anything
  in `Exited` state? `docker logs redwire-<service>` for why.
- **Container starting up.** Give it 30–60 seconds after
  `docker compose up`. The backend runs migrations before it accepts
  connections.
- **Nginx can't resolve the upstream hostname.** Rare, happens after a
  compose down/up when nginx cached a stale DNS. `docker compose restart nginx`.

### 400 Bad Request when going through an external proxy

Almost always "The plain HTTP request was sent to HTTPS port." Your
outer proxy is forwarding plain HTTP to RedWire's HTTPS listener. See
[Running behind an existing reverse proxy](#running-behind-an-existing-reverse-proxy).

### CORS error in the browser console

The `Origin` header the backend receives doesn't match anything in
`CORS_ORIGINS`. Steps:

1. Open DevTools → Network → click the failing request → Request Headers.
   Copy the `Origin` value **verbatim** (including scheme, host, and any
   port).
2. Compare to `CORS_ORIGINS` in `.env`.
3. If they differ:
   - Simple case — add the exact value to `CORS_ORIGINS`, restart backend.
   - Complex case (behind chained proxies) — one of the intermediate
     proxies is rewriting `Origin`. See
     [Running behind an existing reverse proxy](#running-behind-an-existing-reverse-proxy).

Special gotcha: **the browser strips the port from `Origin` when it's
the default for the scheme** (443 for https, 80 for http). If your URL
bar shows `https://redwire.example.com` (no port), the port is 443, and
`Origin: https://redwire.example.com` is what the browser sends — not
`:443`.

### Frontend shows stale content after a deploy

`NEXT_PUBLIC_API_URL` is baked into the client bundle at BUILD time —
changing `.env` doesn't help until you rebuild:

```bash
docker compose -f docker-compose.prod.yml build --no-cache frontend
docker compose -f docker-compose.prod.yml up -d frontend
```

Also possible: browser cache. Hard refresh (Cmd/Ctrl+Shift+R) or clear
site data.

### Vault decrypt errors after restore or key change

Usually one of two things:

- Restored the DB but forgot to restore `.env` with the ORIGINAL
  `VAULT_ENCRYPTION_KEY`. There is no way to recover this — the DB
  ciphertext is encrypted under the missing key.
- Rotated `VAULT_ENCRYPTION_KEY` without running
  `rotate_encryption_keys.py` first. Restore the old key temporarily,
  run the rotation, then set the new key.

### "Rate limit exceeded" on login for internal testing

RedWire caps `/auth/login` at 5/minute per `X-Real-IP` (or per
`no-trusted-proxy` bucket when no proxy header is set). See
`backend/rate_limit.py`. For internal load testing, set distinct
`X-Real-IP` headers per test client — from outside a trusted-proxy CIDR
that header would be ignored, but the test setup can control it. See
`scripts/stress_test.py` (dev-only, gitignored) for the pattern.

### Certbot renewal failing

```bash
docker logs redwire-certbot --tail 50
```

Common causes:

- Port 80 blocked at the firewall — LE uses HTTP-01 challenge on 80.
- DNS points somewhere else — verify `dig $DOMAIN_NAME` returns the
  host running RedWire's nginx.
- Rate-limited by LE (5 duplicate certs per week). Wait a few days or
  request a staging cert.

### Backend log volume too high

Set `SQL_ECHO=false` in `.env` (or unset it) and restart the backend.
Dev compose sets it to `true` for local debugging — never carry that
setting to prod.

---

For further reading:

- [`.env.example`](../.env.example) — every env var with usage notes
- [`backend/plugins/README.md`](../backend/plugins/README.md) — plugin authoring reference
- [`README.md`](../README.md) — project overview, quick start, features
- [`SECURITY.md`](../SECURITY.md) — vulnerability reporting
