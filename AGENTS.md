# AGENTS.md

This file is the binding contract for anyone — human or AI — contributing to
**InsightForge AI**. It defines what the project is, how it must be built,
what is never allowed, and the workflow every change must follow. If a
request conflicts with this file, this file wins unless the project owner
explicitly amends it.

---

## 1. Project Mission

InsightForge AI is a production-style, AI-powered Business Intelligence
platform. Authenticated users and organizations can:

1. Upload business datasets.
2. Profile and clean data.
3. Store and query business data using PostgreSQL.
4. Calculate business KPIs.
5. Explore interactive analytics dashboards.
6. Ask questions about business data using natural language.
7. Convert natural-language questions into safe, validated SQL.
8. Detect anomalies.
9. Forecast business metrics.
10. Perform evidence-backed root-cause analysis.
11. Upload business documents.
12. Search documents using RAG.
13. Generate evidence-backed business reports.
14. Manage users and roles.
15. Maintain audit logs.
16. Run automated tests.
17. Deploy using Docker and CI/CD.

---

## 2. Tech Stack

**Frontend**
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- Apache ECharts

**Backend**
- Python
- FastAPI
- SQLAlchemy
- Alembic
- Pydantic

**Database**
- PostgreSQL
- pgvector

**Analytics**
- Pandas
- NumPy
- DuckDB where useful
- SciPy where useful
- scikit-learn
- XGBoost only where justified

**AI**
- Gemini API
- Function/tool calling
- Structured outputs
- Embeddings
- RAG

**Infrastructure**
- Docker
- Docker Compose
- GitHub Actions

No dependency outside this list may be introduced without explicit
justification and approval (see Principle 17).

---

## 3. Architecture Principles

1. Separate frontend, backend, database, analytics, ML, and AI
   responsibilities. Each layer has a single, clear job.
2. Never put business logic inside frontend components. The frontend
   renders state and calls backend APIs; it does not decide business rules.
3. Never expose secrets in frontend code. API keys, credentials, and
   connection strings live server-side only (environment variables /
   secret stores), never in client bundles or committed files.
4. All database access happens through backend services. The frontend and
   the AI layer never talk to PostgreSQL directly.
5. Use typed request and response schemas (Pydantic on the backend,
   TypeScript types on the frontend) for every API boundary.
6. Use Alembic for all database migrations. No manual, untracked schema
   changes.
7. Never allow the LLM unrestricted database access. The LLM interacts
   with data only through constrained tools/services.
8. AI-generated SQL must be validated before execution — parsed, checked
   against an allow-list of operations and tables/columns, and scoped to
   the requesting organization.
9. AI-generated SQL must be read-only. No INSERT, UPDATE, DELETE, DDL, or
   multi-statement execution is ever permitted from AI-generated queries.
10. Enforce organization-level data isolation at the data-access layer,
    not just in the UI. Every query is scoped by organization.
11. Validate AI outputs (structured-output schemas, tool-call arguments,
    generated SQL, generated report content) before they are used or shown.
12. Never invent numerical results. All numbers presented to users must
    come from actual computation or retrieval, never from LLM guesswork.
13. AI conclusions must be traceable to retrieved data or tool results.
    Every claim in an AI-generated analysis or report should be
    attributable to a specific query result, document chunk, or
    computation.
14. Add logging and audit trails for important operations (data uploads,
    schema/config changes, AI-generated SQL execution, report generation,
    user/role management, authentication events).
15. Write automated tests for backend services, data-validation logic,
    SQL-safety checks, and critical frontend behavior.
16. Keep code maintainable and understandable. Prefer clarity over
    cleverness.
17. Avoid unnecessary dependencies. Justify any addition to the tech
    stack before introducing it.
18. Prefer simple architecture over premature complexity. Do not build for
    hypothetical future scale at the cost of present clarity.
19. Do not silently change architecture decisions. Any deviation from this
    file must be explained and agreed upon before implementation.
20. Implement only what is actually requested. Do not add features, files,
    or scaffolding beyond the current phase's scope.

---

## 4. Security Rules

- All authenticated endpoints must verify identity and organization
  membership before returning or mutating data.
- Organization-level isolation is enforced in the backend data-access
  layer (e.g., mandatory org_id filtering), not assumed from client input.
- Secrets (Gemini API keys, database credentials, JWT signing keys) are
  read from environment variables / a secret manager and are never
  committed to the repository or shipped to the frontend.
- AI-generated SQL is treated as untrusted input: it is parsed and
  validated (read-only, allow-listed tables/columns, org-scoped) before
  execution, and executed with a least-privilege database role.
- File uploads (datasets, documents) are validated for type/size and
  handled defensively before processing.
- All security-relevant actions (auth events, role changes, data exports,
  AI SQL execution) are captured in the audit log.

---

## 5. Coding Standards

- Backend: Python, typed with Pydantic models at every API boundary;
  FastAPI routers organized by domain; SQLAlchemy models separated from
  API schemas; Alembic migrations for every schema change.
- Frontend: TypeScript throughout; Tailwind CSS + shadcn/ui for UI;
  Apache ECharts for data visualization; no business logic in components.
- Naming, structure, and formatting should follow established
  conventions for each ecosystem (PEP 8 / typed Python; standard
  Next.js/TypeScript project conventions).
- Every new module of non-trivial logic should have corresponding
  automated tests.
- Code should be understandable without requiring the original author's
  explanation — favor explicit, readable code over implicit magic.

---

## 6. Development Workflow

This project is built **incrementally, one phase at a time**. The entire
application is never generated at once.

For each phase:

1. **Inspect** the existing repository state before making changes.
2. **Explain** what is about to change and why.
3. **Show** the files expected to be created or modified.
4. **Implement** only the requested phase — nothing beyond its scope.
5. **Run** relevant tests/checks for the change made.
6. **Report** the result clearly.
7. **Stop** and wait for direction before proceeding to the next phase.

No phase should assume or silently start the next one.

---

## 7. Change Control

- This file (`AGENTS.md`) and `docs/architecture.md` are the source of
  truth for project rules and system design.
- Any change to architecture, stack, or principles must be reflected here
  explicitly — never introduced implicitly through code.
