# Architecture Decision Records (ADRs)

This document records the foundational architectural decisions for Filament, their rationale, and their current status.

---

## ADR 001: Backend Framework — FastAPI
* **Decision:** Use FastAPI for the core REST API backend.
* **Rationale:**
  * High-performance asynchronous request handling.
  * Native integration with Pydantic for strong request and response contract validation.
  * Automatic OpenAPI schema generation for synchronization with frontend contracts.
  * Clean dependency injection patterns for database sessions and authentication services.
* **Status:** Accepted.

---

## ADR 002: Frontend Framework — React + TypeScript + Vite
* **Decision:** Build the management and provenance inspection UI using React, TypeScript, and Vite in `apps/web`.
* **Rationale:**
  * Vite provides fast local development cycles and optimized production bundling.
  * TypeScript provides type safety aligned with schemas exported from the backend.
  * Mature ecosystem of visualization libraries for displaying lineage graphs and audit logs.
* **Status:** Accepted (scaffolding deferred to subsequent stages).

---

## ADR 003: Persistence & Database — Supabase PostgreSQL
* **Decision:** Target PostgreSQL as the primary persistence layer, utilizing Supabase for managed deployments and local PostgreSQL for development.
* **Rationale:**
  * Robust ACID compliance and relational integrity, critical for audit trails and lineage tracking.
  * Native support for JSONB, relational graphs, and `pgvector` for vector embeddings if needed in future memory retrieval stages.
  * Broad ecosystem compatibility and ease of deployment.
* **Status:** Accepted.

---

## ADR 004: ORM & Migrations — SQLAlchemy 2.x and Alembic
* **Decision:** Use SQLAlchemy 2.0 (with async driver support) and Alembic for database modeling and schema migrations.
* **Rationale:**
  * SQLAlchemy 2.x introduces strong typing, modern declarative models, and clean async support (`asyncpg`).
  * Alembic provides deterministic, auditable, and reversible schema migration management.
* **Status:** Accepted.

---

## ADR 005: Communication Protocol — REST/JSON with Strict Schema Validation
* **Decision:** Use REST over HTTP with JSON payloads, enforced by strict request and response schemas.
* **Rationale:**
  * Simple, universally understood protocol with broad client support.
  * Enforces boundary validation: input payloads are validated before reaching the service layer; response payloads are sanitized to prevent data leakage.
* **Status:** Accepted.

---

## ADR 006: Testing Framework — pytest
* **Decision:** Use `pytest` (with `pytest-asyncio` and `httpx`) for backend test suites.
* **Rationale:**
  * De facto standard for Python testing with extensive plugin ecosystem.
  * Expressive fixture model for setting up isolated test databases and mock agent interactions.
* **Status:** Accepted.

---

## ADR 007: Python Runtime Compatibility (Provisional)
* **Decision:** The supported Python version remains **provisional** pending ecosystem compatibility testing.
* **Rationale:**
  * The local development machine has Python 3.14 installed.
  * Several core dependencies in the Python data and web ecosystem (e.g., binary wheels for async database drivers, ORM extensions, or validation libraries) may have limited or pre-release support on Python 3.14.
  * Before locking the project's supported Python version (e.g., Python 3.11, 3.12, or 3.13 vs 3.14), library compatibility must be explicitly verified.
* **Status:** Provisional (requires compatibility verification before pinning environment).

