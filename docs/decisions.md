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

## ADR 007: Python Runtime Compatibility & Version Selection
* **Decision:** Standardize the backend runtime on **Python 3.12** (`Python 3.12.13`).
* **Rationale:**
  * While the host environment also had Python 3.14 pre-release installed, major ecosystem packages (precompiled binary wheels for `asyncpg`, `pydantic-core`, `uvloop`) and ORM tooling are proven stable on Python 3.12.
  * Installed and verified with FastAPI 0.162, SQLAlchemy 2.1.6, Alembic 1.20.1, asyncpg 0.32.0, Pydantic 2.14.1, and pytest 9.2.0 in `apps/api/.venv`.
  * Python 3.11 through 3.13 are permitted by package metadata (`requires-python = ">=3.11,<3.14"`), with 3.12 as the primary tested baseline.
* **Status:** Accepted (Python 3.12 selected and verified).

---

## ADR 008: Dual-Relation Graph Model for Claim Lineage
* **Decision:** Represent both claim replacement (supersession) and causal derivation (dependencies) in a unified directed edge table `claim_relations` with explicit `relation_type` and mandatory human/agent `rationale`.
* **Rationale:**
  * Avoids conflating "revising a claim" with "deriving conclusions from a claim".
  * Allows arbitrary N:M DAG structures while keeping traversal queries indexed and straightforward.
  * Captures the semantic justification for why a newer claim supersedes an older claim.
* **Status:** Accepted.

---

## ADR 009: Non-Destructive Invalidation Semantics (`needs_review`)
* **Decision:** When an upstream claim is superseded, dependent claims and recommendations must transition to `needs_review` rather than being automatically deleted, muted, or marked false.
* **Rationale:**
  * A change in underlying evidence or an upstream claim invalidates the deductive basis of a recommendation, but does not prove the recommendation itself is false or useless.
  * Non-destructive marking preserves auditability, lineage, and enables human-in-the-loop or agentic re-evaluation.
* **Status:** Accepted.

---

## ADR 010: Multi-Tier Memory Scope and Server-Side Isolation
* **Decision:** Implement strict three-tier memory visibility (`private`, `team`, `workspace`) within each tenant workspace, enforced exclusively by the server-side service layer.
* **Rationale:**
  * Prevents private agent observations or reasoning scratchpads from leaking into shared team contexts without explicit promotion.
  * Does not rely on LLM system prompt compliance or client filtering.
  * Pairs application-level repository filtering with foreign keys to `workspace_id` for defense-in-depth across shared database connection pools.
* **Status:** Accepted.

---

## ADR 011: Caller-Bound Agent Identity and Explicit Scope Verification
* **Decision:** Resolve agent caller identity exclusively from verified API authentication tokens (`api_key_hash`), rejecting client-supplied `agent_id` overrides.
* **Rationale:**
  * Prevents agent impersonation where an agent could query private memories of other agents simply by passing their `agent_id`.
  * Guarantees that private scope evaluation `(scope = 'private' AND agent_id = :authenticated_agent_id)` is tamper-proof.
* **Status:** Accepted.

---

## ADR 012: Composite Workspace Integrity for Inter-Claim Edges
* **Decision:** Enforce composite foreign keys `(workspace_id, source_claim_id)` and `(workspace_id, target_claim_id)` on `claim_relations` referencing `claims(workspace_id, id)`.
* **Rationale:**
  * Prevents cross-workspace data corruption where a claim in Workspace A could inadvertently supersede or depend on a claim in Workspace B.
  * Guarantees tenant isolation at the relational schema level.
* **Status:** Accepted.

---

## ADR 013: Append-Only Immutability for Audit Trail
* **Decision:** Enforce append-only immutability on `audit_events` via PostgreSQL privilege revocation (`REVOKE UPDATE, DELETE`) and a database trigger preventing mutations.
* **Rationale:**
  * Memory governance requires a non-repudiable history of supersessions, invalidations, and access denials.
  * Prevents compromised application services from tampering with historic audit logs.
* **Status:** Accepted.

