# Filament Architecture & Data Flow

Filament governs agent memory with strict provenance tracking, ensuring that every memory unit is tagged with its origin, contextual lineage, and policy constraints before it can be read, written, or shared.

---

## Core System Flow

The primary data flow follows a tiered, unidirectional pipeline:

```text
┌─────────────────────────────────┐
│     React Client (apps/web)     │
│   (Visual Dashboards & Admin)   │
└────────────────┬────────────────┘
                 │ HTTP / JSON
                 ▼
┌─────────────────────────────────┐
│     FastAPI Routes (apps/api)   │
│   - Route handlers              │
│   - Request validation (Pydantic│
│   - Auth token validation       │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│      Validated Service Layer    │
│   - Provenance tracking logic   │
│   - Server-side policy checks   │
│   - Memory governance engine    │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│   SQLAlchemy 2.x Persistence    │
│   - Async Unit of Work          │
│   - Strong typing & relations   │
└────────────────┬────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│      PostgreSQL (Supabase)      │
│   - Relational tables           │
│   - Vector extensions (planned) │
│   - Audit logs & lineage graph  │
└─────────────────────────────────┘
```

---

## Core Principles

### 1. Server-Side Enforcement (Non-Delegated Governance)
* **No Client Trust:** The frontend client (`apps/web`) is treated as untrusted. No authorization, scope validation, or memory lifecycle checks may rely on client assertions.
* **No LLM Trust:** Memory governance decisions—such as whether a memory fragment may be retrieved, mutated, purged, or exposed—must **never** be delegated to the language model or prompt instructions. All access policies, taint checks, and redactions are strictly evaluated within the validated service layer on the server before inputs reach the model or before responses return to the caller.

### 2. Provenance as a First-Class Primitive
* Every memory element stored in Filament must capture its provenance metadata:
  * Originator (agent ID, user identity, system component)
  * Ingestion timestamp and interaction context
  * Cryptographic or structural lineage (parent memory references, transformations, synthesis steps)
  * Classification level and retention policies

### 3. Layered Isolation
* **Route Layer:** Responsible solely for protocol negotiation, deserialization, rate limiting, and transport status codes.
* **Service Layer:** Houses all business rules, provenance graph management, and governance policies.
* **Persistence Layer:** Manages relational consistency, transaction isolation, and database migrations via SQLAlchemy 2.x and Alembic.

