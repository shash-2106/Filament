# Filament Domain Service Layer Design

This document specifies the architecture, interfaces, validation rules, transactional boundaries, and error handling for the **Filament Domain Service Layer**.

---

## 1. Overview & Architectural Role

Filament serves as the governance, provenance, and validity layer for multi-agent and multi-application systems. The **Domain Service Layer** sits between transport adapters (FastAPI routes) and the persistence layer (SQLAlchemy 2.x / PostgreSQL), enforcing all business logic, authorization invariants, and auditability guarantees.

```text
┌────────────────────────────────────────────────────────┐
│           Transport Layer (FastAPI Routes)            │
│  - Parses HTTP requests & extracts bearer tokens       │
│  - Resolves verified Actor & Tenant identity           │
│  - Builds TrustedContext (untrusted client data purged)│
└──────────────────────────┬─────────────────────────────┘
                           │ TrustedContext + DTOs
                           ▼
┌────────────────────────────────────────────────────────┐
│              Domain Service Layer (Services)           │
│  - EvidenceService, ClaimService, AuditService         │
│  - Enforces workspace isolation & scope visibility     │
│  - Validates confidence scores, support polarity & DAG │
│  - Assembles atomic mutations + AuditEvents            │
└──────────────────────────┬─────────────────────────────┘
                           │ SQLAlchemy AsyncSession (Unit of Work)
                           ▼
┌────────────────────────────────────────────────────────┐
│             Persistence Layer (PostgreSQL)             │
│  - Foreign keys, composite workspace constraints       │
│  - Append-only trigger on audit_events                 │
└────────────────────────────────────────────────────────┘
```

---

## 2. Security Boundary: The `TrustedContext`

### 2.1 The Problem of Untrusted Client Input
In multi-agent environments, agents and client applications cannot be trusted to self-report their `workspace_id` or `agent_id`. If services relied on raw request bodies:
1. A rogue or compromised agent could submit observations attributing them to a privileged system agent.
2. An agent could read or manipulate private claims belonging to another agent.
3. An attacker could pass a foreign `workspace_id` and cross tenant boundaries.

### 2.2 `TrustedContext` Specification
Every domain service method strictly requires a `TrustedContext` instance as its first non-session argument. The `TrustedContext` is created exclusively by trusted authentication middlewares/dependencies after validating API keys or session tokens.

```python
class ActorType(str, Enum):
    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"

@dataclass(frozen=True)
class TrustedContext:
    workspace_id: UUID
    actor_type: ActorType
    actor_id: UUID
    is_active: bool = True
```

### 2.3 Context Invariants
1. **Immutable Tenant Anchor:** All database queries and insertions executed by the service MUST be constrained to `context.workspace_id`.
2. **Attribution Binding:** When an agent creates an evidence snapshot or claim, the owning `agent_id` or `collected_by_agent` is bound directly to `context.actor_id`. Client attempts to specify a different `agent_id` are rejected with `UnauthorizedActorError`.
3. **Cross-Tenant Prevention:** Service methods never accept external `workspace_id` parameters. Any referenced entity (e.g. `evidence_id`, `claim_id`) is validated to belong to `context.workspace_id`.

---

## 3. Transaction Boundaries & Unit of Work

### 3.1 Transaction Policy
1. **Caller-Managed Transactions:** Domain services receive an active `AsyncSession`. Services do **not** call `await session.commit()` or `await session.rollback()` directly. Instead, they stage entities using `session.add()` and `await session.flush()`.
2. **Transaction Scope:** In the HTTP layer, the FastAPI dependency `get_db()` wraps the entire request pipeline in a single database transaction. If the service completes successfully, `get_db()` commits the transaction. If any domain error or unhandled exception is raised, `get_db()` rolls back all staged mutations.
3. **Atomic Audit Logging:** Any state change (creating a claim, recording evidence, establishing a relation) MUST write corresponding `audit_events` rows within the **same** transaction before flush. A mutation cannot commit without its accompanying audit record.

---

## 4. Domain Service Interfaces

### 4.1 Evidence Service (`EvidenceService`)

Responsible for ingesting immutable source observations from files, commits, user inputs, and tool executions.

#### `record_evidence`
* **Signature:**
  ```python
  async def record_evidence(
      session: AsyncSession,
      context: TrustedContext,
      params: RecordEvidenceParams,
  ) -> Evidence
  ```
* **Parameters (`RecordEvidenceParams`):**
  * `source_type`: Literal `'file'`, `'git_commit'`, `'user_turn'`, `'tool_output'`, `'api_response'`.
  * `source_uri`: Non-empty URI or file path identifier.
  * `raw_snippet`: Non-empty text content of the observation.
  * `content_hash`: Optional SHA-256 hex string. If omitted, the service calculates `sha256(raw_snippet.encode('utf-8')).hexdigest()`. If provided, it validates that it matches the computed hash.
  * `metadata`: Optional JSON dictionary (file commit info, line numbers, execution metadata).
* **Validation Rules:**
  * `source_type` must match allowed literals.
  * `raw_snippet` must not be whitespace-only.
  * Attribution is set according to `context.actor_type`:
    * If `actor_type == "agent"`: `collected_by_agent = context.actor_id`, `collected_by_user = None`.
    * If `actor_type == "user"`: `collected_by_user = context.actor_id`, `collected_by_agent = None`.
    * If `actor_type == "system"`: both attribution pointers are `None`.
* **Side Effects (Atomic):**
  1. Creates and adds `Evidence` model to `session`.
  2. Creates and adds `AuditEvent` model with `event_type="EVIDENCE_RECORDED"`, `target_type="evidence"`, `target_id=evidence.id`, and payload containing provenance metadata.
  3. Flushes session to assign generated UUID and timestamps.

---

### 4.2 Claim Service (`ClaimService`)

Responsible for managing the lifecycle of atomic assertions, provenance linkages, supersession revisions, and scope promotions.

#### 4.2.1 `create_claim`
* **Signature:**
  ```python
  async def create_claim(
      session: AsyncSession,
      context: TrustedContext,
      params: CreateClaimParams,
  ) -> Claim
  ```
* **Parameters (`CreateClaimParams`):**
  * `subject`: Target entity (e.g. `database.persistence`, `architecture.caching`).
  * `predicate`: Semantic attribute (e.g. `engine_type`, `configured_as`).
  * `object_value`: Structured JSON payload (e.g. `{"engine": "sqlite"}`).
  * `raw_statement`: Natural-language summary statement.
  * `claim_type`: Literal `'fact'`, `'recommendation'`, `'decision'`, `'preference'`, `'constraint'`. Default: `'fact'`.
  * `scope`: Literal `'private'`, `'team'`, `'workspace'`. Default: `'private'`.
  * `status`: Literal `'current'`, `'superseded'`, `'disputed'`, `'needs_review'`, `'retracted'`. Default: `'current'`.
  * `confidence`: Decimal in range `[0.00, 1.00]`. Default: `1.00`.
  * `agent_id`: Optional UUID.
* **Validation Rules:**
  * Confidence must satisfy $0.00 \le \text{confidence} \le 1.00$.
  * Claims can only be created by an authorized agent in the same workspace. If `context.actor_type != "agent"`, raises `UnauthorizedActorError`.
  * The owning `agent_id` is bound strictly to `context.actor_id`. If the caller explicitly supplied a divergent `agent_id`, raises `UnauthorizedActorError`.
  * `raw_statement`, `subject`, and `predicate` must be non-empty strings and cannot be whitespace-only.
* **Side Effects (Atomic):**
  1. Creates and adds `Claim` model to `session`.
  2. Creates and adds `AuditEvent` model with `event_type="CLAIM_CREATED"`, `target_type="claim"`, `target_id=claim.id`, and payload summary.
  3. Flushes session.

#### 4.2.2 `link_evidence`
* **Signature:**
  ```python
  async def link_evidence(
      session: AsyncSession,
      context: TrustedContext,
      params: LinkEvidenceParams,
  ) -> ClaimEvidence
  ```
* **Parameters (`LinkEvidenceParams`):**
  * `claim_id`: UUID of the target claim.
  * `evidence_id`: UUID of the associated evidence.
  * `support_type`: Literal `'supports'`, `'refutes'`, `'mentions'`. Default: `'supports'`.
  * `confidence_weight`: Decimal in range `[0.00, 1.00]`. Default: `1.00`.
  * `extraction_notes`: Optional natural-language rationale explaining how the evidence justifies or refutes the claim.
* **Validation Rules:**
  * The target claim must exist and have `claim.workspace_id == context.workspace_id`. If not, raises `EntityNotFoundError`.
  * The target evidence must exist and have `evidence.workspace_id == context.workspace_id`. If not, raises `EntityNotFoundError`.
  * If the junction `(claim_id, evidence_id)` already exists, raises `DuplicateLinkError`.
  * Confidence weight must satisfy $0.00 \le w \le 1.00$.
* **Side Effects (Atomic):**
  1. Creates and adds `ClaimEvidence` model to `session`.
  2. Creates and adds `AuditEvent` with `event_type="EVIDENCE_LINKED"`, `target_type="claim_evidence"`, and payload containing `{claim_id, evidence_id, support_type, confidence_weight}`.
  3. Flushes session.

#### 4.2.3 `supersede_claim` *(Specification — Scheduled for Phase C)*
* **Signature:**
  ```python
  async def supersede_claim(
      session: AsyncSession,
      context: TrustedContext,
      params: SupersedeClaimParams,
  ) -> ClaimRelation
  ```
* **Design Specification:**
  * When a new claim supersedes an existing claim:
    1. Validates that both claims exist and belong to `context.workspace_id`.
    2. Validates that `source_claim_id != target_claim_id`.
    3. Updates `target_claim.status = 'superseded'` and increments its version.
    4. Creates `ClaimRelation` with `relation_type = 'supersedes'`, `source_claim_id = new_claim_id`, `target_claim_id = old_claim_id`, and `rationale`.
    5. Dispatches non-destructive cascade invalidation: queries `ClaimRelation` for any claims where `relation_type = 'depends_on'` and `target_claim_id = old_claim_id`. For each dependent claim:
       - If status is `current`, transitions status to `needs_review`.
       - Emits `AuditEvent` with `event_type="DEPENDENCY_INVALIDATED"`.
    6. Emits `AuditEvent` with `event_type="CLAIM_SUPERSEDED"`.

---

## 5. Domain Exception Hierarchy

All domain exceptions inherit from `FilamentDomainError` to ensure clean separation from lower-level database or framework errors:

```text
FilamentDomainError
├── EntityNotFoundError (Entity does not exist in the tenant workspace)
├── WorkspaceMismatchError (Entity belongs to a different workspace)
├── UnauthorizedActorError (Actor lacks permission or attempts impersonation)
├── ValidationDomainError (Validation rule violated: confidence bounds, invalid literals)
├── DuplicateLinkError (Claim-evidence link or relation already exists)
└── InvalidClaimStateError (Illegal state transition attempted)
```

---

## 6. Audit Trail Design & Event Types

Every domain operation stages an immutable record in `audit_events`.

| Operation | `event_type` | `target_type` | Payload Details |
| :--- | :--- | :--- | :--- |
| Ingest evidence | `EVIDENCE_RECORDED` | `evidence` | `source_type`, `source_uri`, `content_hash` |
| Create claim | `CLAIM_CREATED` | `claim` | `claim_type`, `scope`, `subject`, `predicate`, `confidence` |
| Link evidence | `EVIDENCE_LINKED` | `claim_evidence` | `claim_id`, `evidence_id`, `support_type`, `confidence_weight` |
| Supersede claim *(Phase C)* | `CLAIM_SUPERSEDED` | `claim` | `old_claim_id`, `new_claim_id`, `rationale` |
| Invalidate dependency *(Phase C)* | `DEPENDENCY_INVALIDATED` | `claim` | `claim_id`, `invalidating_upstream_claim_id`, `old_status`, `new_status` |

---

## 7. Phased Implementation Strategy

* **Phase A (Current):** Architectural specification and review in `docs/domain-services.md`.
* **Phase B (Foundational Implementation):**
  * `TrustedContext` and domain exceptions.
  * Pydantic schemas / DTOs for service parameters.
  * `EvidenceService.record_evidence` with automatic SHA-256 calculation and audit logging.
  * `ClaimService.create_claim` with actor attribution validation and audit logging.
  * `ClaimService.link_evidence` with cross-workspace protection and audit logging.
  * Isolated unit and mock database tests verifying atomic audit creation and error conditions.
* **Phase C (Implemented in Step 20):**
  * `ClaimService.supersede_claim`, `create_dependency`, and `create_relation`.
  * Non-destructive `needs_review` dependency cascade invalidation with `DEPENDENCY_INVALIDATED` audit events.
  * Directed DAG cycle prevention (`CyclicRelationError`).
  * Endpoints mounted under `/api/v1/claims/{id}/relations`, `/supersede`, and `/dependencies`.
* **Phase D (Steps 22-24 - Condition Governance & Evaluation):**
  * Models: `EnvironmentSnapshot`, `ClaimConditionSet`, `ClaimCondition`, `ClaimVerification`.
  * `SnapshotService.record_snapshot`: Ingests agent-reported environment snapshots with path canonicalization and inventory completeness declarations (`packages_scope`, `runtime_scope`).
  * `ConditionService.establish_initial_conditions`: Atomically establishes initial versioned condition set (version 1), validates conditions against snapshot, and binds `claims.active_condition_version`.
  * `EvaluationService.evaluate_claim_conditions`: Transient read-only evaluation of claim conditions against a newly recorded snapshot following strict precedence semantics (`applicable`, `environment_mismatch`, `indeterminate`, `not_applicable`, `unconditioned`). Strictly read-only without transaction commit, mutation, or audit emission.

