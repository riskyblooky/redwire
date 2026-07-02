<p align="center">
  <img src="docs/images/logo.png" alt="RedWire" width="520">
</p>

<p align="center">
  A self-hosted platform for red team operations management: engagements, findings, assets, evidence, credential vault, cleanup artifacts, runbooks, and professional reporting.
</p>

<p align="center">
  <a href="https://www.typescriptlang.org/"><img src="https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript"></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=next.js&logoColor=white" alt="Next.js"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://www.postgresql.org/"><img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"></a>
</p>

# RedWire

## Overview

RedWire centralizes the operational side of an engagement: who is doing what, what was found, what evidence supports it, what credentials were captured, what was left behind, and what the client receives at the end. It is designed to be run on infrastructure you control.

## Features

- **Authentication and access control** — JWT auth with refresh, optional TOTP, LDAP and SAML SSO, and role-based permissions scoped per engagement.
- **Engagement management** — Engagement lifecycle from proposal through active, complete, and archived states, with per-engagement team assignment and permissions.
- **Findings** — CVSS-scored vulnerability tracking with templates, references, MITRE ATT&CK mapping, evidence attachments, and rich-text editing.
- **Test cases** — Reusable methodology library with ATT&CK mapping, parity with findings for templates and references.
- **Assets** — In-scope asset inventory per engagement with import/export.
- **Evidence** — Encrypted file uploads backed by S3-compatible storage (MinIO).
- **Credential vault** — Per-engagement vault with at-rest encryption for captured credentials and secrets.
- **Cleanup artifacts** — Track everything dropped on target systems so it can be removed before reporting.
- **Runbooks** — Operator-facing checklists and procedures with tree-structured items and templates.
- **Reporting** — PDF and Markdown report generation with customisable layouts, themes, inline images, tables, and rich-text content.
- **Collaboration** — Real-time presence, version history, soft-locks while another user is editing, and a full audit log for create/update/delete operations.
- **Automations** — Trigger actions on finding and test case state changes with tag-based conditions.
- **MCP server** — Exposes RedWire as MCP tools for LLM clients (Claude Desktop, in-app chatbot).
- **Plugin system** — Drop-in backend plugins with manifest, event bus, and settings.

## Technology stack

**Frontend**
- Next.js 14 (App Router), React 18, TypeScript
- Tailwind CSS v4, shadcn/ui (dark theme)
- TanStack Query, Zustand
- TipTap editor with Y.js for collaborative editing

**Backend**
- Python FastAPI (async), SQLAlchemy 2.x, Alembic
- PostgreSQL 15, Redis, MinIO (S3-compatible)
- ReportLab for PDF generation

**Infrastructure**
- Docker and Docker Compose
- Nginx reverse proxy with Certbot for Let's Encrypt

## Quick start

### Prerequisites

- Docker and Docker Compose
- Git, Python 3, OpenSSL (present on any modern Linux)
- 2 GB free RAM minimum (4 GB recommended for production)

### Installation

```bash
git clone <repository-url>
cd redwire
./scripts/deploy_server.sh
```

The deploy script is the supported install path. It:

- Prompts for the deploy domain, admin username, admin email, and admin password (blank → random)
- Generates strong random values for every secret in `.env`:
  - `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `MINIO_ROOT_PASSWORD`, `JWT_SECRET` — each 32 random bytes as hex
  - `VAULT_ENCRYPTION_KEY`, `TOTP_ENCRYPTION_KEY` — proper Fernet keys (32 URL-safe base64 bytes; hex will NOT work)
- Writes `.env` and `credentials_DO_NOT_SHARE.txt` at mode `0600`
- Builds and starts all services via `docker-compose.prod.yml`
- Runs Alembic migrations
- Optionally bootstraps a Let's Encrypt certificate via Certbot (skip for on-prem / internal deployments — a self-signed cert is installed and works fine)

When the script exits, the platform is reachable at `https://<your-domain>` and the admin credentials are in `credentials_DO_NOT_SHARE.txt`. **Back up `VAULT_ENCRYPTION_KEY` separately from the database — losing it means losing access to all vault data.**

**Offline installs:** On a connected machine run `pwsh scripts/export_system.ps1 -IncludeImages` to produce `redwire_migration_package.zip` plus `redwire_images.tar`, ship both to the target, and run `./deploy_server.sh --offline`.

### Manual configuration (advanced)

If you need to configure `.env` by hand instead of letting the script do it, `cp .env.example .env` and generate secrets as follows:

```bash
# hex-32 secrets: POSTGRES_PASSWORD, REDIS_PASSWORD, MINIO_ROOT_PASSWORD, JWT_SECRET
openssl rand -hex 32

# Fernet keys: VAULT_ENCRYPTION_KEY, TOTP_ENCRYPTION_KEY
python3 -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

The Fernet keys are not interchangeable with the hex secrets — the vault and TOTP subsystems will fail closed on startup if either key is missing or malformed. Set `POSTGRES_USER`, `POSTGRES_DB`, `MINIO_ROOT_USER`, `NEXT_PUBLIC_API_URL`, `CORS_ORIGINS`, `DOMAIN_NAME`, and `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_USERNAME` to match your environment, then `docker compose -f docker-compose.prod.yml up -d`.

## Production deployment

The Quick Start above is the production install path — `deploy_server.sh` and `docker-compose.prod.yml` are what runs on real deployments. The Compose file:

- Builds the frontend with `NODE_OPTIONS="--max-old-space-size=2048"` (suitable for a 4 GB VPS)
- Does not expose internal service ports (postgres, redis, minio, mcp) on the host
- Runs Nginx as the public-facing reverse proxy

For an existing install, re-running `./scripts/deploy_server.sh` after `git pull` will apply migrations and rebuild in place.

## Role-based access control

| Role | Capabilities |
|------|--------------|
| Admin | Full system access including user management |
| Team Lead | Create and manage engagements, manage assigned team and findings, generate reports |
| Operator | Create and edit own findings, upload evidence, view assigned engagements |
| Read-Only | View findings and reports without modification |

Permissions are also scoped at the engagement level — a user can have different roles on different engagements.

## Development

### Running locally without Docker

**Backend**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

### Database migrations

```bash
# Create a new migration after model changes
docker compose run --rm backend alembic revision --autogenerate -m "description"

# Apply migrations
docker compose run --rm backend alembic upgrade head

# Rollback one revision
docker compose run --rm backend alembic downgrade -1
```

Migration files follow the convention `YYYY-MM-DD_<revid>_<desc>.py`.

### Common Docker commands

All commands below target the production Compose file (`docker-compose.prod.yml`). For local development with hot-reload, swap `-f docker-compose.prod.yml` for `-f docker-compose.yml` or omit the flag entirely.

```bash
# Start all services
docker compose -f docker-compose.prod.yml up -d

# Follow logs
docker compose -f docker-compose.prod.yml logs -f

# Stop all services
docker compose -f docker-compose.prod.yml down

# Rebuild containers
docker compose -f docker-compose.prod.yml up -d --build

# Remove all data (destroys databases and volumes)
docker compose -f docker-compose.prod.yml down -v
```

## Project structure

```
redwire/
├── backend/                FastAPI application
│   ├── alembic/versions/   Database migrations
│   ├── auth/               JWT, password, TOTP, LDAP, SAML, RBAC
│   ├── models/             SQLAlchemy models
│   ├── schemas/            Pydantic request/response schemas
│   ├── routers/            FastAPI routers
│   ├── utils/              Storage, vault, reports, collaboration
│   └── plugins/            Drop-in backend plugins
├── frontend/               Next.js application
│   └── src/
│       ├── app/            App Router pages
│       ├── components/     React components (shadcn/ui under components/ui)
│       ├── lib/            API client, hooks, types
│       └── stores/         Zustand stores
├── mcp-server/             MCP server (Starlette + SSE)
├── nginx/                  Nginx config and Certbot volumes
├── scripts/                Deploy and operational scripts
├── docker-compose.yml      Development orchestration
├── docker-compose.prod.yml Production orchestration
└── .env.example            Environment template
```

## Security

### Production checklist

- Change the default admin password.
- Generate strong values for `JWT_SECRET` and `VAULT_ENCRYPTION_KEY` (32+ characters).
- Back up `VAULT_ENCRYPTION_KEY` separately from the database.
- Enable HTTPS via the included Nginx + Certbot setup.
- Restrict the host firewall to ports 80 and 443.
- Schedule regular backups of PostgreSQL and MinIO.
- Keep dependencies up to date.
- Review user permissions periodically.

### File uploads

- File type and size validation are enforced (default 50 MB).
- Uploads are stored in MinIO, not on the application filesystem.
- Run an external antivirus scanner against the MinIO bucket for production use.

### Reporting vulnerabilities

See [SECURITY.md](SECURITY.md) for the coordinated disclosure process.

## API documentation

Interactive API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

All endpoints except authentication routes require a JWT bearer token:
```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/engagements
```

## About this project

RedWire is a personal project, primarily vibe-coded with Anthropic's Claude Opus 4.6 and 4.7. The AI assistants did most of the keyboard work; the scoping, design decisions, and review are mine. Model usage and infrastructure are paid for out of pocket.

It is released free because small internal red teams — the kind that have a hardware budget but not budget for a four- or five-figure commercial reporting platform — should not have to choose between an expensive vendor and a shared spreadsheet.

### Donations

If RedWire is useful to you and you would like to help offset ongoing API and hosting costs, open a GitHub issue or discussion to get in touch — a proper donation channel will be set up later. There is no obligation, and the project will remain free regardless.

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/short-description`).
3. Commit changes following Conventional Commits (`feat:`, `fix:`, `security:`, `chore:`).
4. Open a pull request describing the change and any migration impact.

## License

See [LICENSE](LICENSE) for the full license text.
