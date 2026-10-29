# Filament Data Model & Lineage Architecture

This document defines the relational data model for **Filament**, a provenance-aware memory governance and validity layer for multi-agent and multi-application systems.

---

## 1. Governance Philosophy & Core Tenets

Filament does not treat memory as an unconstrained key-value store or raw vector sink. Instead, memory is modeled as a **governed lineage graph of contextual claims supported by evidence, bound by access scopes, and dynamically evaluated for ongoing validity**.

### Foundational Tenets
1. **Claims are Distinct from Evidence:** An observation or document excerpt (evidence) is not identical to the proposition inferred from it (claim). Evidence may remain historically immutable while the validity of derived claims evolves.
2. **Changed Evidence is Not Proof of Falsity:** Modifying a source document or changing a git commit hash does not automatically prove a previous claim false. It signals that dependencies must be audited or marked for review (`NEEDS_REVIEW`), rather than silently erased.
3. **Non-Destructive Invalidation:** When an upstream claim is superseded, dependent recommendations are neither deleted nor marked false. They transition to `NEEDS_REVIEW` with full provenance preserved, allowing agents and human operators to inspect the causal break.
4. **Server-Enforced Scope Boundaries:** Private agent observations must never leak into team or workspace scopes without explicit promotion and authorization. Access boundaries are validated on the server using verified credentials, not caller-supplied identifiers or LLM system prompts.

---

## 2. Entity-Relationship Overview

```text
┌─────────────────┐       ┌─────────────────┐
│   workspaces    │───────┤      users      │
└────────┬────────┘       └─────────────────┘
         │
         │ 1:N
         ▼
┌─────────────────┐       ┌─────────────────┐
│     agents      │───────┤  audit_events   │ (Append-Only)
└────────┬────────┘       └─────────────────┘
         │
         │ 1:N
         ├──────────────────────────────┐
         ▼                              ▼
┌─────────────────┐           ┌──────────────────┐
│    evidence     │           │      claims      │
└────────┬────────┘           └────────┬─────────┘
         │                             │
         │ M:N (supports / refutes)    │ 1:N (recursive DAG)
         ▼                             ▼
┌─────────────────┐           ┌──────────────────┐
│ claim_evidence  │           │ claim_relations  │
│ (provenance)    │           │ (supersedes/     │
└─────────────────┘           │  depends_on)     │
                              └──────────────────┘
```

---

## 3. Relational Schema Specification

### 3.1 `workspaces`
Represents the root tenant boundary. All entities strictly belong to a single workspace.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Unique workspace identifier (UUIDv7/v4). |
| `name` | `VARCHAR(128)` | `NOT NULL` | Display name of the workspace/organization. |
| `slug` | `VARCHAR(64)` | `NOT NULL, UNIQUE` | URL-safe workspace slug. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Workspace creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Workspace modification timestamp. |

* **Indexes:** `CREATE UNIQUE INDEX uq_workspaces_slug ON workspaces(slug);`
* **Deletion Policy:** Restrict deletion if child records exist (`ON DELETE RESTRICT`).

---

### 3.2 `users`
Human operators, administrators, and auditors within a workspace.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Unique user identifier. |
| `workspace_id` | `UUID` | `NOT NULL, FK -> workspaces(id) ON DELETE CASCADE` | Tenant workspace boundary. |
| `email` | `VARCHAR(255)` | `NOT NULL` | User email address. |
| `display_name` | `VARCHAR(128)` | `NOT NULL` | User display name. |
| `role` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'member', CHECK (role IN ('owner', 'admin', 'member', 'auditor'))` | User role within workspace. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Record update timestamp. |

* **Cardinality Design Note:** For MVP, each user row belongs to a single workspace (`workspace_id`), satisfying hackathon requirements without complex membership joins. Multi-workspace user accounts can be extracted into a `workspace_members` join table in future iterations without changing downstream entity schemas.
* **Indexes & Constraints:**
  * `CREATE UNIQUE INDEX uq_users_workspace_email ON users(workspace_id, email);`
  * `CREATE INDEX idx_users_workspace_id ON users(workspace_id);`

---

### 3.3 `agents`
Autonomous agents registered to operate within a workspace with defined visibility and capabilities.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Unique agent identifier. |
| `workspace_id` | `UUID` | `NOT NULL, FK -> workspaces(id) ON DELETE CASCADE` | Tenant workspace boundary. |
| `name` | `VARCHAR(128)` | `NOT NULL` | Unique name of the agent in the workspace (e.g., `architect-agent`, `coder-agent`). |
| `api_key_hash` | `VARCHAR(64)` | `NOT NULL` | SHA-256 hash of agent authentication secret. |
| `system_prompt_hash`| `VARCHAR(64)` | `NULLABLE` | SHA-256 hash of agent instructions for provenance auditing. |
| `default_scope` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'private', CHECK (default_scope IN ('private', 'team', 'workspace'))` | Default memory emission scope. |
| `is_active` | `BOOLEAN` | `NOT NULL, DEFAULT TRUE` | Whether the agent is active and permitted to query/ingest. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Registration timestamp. |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Update timestamp. |

* **Authentication Rule:** Agents must authenticate using a bearer key (`api_key_hash`). The service layer resolves `agent_id` and `workspace_id` from the validated token; caller-supplied identifiers in request bodies are rejected if they do not match the token context.
* **Indexes & Constraints:**
  * `CREATE UNIQUE INDEX uq_agents_workspace_name ON agents(workspace_id, name);`
  * `CREATE INDEX idx_agents_workspace ON agents(workspace_id);`

---

### 3.4 `evidence`
Immutable records of source artifacts, chat turns, documents, or external signals from which claims are extracted.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Unique evidence identifier. |
| `workspace_id` | `UUID` | `NOT NULL, FK -> workspaces(id) ON DELETE CASCADE` | Tenant workspace boundary. |
| `source_type` | `VARCHAR(32)` | `NOT NULL, CHECK (source_type IN ('file', 'git_commit', 'user_turn', 'tool_output', 'api_response'))` | Origin source type. |
| `source_uri` | `TEXT` | `NOT NULL` | URI, path, or identifier (e.g. `repo/README.md#L15`, `git://a1b2c3d`). |
| `content_hash` | `VARCHAR(64)` | `NOT NULL` | SHA-256 hash of the evidence snapshot for integrity verification. |
| `raw_snippet` | `TEXT` | `NOT NULL` | Verbatim text excerpt or content supporting or refuting a claim. |
| `collected_by_agent`| `UUID` | `NULLABLE, FK -> agents(id) ON DELETE SET NULL` | Agent that harvested the evidence. |
| `collected_by_user` | `UUID` | `NULLABLE, FK -> users(id) ON DELETE SET NULL` | Human operator that uploaded or confirmed evidence. |
| `metadata` | `JSONB` | `NOT NULL, DEFAULT '{}'::jsonb` | Extensible metadata (file version, commit author, timestamps, mime type). |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Evidence capture timestamp. |

* **Indexes & Constraints:**
  * `CREATE INDEX idx_evidence_workspace ON evidence(workspace_id);`
  * `CREATE INDEX idx_evidence_source_lookup ON evidence(workspace_id, source_type, content_hash);`
  * `CREATE INDEX idx_evidence_metadata_gin ON evidence USING GIN (metadata);`
* **Immutability:** `evidence` rows are strictly append-only. Edits to source files create *new* evidence records rather than mutating existing rows.

---

### 3.5 `claims`
Atomic assertions, state observations, or derived recommendations stored in memory.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Unique claim identifier. |
| `workspace_id` | `UUID` | `NOT NULL, FK -> workspaces(id) ON DELETE CASCADE` | Tenant workspace boundary. |
| `agent_id` | `UUID` | `NOT NULL, FK -> agents(id) ON DELETE RESTRICT` | Agent that originated this claim. |
| `claim_type` | `VARCHAR(32)` | `NOT NULL, CHECK (claim_type IN ('fact', 'recommendation', 'decision', 'preference', 'constraint'))` | Type of assertion. |
| `subject` | `VARCHAR(128)` | `NOT NULL` | Semantic entity or topic (e.g. `project.persistence`, `database.engine`). |
| `predicate` | `VARCHAR(64)` | `NOT NULL` | Relationship or attribute (e.g. `configured_as`, `migrated_to`, `recommends`). |
| `object_value` | `JSONB` | `NOT NULL` | Structured value/payload of the claim (e.g. `{"database": "sqlite", "version": 3}`). |
| `raw_statement` | `TEXT` | `NOT NULL` | Human-readable statement (e.g. *"The project database migrated to SQLite"*). |
| `scope` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'private', CHECK (scope IN ('private', 'team', 'workspace'))` | Visibility tier. |
| `status` | `VARCHAR(32)` | `NOT NULL, DEFAULT 'current', CHECK (status IN ('current', 'superseded', 'disputed', 'needs_review', 'retracted'))` | Lifecycle validity status. |
| `confidence` | `NUMERIC(3, 2)` | `NOT NULL, DEFAULT 1.00, CHECK (confidence >= 0.00 AND confidence <= 1.00)` | Confidence score (0.00 to 1.00). |
| `version` | `INTEGER` | `NOT NULL, DEFAULT 1` | Optimistic locking counter. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Ingestion timestamp. |
| `updated_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Last status update timestamp. |

* **Composite Key for Cross-Table Integrity:**
  * `CREATE UNIQUE INDEX uq_claims_workspace_id ON claims(workspace_id, id);`
* **Query Indexes:**
  * `CREATE INDEX idx_claims_query_active ON claims(workspace_id, scope, status, subject);`
  * `CREATE INDEX idx_claims_agent_scope ON claims(workspace_id, agent_id, scope);`
  * `CREATE INDEX idx_claims_status ON claims(status);`
  * `CREATE INDEX idx_claims_object_gin ON claims USING GIN (object_value);`

---

### 3.6 `claim_evidence`
Many-to-many junction table binding claims to supporting or refuting evidence records.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `claim_id` | `UUID` | `NOT NULL, FK -> claims(id) ON DELETE CASCADE` | Claim being justified or refuted. |
| `evidence_id` | `UUID` | `NOT NULL, FK -> evidence(id) ON DELETE RESTRICT` | Associated evidence record. |
| `support_type` | `VARCHAR(16)` | `NOT NULL, DEFAULT 'supports', CHECK (support_type IN ('supports', 'refutes', 'mentions'))` | Polarity of the evidence relative to the claim. |
| `extraction_notes` | `TEXT` | `NULLABLE` | Explanation of how the claim was synthesized or contradicted. |
| `confidence_weight`| `NUMERIC(3, 2)` | `NOT NULL, DEFAULT 1.00, CHECK (confidence_weight >= 0.00 AND confidence_weight <= 1.00)` | Weight of this evidence for this claim. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Association timestamp. |

* **Primary Key:** `PRIMARY KEY (claim_id, evidence_id)`
* **Support Polarity Semantics:** Distinguishes evidence that validates a claim from evidence that refutes it, allowing claims to be marked `DISPUTED` with direct links to the contradicting evidence.
* **Indexes:** `CREATE INDEX idx_claim_evidence_reverse ON claim_evidence(evidence_id, claim_id);`

---

### 3.7 `claim_relations`
Captures directed causal and structural relationships between claims. This table houses both **supersession** (revisions) and **dependencies** (derivations).

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Unique relation record identifier. |
| `workspace_id` | `UUID` | `NOT NULL, FK -> workspaces(id) ON DELETE CASCADE` | Tenant workspace boundary. |
| `source_claim_id` | `UUID` | `NOT NULL` | Subject/origin claim in the directed edge. |
| `target_claim_id` | `UUID` | `NOT NULL` | Object/destination claim in the directed edge. |
| `relation_type` | `VARCHAR(32)` | `NOT NULL, CHECK (relation_type IN ('supersedes', 'depends_on', 'contradicts', 'corroborates'))` | Edge semantic type. |
| `rationale` | `TEXT` | `NOT NULL` | Explicit explanation of why this relation exists. |
| `created_by_agent`| `UUID` | `NULLABLE, FK -> agents(id) ON DELETE SET NULL` | Agent that established this relation. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Relation creation timestamp. |

* **Workspace Consistency Foreign Keys:**
  Both claims in a relation must belong to the exact same workspace as the relation itself:
  * `FOREIGN KEY (workspace_id, source_claim_id) REFERENCES claims(workspace_id, id) ON DELETE CASCADE`
  * `FOREIGN KEY (workspace_id, target_claim_id) REFERENCES claims(workspace_id, id) ON DELETE CASCADE`
* **Integrity & Cycle Constraints:**
  * `CHECK (source_claim_id <> target_claim_id)` — Prevents immediate self-referential loops.
  * `CREATE UNIQUE INDEX uq_claim_relation_edge ON claim_relations(source_claim_id, target_claim_id, relation_type);`
  * `CREATE INDEX idx_claim_relations_target ON claim_relations(target_claim_id, relation_type);`

#### Edge Direction Definitions
The direction of the edge is explicitly defined as `source_claim_id -> target_claim_id`:
1. **`supersedes` (Newer Replaces Older):**
   * **Convention:** `NEW_CLAIM (source) supersedes OLD_CLAIM (target)`.
   * **Example:** `source_claim_id = Claim_SQLite`, `target_claim_id = Claim_PostgreSQL`, `relation_type = 'supersedes'`, `rationale = "Git commit a1b2c3d migrated persistence to SQLite."`
2. **`depends_on` (Derived Requires Prerequisite):**
   * **Convention:** `DEPENDENT_RECOMMENDATION (source) depends_on PREREQUISITE_FACT (target)`.
   * **Example:** `source_claim_id = Rec_AsyncpgPool`, `target_claim_id = Claim_PostgreSQL`, `relation_type = 'depends_on'`, `rationale = "Asyncpg pool sizing is predicated on PostgreSQL."`

---

### 3.8 `audit_events`
Append-only, immutable security and governance audit trail recording all critical lifecycle transitions, cascade invalidations, and policy evaluations.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Unique audit event identifier. |
| `workspace_id` | `UUID` | `NOT NULL, FK -> workspaces(id) ON DELETE CASCADE` | Tenant workspace boundary. |
| `actor_type` | `VARCHAR(32)` | `NOT NULL, CHECK (actor_type IN ('agent', 'user', 'system'))` | Actor initiating action. |
| `actor_id` | `UUID` | `NOT NULL` | ID of the agent, user, or system worker. |
| `event_type` | `VARCHAR(64)` | `NOT NULL` | E.g. `CLAIM_INGESTED`, `CLAIM_SUPERSEDED`, `DEPENDENCY_INVALIDATED`, `SCOPE_PROMOTION_REQUESTED`, `UNAUTHORIZED_ACCESS_BLOCKED`. |
| `target_type` | `VARCHAR(32)` | `NOT NULL` | Entity type affected: `claim`, `evidence`, `relation`. |
| `target_id` | `UUID` | `NOT NULL` | Entity ID affected. |
| `idempotency_key` | `VARCHAR(64)` | `NULLABLE` | Optional key to deduplicate events across retries. |
| `payload` | `JSONB` | `NOT NULL, DEFAULT '{}'::jsonb` | Snapshot of changes, reasons, policy evaluation outputs, or diffs. |
| `created_at` | `TIMESTAMPTZ` | `NOT NULL, DEFAULT NOW()` | Event recording timestamp. |

* **Immutability Enforcement:**
  1. **PostgreSQL Grant Layer:** The application connection role (`filament_app`) is granted `SELECT, INSERT` only on `audit_events`. `UPDATE` and `DELETE` privileges are explicitly revoked.
  2. **Database Trigger:** A `BEFORE UPDATE OR DELETE` trigger aborts any modification attempt, preventing even administrative application connections from mutating audit history:
     ```sql
     CREATE OR REPLACE FUNCTION filament_protect_audit_log() RETURNS TRIGGER AS $$
     BEGIN
         RAISE EXCEPTION 'audit_events is append-only and cannot be updated or deleted';
     END;
     $$ LANGUAGE plpgsql;

     CREATE TRIGGER trg_protect_audit_events
     BEFORE UPDATE OR DELETE ON audit_events
     FOR EACH ROW EXECUTE FUNCTION filament_protect_audit_log();
     ```
* **Indexes:**
  * `CREATE INDEX idx_audit_events_timeline ON audit_events(workspace_id, created_at DESC);`
  * `CREATE INDEX idx_audit_target ON audit_events(target_type, target_id);`
  * `CREATE UNIQUE INDEX uq_audit_idempotency ON audit_events(workspace_id, idempotency_key) WHERE idempotency_key IS NOT NULL;`

---

## 4. Claim Lifecycle & State-Transition Semantics

```text
       ┌──────────────┐
       │   [Draft]    │
       └──────┬───────┘
              │ Ingestion & validation
              ▼
       ┌──────────────┐
       │   CURRENT    │◄─────────────────┐
       └──┬────────┬──┘                  │
          │        │                     │ Re-verified /
          │        │ Contested           │ Resolved
Superseded│        ▼                     │
by newer  │   ┌──────────────┐           │
evidence  │   │   DISPUTED   │───────────┘
          │   └──────────────┘
          ▼
┌──────────────────┐       Upstream       ┌──────────────────┐
│    SUPERSEDED    │       claim changed  │   NEEDS_REVIEW   │
│  (Historical;    │─────────────────────►│  (Recommendation │
│   not in prompt) │                      │   unverified)    │
└──────────────────┘                      └─────────┬────────┘
                                                    │
                                                    ▼ (Dismiss or Update)
                                          ┌──────────────────┐
                                          │    RETRACTED     │
                                          └──────────────────┘
```

### 4.1 State Definitions
1. **`CURRENT`**:
   * Active, verified claim eligible for inclusion in agent prompt contexts matching its scope.
2. **`SUPERSEDED`**:
   * Replaced by a newer or higher-authority claim on the same topic.
   * Excluded from active prompt contexts, but preserved for historical audit queries.
   * Always paired with a `supersedes` relation record pointing from the successor to the superseded claim, accompanied by a mandatory `rationale`.
3. **`DISPUTED`**:
   * Contradictory evidence or conflicting claims exist without consensus.
   * Excluded from affirmative prompt context or returned only with explicit conflict caveats.
4. **`NEEDS_REVIEW`**:
   * An upstream prerequisite claim (`relation_type = 'depends_on'`) was superseded, disputed, or retracted.
   * **Integrity Invariant:** Changed upstream evidence does *not* prove a dependent recommendation is false or justify its deletion. The recommendation is retained and flagged for re-evaluation.
5. **`RETRACTED`**:
   * Explicitly withdrawn by an authorized user or authoring agent due to confirmed error.

### 4.2 State Transition Matrix

| Current State | Event Trigger | Next State | Audit Event Emitted | Required Metadata |
| :--- | :--- | :--- | :--- | :--- |
| `CURRENT` | Newer authoritative claim ingested | `SUPERSEDED` | `CLAIM_SUPERSEDED` | Successor `claim_id` + `rationale`. |
| `CURRENT` | Ingestion of refuting evidence (`support_type = 'refutes'`) | `DISPUTED` | `CLAIM_DISPUTED` | Refuting `evidence_id` + conflict note. |
| `CURRENT` | Upstream prerequisite transitions to `SUPERSEDED` | `NEEDS_REVIEW` | `DEPENDENCY_INVALIDATED` | Broken upstream `claim_id`. |
| `NEEDS_REVIEW`| Agent or user verifies recommendation remains sound | `CURRENT` | `CLAIM_REVALIDATED` | Justification note. |
| `NEEDS_REVIEW`| New adapted recommendation created to replace stale one | `SUPERSEDED` | `CLAIM_SUPERSEDED` | Successor recommendation `claim_id`. |
| Any | Explicit operator or agent retraction | `RETRACTED` | `CLAIM_RETRACTED` | Reason for retraction. |

---

## 5. Lineage, Cascades, & Cycle Prevention

### 5.1 Supersession Mechanics (Demo Scenarios 1, 2, and 3)
1. **Initial State (Claim 1):**
   * `Claim 1`: `{id: "c1", subject: "project.persistence", predicate: "database_type", object_value: "PostgreSQL", status: "CURRENT", scope: "team"}`.
   * Supported by `Evidence 1` (`README.md#L15`) via `claim_evidence` (`support_type = 'supports'`).
2. **Migration Event (Claim 2):**
   * `Evidence 2` recorded: Git commit `a1b2c3d` *"chore: migrate persistence from postgresql to sqlite"*.
   * `Claim 2`: `{id: "c2", subject: "project.persistence", predicate: "database_type", object_value: "SQLite", status: "CURRENT", scope: "team"}`.
3. **Atomic Supersession Transaction:**
   Within a single database transaction:
   1. Insert `Claim 2` with status `CURRENT`.
   2. Link `Claim 2` to `Evidence 2` in `claim_evidence` (`support_type = 'supports'`).
   3. Update `Claim 1` status to `SUPERSEDED`.
   4. Insert `claim_relations`:
      * `source_claim_id`: `c2` (New SQLite claim)
      * `target_claim_id`: `c1` (Old PostgreSQL claim)
      * `relation_type`: `'supersedes'`
      * `rationale`: `"Git commit a1b2c3d explicitly replaced PostgreSQL with SQLite in pyproject.toml and docker-compose.yml."`
   5. Record `audit_events` with `event_type = 'CLAIM_SUPERSEDED'`.

### 5.2 Dependency Cascades (Demo Scenario 4)
Consider `Claim 3` (Recommendation derived from `Claim 1`):
* `Claim 3`: `{id: "c3", claim_type: "recommendation", raw_statement: "Configure asyncpg connection pool with max_overflow=20", status: "CURRENT"}`.
* Linked via `claim_relations`:
  * `source_claim_id`: `c3` (Recommendation)
  * `target_claim_id`: `c1` (PostgreSQL fact)
  * `relation_type`: `'depends_on'`
  * `rationale`: `"asyncpg connection pool settings are predicated on PostgreSQL persistence."`

**Cascade Execution Logic:**
When `c1` is updated to `SUPERSEDED`:
1. Find all active claims that depend on `c1`:
   ```sql
   SELECT source_claim_id 
   FROM claim_relations 
   WHERE target_claim_id = :superseded_claim_id 
     AND relation_type = 'depends_on';
   ```
2. For each dependent claim (`c3`):
   * Update `status = 'NEEDS_REVIEW'`.
   * Increment optimistic lock `version = version + 1`.
   * Insert `audit_events` row:
     ```json
     {
       "event_type": "DEPENDENCY_INVALIDATED",
       "target_id": "c3",
       "payload": {
         "broken_prerequisite_id": "c1",
         "broken_prerequisite_status": "SUPERSEDED",
         "action_taken": "status_changed_to_needs_review"
       }
     }
     ```
3. **Preservation Invariant:** `c3` is neither deleted nor marked false. If an agent subsequently asks *"What connection pool size was recommended?"*, Filament can retrieve `c3` with its governance flag: *"Recommendation Claim 3 (asyncpg pool) exists but is flagged as needs_review because its prerequisite (PostgreSQL database) was superseded by SQLite."*

### 5.3 Graph Cycle Prevention
Dependency chains (`depends_on`) and supersession lineages (`supersedes`) must strictly form Directed Acyclic Graphs (DAGs).
* **Direct Self-Loops:** Prohibited by database constraint `CHECK (source_claim_id <> target_claim_id)`.
* **Multi-Hop Cycles:** Before inserting into `claim_relations`, the service layer executes a depth-limited recursive traversal:
  ```sql
  WITH RECURSIVE lineage AS (
      SELECT target_claim_id, 1 as depth
      FROM claim_relations
      WHERE source_claim_id = :new_target_id 
        AND relation_type = :relation_type
      UNION ALL
      SELECT cr.target_claim_id, l.depth + 1
      FROM claim_relations cr
      JOIN lineage l ON cr.source_claim_id = l.target_claim_id
      WHERE cr.relation_type = :relation_type AND l.depth < 10
  )
  SELECT 1 FROM lineage WHERE target_claim_id = :new_source_id LIMIT 1;
  ```
  If a path exists, the insert is aborted with `CyclicRelationError`.

---

## 6. Authorization Strategy & Scope Governance (Demo Scenario 5)

### 6.1 Scope Tiers
* **`private`**: Visible **only** to the authoring agent (`agent_id`) within the tenant workspace.
* **`team`**: Visible to all registered agents and authorized users within the tenant workspace.
* **`workspace`**: System-wide public memory within the tenant workspace (e.g. organizational standards).

### 6.2 Scenario 5 Enforcement: Private Memory Isolation
Suppose `Agent A` generates private memory `Claim 4` (`scope = 'private'`, `agent_id = Agent_A_UUID`).
When `Agent B` queries memory:
1. **Identity Resolution:** The incoming request from Agent B is authenticated via API bearer token. The service layer extracts `requesting_agent_id = Agent_B_UUID`.
2. **Query Formulation in Service Layer:**
   ```sql
   SELECT c.* 
   FROM claims c
   WHERE c.workspace_id = :current_workspace_id
     AND c.status = 'current'
     AND (
       c.scope IN ('team', 'workspace')
       OR (c.scope = 'private' AND c.agent_id = :requesting_agent_id)
     );
   ```
   `Claim 4` is private to Agent A, so it is strictly filtered out of Agent B's query results.
3. **Direct Lookup Denial:**
   If Agent B attempts to directly request `GET /api/v1/claims/{claim_4_id}`:
   * Service evaluates: `claim.scope == 'private' and claim.agent_id != requesting_agent_id`.
   * Action: Access is denied (`403 Forbidden`).
   * Audit: Emits `audit_events` with `event_type = 'UNAUTHORIZED_SCOPE_ACCESS_BLOCKED'`.
4. **Scope Promotion Policy:**
   A private claim cannot become team-visible through prompt manipulation. Promotion requires calling `POST /api/v1/claims/{id}/promote`, which verifies that the caller is the authoring agent or workspace admin, updates `scope = 'team'`, and logs a `SCOPE_PROMOTED` audit event.

### 6.3 Multi-Tenant Database vs Application Level Isolation
* **Application Level (Primary Trust Boundary):**
  * Every repository query mandatorily filters by `workspace_id`.
  * FastAPI dependencies extract and verify `workspace_id` from authenticated session tokens.
* **PostgreSQL Row-Level Security (RLS) Strategy:**
  * Application connections run under a dedicated unprivileged role: `filament_app`.
  * RLS policies are enabled on all tenant tables:
    ```sql
    ALTER TABLE claims ENABLE ROW LEVEL SECURITY;
    ALTER TABLE claims FORCE ROW LEVEL SECURITY;

    CREATE POLICY workspace_isolation_policy ON claims
    FOR ALL
    TO filament_app
    USING (workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid);
    ```
  * During database session checkout, the connection sets `SET LOCAL app.current_workspace_id = :workspace_id`.
  * Migrations run under a separate administrative role (`filament_migrator` or `supabase_admin`) with schema alteration privileges.

---

## 7. Concurrency, Deletion Policies, & Failure Modes

### 7.1 Concurrency & Race Conditions
* **Optimistic Locking:** The `version` integer in `claims` prevents concurrent overwrite conflicts. Invalidation cascades and status updates execute:
  ```sql
  UPDATE claims 
  SET status = :new_status, version = version + 1, updated_at = NOW()
  WHERE id = :id AND version = :expected_version;
  ```
  If 0 rows are updated, a `ConcurrencyConflictError` triggers a transaction rollback and retry.

### 7.2 Deletion Semantics
* **Prohibition of Hard Deletes:** Hard deleting claims breaks lineage graphs and foreign keys in `claim_relations`, `claim_evidence`, and `audit_events`.
* **Soft Retraction:** Memory revocation updates `status = 'retracted'`, preserving the historic lineage node while removing it from active reasoning.
* **Workspace Teardown:** `ON DELETE CASCADE` is permitted strictly at the root `workspaces` table level to allow complete tenant deletion.

---

## 8. Hackathon Essential Scope vs Future Extensions

| Component | Essential (Hackathon MVP) | Future Extension |
| :--- | :--- | :--- |
| **Tenant Boundaries** | `workspaces`, `users`, `agents` | Fine-grained RBAC/ABAC role hierarchies. |
| **Memory Units** | `claims` with subject, predicate, object, status | Composite nested claims, fuzzy claim deduplication. |
| **Provenance** | `evidence` snapshots, `claim_evidence` junction | Automated live file watchers, git webhook ingestion. |
| **Lineage & Graph** | `claim_relations` (`supersedes`, `depends_on`) | Automated multi-agent dispute resolution voting. |
| **Audit Log** | Append-only `audit_events` with trigger protection | Tamper-evident cryptographic hash chains (Merkle tree). |
| **Vector Search** | Exact & structured JSONB attribute matching | `pgvector` embeddings for semantic claim similarity. |
| **Policy Engine** | Hardcoded server-side scope and status rules | Dynamic CEL (Common Expression Language) policy engine. |

---

## 9. Traceability to Demo Scenarios

| Scenario Requirement | Schema & Architecture Solution |
| :--- | :--- |
| **1. Initial PostgreSQL Claim** | Stored in `claims` (`status = 'current'`, `scope = 'team'`) linked via `claim_evidence` (`support_type = 'supports'`) to README evidence. |
| **2. SQLite Migration Evidence** | Captured in `evidence` with Git commit metadata and SHA-256 content hash. |
| **3. Supersession with Rationale** | New SQLite claim inserted as `current`; PostgreSQL claim updated to `superseded`; linked in `claim_relations` (`source = SQLite, target = PostgreSQL, relation_type = 'supersedes'`) with explicit `rationale` text. |
| **4. Dependent Recommendation Marked `needs_review`** | Downstream claim linked via `relation_type = 'depends_on'` automatically transitions to `needs_review` when parent claim is superseded; recommendation is not deleted or falsified. |
| **5. Private vs Team Scope Isolation** | `scope` attribute (`private` vs `team`); query filtering guarantees private memories of Agent A are invisible to Agent B in team queries; direct unauthorized access returns `403 Forbidden` and logs an audit violation. |
