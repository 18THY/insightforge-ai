# InsightForge AI

An AI-powered Business Intelligence platform. See `AGENTS.md` for project
rules, architecture principles, and the development workflow, and
`docs/architecture.md` for the system design.

> **Status:** Phase 1 — project foundation only. No authentication,
> analytics, dashboards, or AI features are implemented yet.

---

## Project structure

```
insightforge-ai/
├── frontend/     Next.js + TypeScript + Tailwind CSS application
├── backend/      FastAPI application
├── data/         Local data directory (git-ignored contents)
├── docs/         Project documentation
├── scripts/      Utility/dev scripts
├── docker-compose.yml
├── .env.example
└── AGENTS.md
```

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose
  (recommended — runs everything with no local Node/Python setup), **or**
- Node.js 20+ and npm, for running the frontend directly
- Python 3.12+, for running the backend directly
- PostgreSQL 16, if not using Docker for the database

---

## Environment configuration

All configuration is provided via environment variables. No secrets are
hardcoded anywhere in the codebase.

```bash
cp .env.example .env
```

Then adjust values in `.env` as needed. `.env` is git-ignored and must
never be committed.

---

## Option A — Run everything with Docker Compose (recommended)

```bash
cp .env.example .env
docker compose up --build
```

This starts:

| Service  | URL                     |
|----------|--------------------------|
| Frontend | http://localhost:3000    |
| Backend  | http://localhost:8000    |
| Database | localhost:5432 (Postgres)|

Verify the backend is healthy:

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"InsightForge AI"}
```

Stop everything with `docker compose down` (add `-v` to also remove the
Postgres data volume).

---

## Option B — Run services directly (without Docker)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

The backend reads configuration from `.env` at the repository root (or
its own `backend/.env`, if present) and defaults to sensible local values
if none is set.

Run backend tests:

```bash
cd backend
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend reads `NEXT_PUBLIC_API_URL` to know where to reach the
backend (defaults to `http://localhost:8000`).

---

## Verifying the setup

1. Open http://localhost:3000 — you should see the InsightForge AI shell
   page with a "Backend status" indicator.
2. The indicator should turn **online** once the backend is reachable.
3. `curl http://localhost:8000/health` should return:

   ```json
   {"status": "ok", "service": "InsightForge AI"}
   ```

---

## Development workflow

This project is built incrementally, one phase at a time, following the
rules in `AGENTS.md`. Please read that file before contributing — it
covers architecture principles, security rules, coding standards, and how
changes are expected to be scoped and reviewed.
