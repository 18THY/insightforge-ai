# InsightForge AI — Architecture

This document describes the intended technical architecture of the system:
its layers, how they interact, and how each of the platform's capabilities
maps onto the stack. It is a design reference; the authoritative rules
governing *how* the system must be built live in `AGENTS.md`.

> Status: architecture reference only. No application code has been
> implemented yet — this describes the target design that later phases
> will build toward incrementally.

---

## 1. System Overview

InsightForge AI is a multi-tenant (organization-scoped) Business
Intelligence platform composed of six independently responsible layers:

```
┌─────────────────────────────────────────────────────────────────┐
│                           Frontend                                │
│         Next.js · TypeScript · Tailwind · shadcn/ui · ECharts     │
│         (renders state, calls backend APIs, no business logic)    │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ HTTPS / typed JSON (OpenAPI schema)
┌───────────────────────────────▼───────────────────────────────────┐
│                            Backend                                 │
│            FastAPI · SQLAlchemy · Alembic · Pydantic                │
│   (auth, org isolation, business logic, API surface, orchestration) │
└───────┬───────────────┬────────────────┬───────────────┬──────────┘
        │               │                │               │
┌───────▼──────┐ ┌──────▼───────┐ ┌──────▼───────┐ ┌─────▼───────────┐
│   Database    │ │  Analytics   │ │      AI      │ │   Audit / Log    │
│ PostgreSQL +  │ │ Pandas/NumPy │ │ Gemini API   │ │  storage (via     │
│  pgvector     │ │ DuckDB/SciPy │ │ tool calling,│ │  backend, in      │
│               │ │ scikit-learn │ │ structured   │ │  PostgreSQL)      │
│               │ │ XGBoost (opt)│ │ outputs, RAG │ │                   │
└───────────────┘ └──────────────┘ └──────────────┘ └───────────────────┘
```

Key rule: **the frontend and the AI layer never access PostgreSQL
directly.** All data access is mediated by backend services (Principle 4,
7, 8, 9 in `AGENTS.md`).

---

## 2. Layer Responsibilities

### 2.1 Frontend (Next.js / TypeScript)
- Renders dashboards, upload flows, chat-style Q&A, and report views.
- Calls backend REST/JSON APIs using generated or hand-written TypeScript
  types matching backend Pydantic schemas.
- Owns presentation state only (loading, filters, chart config). Owns no
  business rules, no direct data access, no secrets.
- Uses Apache ECharts for all charting; shadcn/ui + Tailwind for UI
  primitives and layout.

### 2.2 Backend (FastAPI / SQLAlchemy / Alembic / Pydantic)
- Single entry point for all client and AI interactions with data.
- Responsibilities:
  - Authentication, authorization, and organization-scoping on every
    request.
  - Typed request/response contracts (Pydantic) for every endpoint.
  - Orchestration of analytics, ML, and AI calls — the backend decides
    *when* and *how* those layers are invoked; they are never called
    directly by the frontend.
  - Validation and sandboxing of AI-generated SQL before execution.
  - Writing audit log entries for security- and data-relevant actions.
- Schema evolution is managed exclusively through Alembic migrations.

### 2.3 Database (PostgreSQL + pgvector)
- System of record for business data, users/roles, KPIs, audit logs, and
  vector embeddings (via pgvector) used for RAG document search.
- Organization isolation is enforced at the query layer in the backend
  (e.g., mandatory `org_id` scoping), backed by schema constraints.
- The AI layer is never granted direct database credentials; any
  AI-influenced query is executed by the backend under a constrained,
  least-privilege, read-only path for AI-originated SQL.

### 2.4 Analytics (Pandas / NumPy / DuckDB / SciPy / scikit-learn / XGBoost)
- Used by backend services for: data profiling and cleaning, KPI
  computation, anomaly detection, forecasting, and statistical root-cause
  analysis.
- DuckDB is used where in-process analytical querying over
  tabular/dataframe data is more efficient than round-tripping through
  PostgreSQL.
- scikit-learn covers standard statistical/ML methods (e.g., anomaly
  detection, baseline forecasting models); XGBoost is introduced only
  where a concrete accuracy or capability need justifies the added
  dependency (Principle 17).
- Analytics outputs are structured data (numbers, series, model outputs)
  — never free text — so they can be safely handed to the AI layer as
  grounded evidence.

### 2.5 AI (Gemini API)
- Used for: natural-language question understanding, NL-to-SQL
  generation, RAG-based document search and synthesis, and generation of
  evidence-backed narrative reports.
- Interacts with the rest of the system only through backend-defined
  tools/functions (function/tool calling) and structured outputs — never
  via direct database or filesystem access.
- Every AI-generated conclusion must cite the specific tool result,
  query result, or document chunk it is based on (Principle 13). Outputs
  are validated against expected schemas before use (Principle 11).
- Embeddings (for RAG) are generated via the Gemini API and stored in
  PostgreSQL via pgvector.

### 2.6 Audit / Logging
- Cross-cutting concern owned by the backend: important operations
  (uploads, schema changes, AI SQL execution, report generation, user/role
  management, authentication events) are written to an audit log table in
  PostgreSQL.
- Audit records are structured (who, what, when, org, outcome) and are
  themselves subject to organization-scoped access control.

---

## 3. Data Flow Patterns

### 3.1 Structured data flow (dataset upload → dashboard)
```
User uploads dataset (frontend)
  → Backend validates file, stores raw + profiled data (PostgreSQL)
  → Backend/analytics layer profiles, cleans, computes KPIs
  → Frontend requests dashboard data via typed API
  → Backend returns computed results
  → Frontend renders with ECharts
```

### 3.2 Natural-language question → answer
```
User asks a question in natural language (frontend)
  → Backend sends question + schema/context to Gemini API (tool calling)
  → Gemini proposes a SQL query (structured output)
  → Backend validates SQL: read-only, allow-listed, org-scoped
  → Backend executes validated SQL against PostgreSQL
  → Backend returns results to Gemini (as tool result) for narration,
    or directly to the frontend as data
  → Frontend renders answer + supporting data, with traceability back
    to the executed query
```

### 3.3 Document RAG flow
```
User uploads business document (frontend)
  → Backend extracts text, chunks it, requests embeddings (Gemini API)
  → Backend stores chunks + embeddings (PostgreSQL/pgvector), org-scoped
  → User asks a question
  → Backend performs vector similarity search (pgvector), org-scoped
  → Backend sends retrieved chunks + question to Gemini API
  → Gemini generates an answer grounded in retrieved chunks
  → Backend validates response, returns to frontend with citations
```

### 3.4 Evidence-backed report generation
```
Backend gathers: KPI results, anomaly/forecast outputs, relevant document
chunks (RAG) — all already computed/retrieved and org-scoped
  → Backend sends this evidence bundle to Gemini API with structured
    output constraints
  → Gemini generates report content that references only the supplied
    evidence
  → Backend validates the structured output (no invented figures,
    citations map to supplied evidence)
  → Report is stored/returned, with audit log entry
```

---

## 4. Capability-to-Layer Mapping

| # | Capability | Primary layer(s) |
|---|---|---|
| 1 | Upload business datasets | Frontend, Backend |
| 2 | Profile and clean data | Backend, Analytics |
| 3 | Store and query business data | Backend, PostgreSQL |
| 4 | Calculate business KPIs | Backend, Analytics |
| 5 | Interactive analytics dashboards | Frontend (ECharts), Backend |
| 6 | Natural-language questions | Backend, AI |
| 7 | NL-to-safe-SQL | Backend, AI (with validation layer) |
| 8 | Anomaly detection | Analytics (scikit-learn) |
| 9 | Forecasting | Analytics (scikit-learn/XGBoost) |
| 10 | Root-cause analysis | Analytics + AI (evidence-grounded) |
| 11 | Upload business documents | Frontend, Backend |
| 12 | RAG document search | Backend, PostgreSQL/pgvector, AI |
| 13 | Evidence-backed reports | Backend, AI, Analytics |
| 14 | User and role management | Backend, PostgreSQL |
| 15 | Audit logs | Backend, PostgreSQL |
| 16 | Automated tests | All layers (test suites per layer) |
| 17 | Docker / CI/CD deployment | Infrastructure (Docker, Docker Compose, GitHub Actions) |

---

## 5. Multi-Tenancy & Isolation

- Every persisted business entity (datasets, KPIs, documents, embeddings,
  reports, audit entries) is associated with an `organization_id`.
- Backend data-access functions require and enforce organization scope;
  there is no code path where a query executes without it.
- AI-generated SQL is additionally constrained to the requesting
  organization's data before execution, independent of what the model
  itself proposes.

---

## 6. Deployment Architecture (target)

- **Docker**: each service (frontend, backend, database) is containerized
  independently.
- **Docker Compose**: local development and integration environment,
  wiring frontend, backend, and PostgreSQL (with pgvector) together.
- **GitHub Actions**: CI pipeline runs automated tests and checks on
  every change; CD pipeline (once defined) handles build/publish/deploy
  steps.

Concrete Compose/CI configuration will be introduced in the relevant
later phase, per the incremental development workflow in `AGENTS.md`.

---

## 7. Open Design Questions (to resolve in later phases)

These are intentionally left undecided at this stage, to be addressed
when their corresponding phase is implemented:

- Exact authentication mechanism (e.g., session vs. JWT) and provider.
- Precise SQL validation strategy for AI-generated queries (e.g.,
  AST-based allow-listing approach).
- Forecasting/anomaly-detection model choices per metric type.
- Report output format(s) (e.g., in-app only vs. exportable documents).

Resolving these prematurely would violate Principle 18 (prefer simple
architecture over premature complexity) and Principle 19 (do not silently
change architecture decisions).
