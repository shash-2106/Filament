# Filament — Governed Agent Memory & Environmental Provenance Platform

Filament is an immutable, provenance-aware memory governance platform for autonomous AI coding agents and development teams. It binds agent memories, architectural decisions, and operational constraints to verifiable environmental prerequisites—evaluating memory validity deterministically against repository snapshots, package lockfiles, and runtime configurations to prevent silent hallucination and drift.

---

## Key Capabilities

1. **Environmental Validity Requirements & Drift Detection:**
   - Memories are not static text blobs; they carry versioned condition sets (`file_hash`, `lockfile_hash`, `package_version`, `runtime_fact`).
   - Deterministic evaluation engine tests claims against immutable environment snapshots (`applicable` vs `environment_mismatch`).
   - Distinguishes breaking implementation refactors from benign changes (such as README edits).

2. **Immutable Provenance & Evidence Ingestion:**
   - Every claim links to verifiable evidence records with exact substrings, source URIs (`file`, `git_commit`, `tool_output`), and cryptographic digests.
   - Preserves complete derivation chains across memory revisions and supersessions.

3. **Autonomous Memory Extraction (Meta Muse Spark 1.3):**
   - Ingests multi-turn agent conversation transcripts and extracts structured candidate memories with bounded outputs.
   - Built-in fail-closed spending ledger, per-request budget reservations, and pre-flight token/cost estimation.
   - Human-in-the-loop review stepper allows refining and approving candidates before persistence.
   - Includes graceful zero-dependency simulation fallback when model gateways are in standby.

4. **Multi-Tenant Security & Row-Level Isolation:**
   - Strict workspace boundary isolation with composite primary/foreign keys across PostgreSQL / Supabase.
   - Immutable audit logging with append-only database triggers.

5. **Neural Graphite Visual Interface:**
   - Tailored developer intelligence workstation styling (`#0B1210` obsidian canvas, elevated `#14231D` panels, phosphor green `#7FDD9D` accents).
   - Interactive memory graph, live inspection drawer, and step-by-step extraction workflows.

---

## Monorepo Architecture

```text
Filament/
├── apps/
│   ├── api/                 # FastAPI asynchronous backend (Python 3.12 + SQLAlchemy 2.x)
│   │   ├── src/filament_api/
│   │   │   ├── api/routes/  # Endpoints: claims, evidence, snapshots, extraction, audit
│   │   │   ├── models/      # Relational domain models (PostgreSQL / Supabase)
│   │   │   ├── services/    # Business logic, condition evaluation, Meta API gateway
│   │   │   └── schemas/     # Pydantic DTO contracts and validation models
│   │   └── tests/           # Full pytest regression suite
│   └── web/                 # React 19 + TypeScript + Vite + Tailwind CSS workstation
│       ├── src/
│       │   ├── api/         # Typed API client and React Query hooks
│       │   ├── components/  # Drawer inspection, modal steppers, network graph
│       │   └── pages/       # Memories, Evidence, DAG Connections, Activity, Guide
│       └── test/            # Vitest unit test suite
├── packages/
│   └── contracts/           # Shared API schema specifications
├── start_backend.sh         # Production/dev launch script configuring Supabase connection pooler
├── pytest.ini               # Backend test runner configuration
└── README.md                # System overview and runbook
```

---

## Technology Stack

* **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.x (asyncpg), Alembic, Pydantic v2.
* **Frontend:** React 19, TypeScript, Vite, Tailwind CSS, Lucide icons, TanStack React Query.
* **Database & Ledger:** Supabase PostgreSQL with pooler connection management and cryptographic audit trails.
* **Model Inference:** Meta Muse Spark 1.3 Standard with automated spending ledger guardrails.
* **Testing:** Pytest (asyncio), Vitest (React Testing Library), Playwright.

---

## Quickstart & Local Setup

### 1. Prerequisites
- Python 3.12+
- Node.js 18+ (Node 20+ recommended)
- Supabase or PostgreSQL database instance

### 2. Environment Configuration
Copy `.env.example` to `.env` or set your environment variables:
```bash
# Database Configuration (Supabase pooler or local PostgreSQL)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/filament_dev
SUPABASE_DB_PASSWORD=your_password_here
SUPABASE_PROJECT_REF=your_project_ref_here

# Meta Model Gateway (Optional / Standby for extraction)
MODEL_API_ENABLED=true
MODEL_API_KEY=your_key_here
MODEL_API_MAX_OUTPUT_TOKENS=3000
```

### 3. Start the Backend API
Use the provided startup script which automatically constructs the asyncpg pooler URL:
```bash
./start_backend.sh
```
*API will run at `http://127.0.0.1:8000` (docs available at `/docs`).*

### 4. Start the Web Frontend
In another terminal session:
```bash
cd apps/web
npm install
npm run dev
```
*Web dashboard will run at `http://localhost:5173`.*

---

## Running Test Suites

### Backend Tests
```bash
cd apps/api
.venv/bin/pytest tests/ -v
```

### Frontend Tests & Typecheck
```bash
cd apps/web
npm test          # Vitest suite
npm run build     # TypeScript check and Vite production bundle
```

---

## Verified Demo Workflow

1. **Inspect Governed Memory:**
   - Open `/memory` in the browser.
   - Click **Inspect** on `redis.connection_pool` to view statement confidence, scope, and provenance.
2. **Audit Environmental Drift:**
   - Under **Validity Requirements & Evaluation**, select `git:main:baseline_config` and click **Evaluate Against Snapshot** -> **`OUTCOME: APPLICABLE`**.
   - Switch snapshot to `git:main:refactor_redis_pool` and re-evaluate -> **`OUTCOME: ENVIRONMENT MISMATCH`** (detects code drift in `src/services/redis_client.py`).
   - Switch snapshot to `git:main:readme_typo_fix` -> **`OUTCOME: APPLICABLE`** (demonstrates technical stability despite documentation edits).
3. **Extract from Conversation (Muse Spark 1.3):**
   - Click **Extract with Muse Spark** on `/memory`.
   - Paste transcript text -> Click **Calculate Tokens & Cost Preview** to view worst-case cost estimates under global caps.
   - Click **Confirm & Extract** -> Review extracted structured candidate claims and supporting evidence excerpts before committing.

---

## License

Apache-2.0
