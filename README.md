# Filament

Filament is a provenance-aware memory governance system for AI agents. It provides fine-grained tracking, verification, and server-side policy enforcement over an agent's memory lifecycle, ensuring that data origins, contextual lineage, and access permissions remain auditable and constrained across interactions.

> [!NOTE]
> This repository is in the foundational setup stage. Core application logic, database schemas, and client scaffolds are planned and not yet implemented.

---

## Intended Architecture & Stack

* **Backend (`apps/api`):** Python with FastAPI, SQLAlchemy 2.x, Alembic migrations, and pytest.
* **Frontend (`apps/web`):** React, TypeScript, and Vite.
* **Contracts (`packages/contracts`):** API schemas, contracts, and type definitions shared across services.
* **Database & Persistence:** PostgreSQL via Supabase (managed) or standard local PostgreSQL for development.
* **Governance Model:** Server-side policy evaluation ensuring memory read/write boundaries cannot be bypassed by clients or LLM prompt manipulation.

---

## Monorepo Layout

```text
Filament/
├── apps/
│   ├── api/                 # Python FastAPI backend service
│   └── web/                 # React + TypeScript + Vite frontend application
├── packages/
│   └── contracts/           # API contracts and schema definitions
├── docs/
│   ├── architecture.md      # System data flow and security principles
│   └── decisions.md         # Architecture Decision Records (ADRs) and runtime notes
├── .env.example             # Template for local environment variables
├── .gitignore               # Root git ignore specification
└── README.md                # Project overview and roadmap
```

---

## Planned Development Stages

All features listed below reflect planned capabilities and are **not yet implemented**:

* **Stage 1 (Current):** Foundation setup, monorepo scaffolding, configuration templates, and architecture documentation.
* **Stage 2 (Planned):** Python runtime verification, virtual environment setup, and baseline dependency selection.
* **Stage 3 (Planned):** Database connection, Alembic setup, and core provenance schema modeling (Agents, Memories, Provenance Records, Access Policies).
* **Stage 4 (Planned):** Backend domain services and FastAPI endpoints for memory ingestion, lineage tracking, and policy enforcement.
* **Stage 5 (Planned):** Web frontend dashboard for visual provenance exploration and memory governance control.
* **Stage 6 (Planned):** Agent SDK / client library integration and end-to-end audit pipelines.

---

## Python Compatibility Notice

During local environment reconnaissance, Python 3.14 was identified on the host system. Because major third-party libraries in the Python ecosystem (such as specific async database drivers, ORM extensions, or Pydantic binary wheels) may not yet publish stable wheels for Python 3.14, **the supported Python version for Filament is marked as provisional**. Dependency compatibility across prospective runtime versions (e.g., Python 3.11, 3.12, or 3.13) will be validated before locking dependencies in `apps/api`.

