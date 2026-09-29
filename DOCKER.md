# Docker

This project ships with **Docker Compose profiles**. Both are **non-production**:

| Profile | Purpose | Frontend | Backend |
|---|---|---|---|
| `dev` | Day-to-day development | Vite (hot reload) | uvicorn `--reload` + source mounts |
| `qa` | QA / pre-release testing | nginx (built SPA) | uvicorn workers, no source mounts |

There is **no production profile** in this setup.

## Prerequisites

- Docker Desktop installed and running
- Free ports: `5173` (UI), `8001` (API)
- Dev publishes PostgreSQL on `5433`; QA uses `5434` by default (see env files)

## 1. Create env files

```bash
cp .env.dev.example .env.dev
cp .env.qa.example  .env.qa
```

Edit secrets if you want (`JWT_SECRET`, `DB_PASSWORD`, `FIRECRAWL_API_KEY`).

## 2. Start DEV

```bash
docker compose -p tender-dev --env-file .env.dev --profile dev up --build
```

- UI: http://localhost:5173
- API: http://localhost:8001/docs
- Login: `admin` / `AdminPass12345`

Code under `tender-backend/app` and `tender-frontend/src` reloads automatically.

## 3. Start QA

```bash
docker compose -p tender-qa --env-file .env.qa --profile qa up --build
```

Same default URLs. Use a different `-p` project name so QA does not share the DEV database volume.

## 3b. QA on a VM with an existing PostgreSQL

When the database already exists (created by a DBA), point `.env.qa` at it:

```
DB_HOST=<db server IP>          # Postgres on the same VM: host.docker.internal
DB_PORT=5432
DB_USER=<db user>
DB_PASSWORD=<db password>
DB_NAME=tender_fetching
```

Set the public URLs too (the API URL is baked into the frontend at build time):

```
VITE_API_BASE_URL=http://<vm-ip-or-domain>:8001
CORS_ORIGINS=http://<vm-ip-or-domain>:5173
JWT_SECRET=<long random string>
```

Start only the app containers (`--no-deps` skips the bundled `db`):

```bash
docker compose -p tender-qa --env-file .env.qa --profile qa up -d --build --no-deps backend-qa frontend-qa
```

The backend runs migrations and seeds on start, so the database only needs to exist and be owned by `DB_USER`.

If Postgres runs directly on the VM (not in Docker), it must accept connections from the Docker network: `listen_addresses = '*'` in `postgresql.conf` and a `host all all 172.16.0.0/12 scram-sha-256` line in `pg_hba.conf`.

## 4. Stop

```bash
docker compose -p tender-dev --profile dev down
docker compose -p tender-qa  --profile qa  down
```

Add `-v` to also delete the PostgreSQL volume.

## What runs inside

| Service | Image / role |
|---|---|
| `db` | PostgreSQL 16 |
| `backend-dev` / `backend-qa` | FastAPI (migrate + optional seed on start) |
| `frontend-dev` | Vite |
| `frontend-qa` | nginx serving the built SPA |

## Notes for your instructor

- Profiles are activated with `--profile dev` or `--profile qa`.
- Env files drive ports, DB password, JWT, CORS, and `ENVIRONMENT`.
- Backend entrypoint waits for PostgreSQL, runs `alembic upgrade head`, then seeds admin/reference data when `RUN_SEEDS=true`.

If the second profile should be named something else (for example `staging`), rename `dev` in `docker-compose.yml` and the `.env.*.example` files.
