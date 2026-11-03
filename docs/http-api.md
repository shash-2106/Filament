# Filament HTTP API & Authentication Specification

This document defines the REST API contract, authentication mechanism, error handling strategy, and tenant authorization rules for **Filament API (v1)**.

---

## 1. Architecture & Design Principles

The HTTP API is the external boundary through which client applications and autonomous agents interact with Filament. It enforces:

1. **Protocol-Level Isolation:** Route handlers deserialize and validate HTTP requests, delegate business logic to the domain service layer (`EvidenceService`, `ClaimService`), and map domain exceptions to standard HTTP error envelopes.
2. **Untrusted Client Inputs:** Request bodies are strictly forbidden from specifying `workspace_id` or overriding caller attribution. All tenant and actor identities are derived exclusively from verified authentication credentials.
3. **Defense-in-Depth Scope Enforcement:** Access to private memories is restricted to the owning agent. Cross-tenant or out-of-scope resources return `404 Not Found` rather than `403 Forbidden` to prevent resource enumeration.
4. **Atomic Unit-of-Work Transactions:** Every state-modifying request executes inside a database transaction managed by the `get_db` dependency. Domain mutations and their corresponding `AuditEvent` records commit atomically or roll back entirely upon failure.

---

## 2. Authentication Boundary & Credential Flow

### 2.1 The Authentication Mechanism
Filament authenticates agents using secret API bearer tokens passed via the standard HTTP `Authorization` header:

```http
Authorization: Bearer <agent_secret_key>
```

* **No Query/Body Tokens:** Secrets passed via query strings or request bodies are strictly rejected to prevent credential leakage into access logs, web proxies, or browser histories.
* **No Raw Key Storage:** Raw secrets are never stored in PostgreSQL, never logged, and never returned in API responses. The database stores only the 64-character hexadecimal SHA-256 digest (`api_key_hash`) of the secret.

### 2.2 Credential Verification Pipeline

```text
Incoming HTTP Request
       │
       ▼
Extract "Authorization: Bearer <token>"
       │
       ├─► Missing or malformed? ──► HTTP 401 Unauthorized (WWW-Authenticate: Bearer)
       ▼
Compute SHA-256: hashlib.sha256(token.encode('utf-8')).hexdigest()
       │
       ▼
Query: SELECT id, workspace_id, is_active, api_key_hash FROM agents WHERE api_key_hash = :hash
       │
       ├─► Not found? ──► Dummy constant-time comparison ──► HTTP 401 Unauthorized
       ▼
Constant-time verification: hmac.compare_digest(token_hash, agent.api_key_hash)
       │
       ├─► agent.is_active == False? ──► HTTP 401 Unauthorized ("Agent account is disabled.")
       ▼
Instantiate TrustedContext:
  TrustedContext(
      workspace_id=agent.workspace_id,
      actor_type="agent",
      actor_id=agent.id,
      is_active=True
  )
       │
       ▼
Inject into Route Handler via FastAPI Dependency
```

### 2.3 Constant-Time Comparison
To protect against timing side-channel attacks during hash validation, credential comparison utilizes `hmac.compare_digest(token_hash, agent.api_key_hash)`. If no agent matches the query, a dummy comparison against a static baseline hash is executed prior to returning `401 Unauthorized` to normalize execution timing.

### 2.4 Security Assumptions & Threat Model
* **Threat Boundary:** The authentication scheme protects against unauthenticated callers, agent impersonation across workspaces, and compromised passive network observers (assuming TLS).
* **Non-Goals / Limitations:** This scheme does not protect against:
  1. Compromised host environments or servers with memory inspection capabilities.
  2. Database administrators or privileged users with direct access to Supabase / PostgreSQL.
  3. Rainbow-table attacks against weak, low-entropy agent keys (keys should be generated with at least 256 bits of entropy, e.g., `fil_live_` prefixed base64/hex tokens).

---

## 3. Schema Evaluation: Key Revocation, Rotation, and Expiry

An audit of the current database schema (`agents` table) reveals the following capabilities and gaps:

| Capability | Current Schema Support | Mechanism / Gap Analysis |
| :--- | :--- | :--- |
| **Agent Disabling / Hard Revocation** | **Supported** | Setting `agents.is_active = FALSE` immediately prevents any key associated with that agent from authenticating. |
| **Immediate Key Overwrite** | **Supported** | Updating `agents.api_key_hash` immediately invalidates the previous key and activates the new key. |
| **Zero-Downtime Key Rotation** | **Not Supported** | The `agents` table possesses a single `api_key_hash` column. Storing two valid keys simultaneously during a rotation grace period is impossible without schema changes. |
| **Key Expiration** | **Not Supported** | The `agents` table lacks an `expires_at` timestamp. Keys remain valid indefinitely until manually overwritten or disabled. |
| **Granular Per-Key Revocation** | **Not Supported** | If an agent has multiple operational instances, revoking access for one instance requires rotating the key for all instances. |

### Schema Change Recommendation (Post-MVP Milestone)
For the MVP/Hackathon scope, the single `api_key_hash` and `is_active` flags on `agents` satisfy all demonstration requirements without modifying migrations.

For production readiness, the recommended schema evolution is extracting keys into a dedicated `agent_api_keys` table:
```sql
CREATE TABLE agent_api_keys (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL,
    key_prefix VARCHAR(12) NOT NULL,
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NULL,
    revoked_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
*No schema changes will be introduced in this milestone.*

---

## 4. Error Handling & Information Leakage Prevention

### 4.1 Safe Error Response Model
All API error responses adhere to a consistent JSON envelope:

```json
{
  "error": {
    "code": "ENTITY_NOT_FOUND",
    "message": "Claim with ID '9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d' was not found.",
    "details": {}
  }
}
```

### 4.2 Error Taxonomy & Status Codes

| HTTP Status | Error Code | Trigger Condition | Information Leakage Protection |
| :--- | :--- | :--- | :--- |
| **401 Unauthorized** | `UNAUTHORIZED` | Missing/malformed Authorization header, unknown key hash, or disabled agent. | Header `WWW-Authenticate: Bearer` is included. Generic error messages prevent username/agent enumeration. |
| **403 Forbidden** | `FORBIDDEN` | Verified agent attempts an operation outside permitted capability or scope. | Message specifies policy reason without disclosing internal role permissions. |
| **404 Not Found** | `NOT_FOUND` | Entity does not exist, belongs to another workspace, or is in private scope of another agent. | **Critical:** Returns 404 even if the record exists in another workspace to prevent cross-tenant resource enumeration. |
| **409 Conflict** | `CONFLICT` | Attempting to link an evidence snapshot that is already linked to the target claim. | Identifies duplicate edge without mutating existing records. |
| **422 Unprocessable Entity** | `VALIDATION_ERROR` | Schema validation failed (confidence out of bounds, whitespace strings, invalid enums). | Returns Pydantic error list detailing field constraints. |
| **500 Internal Server Error** | `INTERNAL_ERROR` | Unhandled exception or database connection failure. | Stack traces, raw SQL queries, and table names are suppressed; an internal correlation ID is logged. |

---

## 5. REST API Endpoint Contracts

Base URL Prefix: `/api/v1`

---

### 5.1 Health Probe

#### `GET /api/v1/health`
Lightweight process health probe for load balancers and orchestrators. Does not query PostgreSQL.

* **Authentication:** None (Public).
* **Request:** No parameters or payload.
* **Response (200 OK):**
  ```json
  {
    "status": "ok",
    "environment": "development",
    "version": "0.1.0",
    "database": "not_checked"
  }
  ```

---

### 5.2 Record Evidence Snapshot

#### `POST /api/v1/evidence`
Ingests an immutable observation snippet from a source document, git commit, tool run, or interaction turn.

* **Authentication:** Required (`Authorization: Bearer <agent_key>`).
* **Actor Type:** Agent.
* **Transaction & Audit:** Atomic. Staged alongside an `EVIDENCE_RECORDED` audit event; committed by session dependency upon successful handler execution.

#### Request Headers
```http
Authorization: Bearer fil_live_9a8b7c6d5e4f3a2b1c0d
Content-Type: application/json
```

#### Request Body (`RecordEvidenceParams`)
```json
{
  "source_type": "git_commit",
  "source_uri": "git://github.com/org/repo@a1b2c3d4",
  "raw_snippet": "Migrated database driver to asyncpg and configured pool size to 20.",
  "content_hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "metadata": {
    "commit_hash": "a1b2c3d4",
    "author": "dev@example.com"
  }
}
```
* `content_hash` is optional; if omitted, the server computes `sha256(raw_snippet)`.
* Extra fields are forbidden (`extra="forbid"`).

#### Response (201 Created)
```json
{
  "id": "e4eaaaf2-d142-4e4d-9e6a-72efc9bb3e10",
  "workspace_id": "018f3a20-0000-7000-8000-000000000001",
  "source_type": "git_commit",
  "source_uri": "git://github.com/org/repo@a1b2c3d4",
  "content_hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
  "raw_snippet": "Migrated database driver to asyncpg and configured pool size to 20.",
  "collected_by_agent": "018f3a20-0000-7000-8000-000000000002",
  "collected_by_user": null,
  "metadata": {
    "commit_hash": "a1b2c3d4",
    "author": "dev@example.com"
  },
  "created_at": "2026-10-29T10:45:00.000Z"
}
```

---

### 5.3 Create Memory Claim

#### `POST /api/v1/claims`
Asserts an atomic, governed fact or recommendation in memory.

* **Authentication:** Required (`Authorization: Bearer <agent_key>`).
* **Actor Type:** Agent. The claim's `agent_id` is automatically set to the authenticated agent's ID; caller attempts to supply a different `agent_id` are rejected with `403 Forbidden`.
* **Transaction & Audit:** Atomic. Staged alongside a `CLAIM_CREATED` audit event; committed by session dependency.

#### Request Body (`CreateClaimParams`)
```json
{
  "subject": "database.persistence",
  "predicate": "engine_type",
  "object_value": {
    "engine": "postgresql",
    "driver": "asyncpg",
    "pool_size": 20
  },
  "raw_statement": "The project uses PostgreSQL with asyncpg connection pooling.",
  "claim_type": "fact",
  "scope": "team",
  "status": "current",
  "confidence": "0.95"
}
```

#### Response (201 Created)
```json
{
  "id": "7f8b9c0d-1e2f-3a4b-5c6d-7e8f9a0b1c2d",
  "workspace_id": "018f3a20-0000-7000-8000-000000000001",
  "agent_id": "018f3a20-0000-7000-8000-000000000002",
  "claim_type": "fact",
  "subject": "database.persistence",
  "predicate": "engine_type",
  "object_value": {
    "engine": "postgresql",
    "driver": "asyncpg",
    "pool_size": 20
  },
  "raw_statement": "The project uses PostgreSQL with asyncpg connection pooling.",
  "scope": "team",
  "status": "current",
  "confidence": "0.95",
  "version": 1,
  "created_at": "2026-10-29T10:45:10.000Z",
  "updated_at": "2026-10-29T10:45:10.000Z"
}
```

---

### 5.4 Link Evidence to Claim

#### `POST /api/v1/claims/{claim_id}/evidence`
Associates an existing evidence record with a claim, specifying support polarity (`supports`, `refutes`, `mentions`) and confidence weight.

* **Authentication:** Required (`Authorization: Bearer <agent_key>`).
* **Path Parameter:** `claim_id` (UUID).
* **Validation & Authorization:**
  * `claim_id` must exist in `context.workspace_id`.
  * `evidence_id` must exist in `context.workspace_id`.
  * If either record belongs to another workspace, returns `404 Not Found`.
  * If `(claim_id, evidence_id)` link already exists, returns `409 Conflict`.
* **Transaction & Audit:** Atomic. Staged alongside an `EVIDENCE_LINKED` audit event; committed by session dependency.

#### Request Body (`LinkEvidenceRequest`)
```json
{
  "evidence_id": "e4eaaaf2-d142-4e4d-9e6a-72efc9bb3e10",
  "support_type": "supports",
  "confidence_weight": "1.00",
  "extraction_notes": "Commit message explicitly documents asyncpg configuration."
}
```

#### Response (201 Created)
```json
{
  "workspace_id": "018f3a20-0000-7000-8000-000000000001",
  "claim_id": "7f8b9c0d-1e2f-3a4b-5c6d-7e8f9a0b1c2d",
  "evidence_id": "e4eaaaf2-d142-4e4d-9e6a-72efc9bb3e10",
  "support_type": "supports",
  "confidence_weight": "1.00",
  "extraction_notes": "Commit message explicitly documents asyncpg configuration.",
  "created_at": "2026-10-29T10:45:20.000Z"
}
```

---

### 5.5 Retrieve Claim & Provenance

#### `GET /api/v1/claims/{claim_id}`
Fetches an individual claim and its provenance chain (supporting and refuting evidence records) within the caller's tenant boundary.

* **Authentication:** Required (`Authorization: Bearer <agent_key>`).
* **Path Parameter:** `claim_id` (UUID).
* **Scope & Visibility Evaluation:**
  1. `claim.workspace_id == context.workspace_id`: If false, returns `404 Not Found`.
  2. If `claim.scope == 'private'`: Must satisfy `claim.agent_id == context.actor_id`. If queried by a different agent in the same workspace, returns `404 Not Found` to preserve agent privacy.
  3. If `claim.scope in ('team', 'workspace')`: Readable by any active agent in the workspace.
* **Side Effects:** None (read-only query).

#### Response (200 OK)
```json
{
  "claim": {
    "id": "7f8b9c0d-1e2f-3a4b-5c6d-7e8f9a0b1c2d",
    "workspace_id": "018f3a20-0000-7000-8000-000000000001",
    "agent_id": "018f3a20-0000-7000-8000-000000000002",
    "claim_type": "fact",
    "subject": "database.persistence",
    "predicate": "engine_type",
    "object_value": {
      "engine": "postgresql",
      "driver": "asyncpg",
      "pool_size": 20
    },
    "raw_statement": "The project uses PostgreSQL with asyncpg connection pooling.",
    "scope": "team",
    "status": "current",
    "confidence": "0.95",
    "version": 1,
    "created_at": "2026-10-29T10:45:10.000Z",
    "updated_at": "2026-10-29T10:45:10.000Z"
  },
  "provenance": [
    {
      "evidence_id": "e4eaaaf2-d142-4e4d-9e6a-72efc9bb3e10",
      "source_type": "git_commit",
      "source_uri": "git://github.com/org/repo@a1b2c3d4",
      "content_hash": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
      "raw_snippet": "Migrated database driver to asyncpg and configured pool size to 20.",
      "support_type": "supports",
      "confidence_weight": "1.00",
      "extraction_notes": "Commit message explicitly documents asyncpg configuration.",
      "linked_at": "2026-10-29T10:45:20.000Z"
    }
  ]
}
```

### 5.5 Record Environment Snapshot
`POST /api/v1/snapshots`

Ingests an agent-reported environment snapshot capturing file hashes, package inventory, and runtime facts.

#### Status Codes & Error Envelopes
* `201 Created`: Snapshot recorded and committed.
* `401 Unauthorized`: Missing or invalid API key.
* `403 Forbidden`: Caller is not an authorized agent (`FORBIDDEN`).
* `422 Unprocessable Content`: Validation failure (malformed path, missing hash, or invalid package ecosystem format).

#### Request Body (`RecordSnapshotParams`)
```json
{
  "source_ref": "git:main:commit_abc123",
  "source_type": "agent_client",
  "verification_level": "agent_reported",
  "scan_scope": "full_repository",
  "snapshot_data": {
    "scanned_roots": ["."],
    "files": {
      "config/redis.conf": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    "unreadable_paths": [],
    "packages": {
      "pypi:redis": "5.0.1"
    },
    "packages_scope": "complete",
    "runtime": {
      "python": "3.12"
    },
    "runtime_scope": "complete"
  }
}
```

---

### 5.6 Establish Claim Conditions
`POST /api/v1/claims/{claim_id}/conditions`

Binds an initial versioned prerequisite condition set to an existing unconditioned claim against a recorded snapshot.

#### Status Codes & Error Envelopes
* `201 Created`: Initial condition set established (version 1), verification recorded, and claim `active_condition_version` updated.
* `401 Unauthorized`: Missing or invalid API key.
* `404 Not Found`: Claim or snapshot not found or belongs to another workspace.
* `409 Conflict`: Claim is already conditioned (`CONDITIONS_ALREADY_ESTABLISHED`).
* `422 Unprocessable Content`: Condition mismatch against snapshot (`CONDITION_SNAPSHOT_MISMATCH`), missing critical condition, or malformed condition payload.

#### Request Body (`EstablishConditionsParams`)
```json
{
  "based_on_snapshot_id": "018f3a20-0000-7000-8000-000000000005",
  "rationale": "Redis configuration and library version required for cluster mode assertion.",
  "conditions": [
    {
      "condition_type": "file_hash",
      "target_path": "config/redis.conf",
      "comparator": "hash_equals",
      "expected_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "is_critical": true
    },
    {
      "condition_type": "package_version",
      "target_path": "pypi:redis",
      "comparator": "version_equals",
      "expected_value": {"version": "5.0.1"},
      "is_critical": true
    }
  ]
}
```

---

### 5.7 Transient Condition Evaluation
`POST /api/v1/claims/{claim_id}/evaluate`

Evaluates whether a claim's active prerequisite conditions still hold in a specified environment snapshot.

**Strictly Read-Only:**
- Does **not** update claim status or increment version.
- Does **not** update `active_condition_version`.
- Does **not** create a `claim_verifications` record.
- Does **not** write an audit trail event.
- Does **not** issue transaction commits or flushes.

#### Precedence and Overall Outcome Semantics
| Claim State / Condition Result | Overall Outcome | `is_applicable` |
|---|---|---|
| Claim is retracted | `not_applicable` | `false` |
| Claim is superseded | `not_applicable` | `false` |
| Claim is disputed | `not_applicable` | `false` |
| Claim is `needs_review` | `not_applicable` | `false` |
| Claim has no active condition set | `unconditioned` | `false` |
| Any critical condition is `DRIFTED` | `environment_mismatch` | `false` |
| Any critical condition is `UNCHECKED` | `indeterminate` | `false` |
| All critical conditions are `SATISFIED` | `applicable` | `true` |

* **Precedence:** `DRIFTED` beats `UNCHECKED` when both occur on critical conditions.
* **Noncritical Conditions:** Noncritical conditions are evaluated and returned in the results list, but do not independently change the overall outcome.

#### Status Codes & Error Envelopes
* `200 OK`: Transient evaluation succeeded.
* `401 Unauthorized`: Missing or invalid API key.
* `403 Forbidden`: Caller is not an authorized agent.
* `404 Not Found`: Claim or snapshot not found, cross-workspace, or out-of-scope (`NOT_FOUND`).
* `422 Unprocessable Content`: Schema validation error (`VALIDATION_ERROR`).

#### Request Body (`EvaluateClaimConditionsRequest`)
```json
{
  "snapshot_id": "018f3a20-0000-7000-8000-000000000006"
}
```

#### Response (200 OK - `ClaimEvaluationResponse`)
```json
{
  "claim_id": "8a9b0c1d-2e3f-4a5b-6c7d-8e9f0a1b2c3d",
  "snapshot_id": "018f3a20-0000-7000-8000-000000000006",
  "active_condition_version": 1,
  "outcome": "applicable",
  "is_applicable": true,
  "condition_results": [
    {
      "condition_id": "018f3a20-0000-7000-8000-000000000010",
      "condition_type": "file_hash",
      "target_path": "config/redis.conf",
      "target": "config/redis.conf",
      "is_critical": true,
      "comparator": "hash_equals",
      "expected_value": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "observed_value": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "status": "SATISFIED",
      "reason": "HASH_MATCHES",
      "details": {
        "target_path": "config/redis.conf",
        "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
      }
    }
  ]
}
```

### 5.8 Formal Re-verification and Condition Versioning
`POST /api/v1/claims/{claim_id}/reverify`

Formally reverifies a claim against a newly recorded environment snapshot and persists an immutable `ClaimVerification` record.

#### Supported Operations
1. **Verify Against Existing Conditions (`action="verify_existing"`):**
   - Evaluates the snapshot against the current active condition set.
   - Persists a new `ClaimVerification` row (`verification_type="reverification"`).
   - Preserves active conditions and claim status without modification.
2. **Adopt Replacement Conditions (`action="adopt_new_conditions"`):**
   - Validates proposed conditions against the supplied snapshot (must all be `SATISFIED`).
   - Requires explicit adoption intent with rationale and at least one critical condition.
   - Atomically establishes a new immutable `ClaimConditionSet` (version $V+1$).
   - Atomically updates `claims.active_condition_version = V+1` and increments `claims.version`.
   - Persists a `ClaimVerification` record attesting applicability under the new version.

#### Concurrency and Lifecycle Rules
- **Optimistic Concurrency:** Caller must supply `expected_condition_version`. If a concurrent transaction adopted a newer version, the request is rejected with `409 Conflict` (`STALE_CONDITION_VERSION`).
- **Pessimistic Row Lock:** Row-level `SELECT ... FOR UPDATE` serializes concurrent reverifications on the same claim.
- **Terminal States:** Claims in `retracted` or `superseded` status cannot be reverified (rejected with `422 Unprocessable Content` / `INVALID_CLAIM_STATE`).
- **Review/Disputed Claims:** Claims in `needs_review` or `disputed` status can be reverified, but their lifecycle status is preserved and never silently altered.

#### Status Codes & Error Envelopes
* `200 OK`: Re-verification succeeded and verification record committed.
* `401 Unauthorized`: Missing or invalid API key.
* `403 Forbidden`: Caller is not an authorized agent (`FORBIDDEN`).
* `404 Not Found`: Claim or snapshot not found, cross-workspace, or out-of-scope (`NOT_FOUND`).
* `409 Conflict`: Stale active condition version (`STALE_CONDITION_VERSION`).
* `422 Unprocessable Content`: Condition mismatch against snapshot (`CONDITION_SNAPSHOT_MISMATCH`), terminal claim status (`INVALID_CLAIM_STATE`), unconditioned claim, or invalid adoption schema.

#### Request Body (`ReverifyClaimParams`)
```json
{
  "snapshot_id": "018f3a20-0000-7000-8000-000000000006",
  "action": "adopt_new_conditions",
  "expected_condition_version": 1,
  "attestation_notes": "Redis upgraded to 5.0.2 topology; verified clean operation.",
  "adopt_rationale": "Updated Redis library and config following minor version upgrade.",
  "proposed_conditions": [
    {
      "condition_type": "file_hash",
      "target_path": "config/redis.conf",
      "comparator": "hash_equals",
      "expected_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "is_critical": true
    }
  ]
}
```

#### Response (200 OK - `ReverifyClaimResponse`)
```json
{
  "verification_id": "018f3a20-0000-7000-8000-000000000020",
  "claim_id": "8a9b0c1d-2e3f-4a5b-6c7d-8e9f0a1b2c3d",
  "snapshot_id": "018f3a20-0000-7000-8000-000000000006",
  "condition_set_version": 2,
  "active_condition_version": 2,
  "verification_type": "reverification",
  "outcome": "applicable",
  "is_applicable": true,
  "action_taken": "adopt_new_conditions",
  "verified_by_agent": "018f3a20-0000-7000-8000-000000000002",
  "attestation_notes": "Redis upgraded to 5.0.2 topology; verified clean operation.",
  "condition_results": [
    {
      "condition_id": "018f3a20-0000-7000-8000-000000000021",
      "condition_type": "file_hash",
      "target_path": "config/redis.conf",
      "target": "config/redis.conf",
      "is_critical": true,
      "comparator": "hash_equals",
      "expected_value": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "observed_value": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "status": "SATISFIED",
      "reason": "HASH_MATCHES",
      "details": {
        "target_path": "config/redis.conf",
        "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
      }
    }
  ],
  "created_at": "2026-11-01T12:00:00.000Z"
}
```

---

## 6. Transaction & Audit Guarantees

1. **Transactional Boundary:** Every mutation route is injected with `session: AsyncSession = Depends(get_db)`. If the endpoint finishes without exception, `get_db()` issues `await session.commit()`. If an exception occurs, `get_db()` issues `await session.rollback()`.
2. **Atomic Audit Logging:** Service methods stage an `AuditEvent` within the active session prior to flush. If the transaction commits, the audit log commits; if it rolls back, the audit log rolls back.
3. **Trigger Protection:** Once committed, PostgreSQL's `trg_protect_audit_events` trigger permanently forbids `UPDATE` or `DELETE` on the generated audit event rows.

---

## 7. Open Decisions & Implementation Roadmap

1. **Scope Promotion Workflow:** In future milestones, transitioning a claim from `private` to `team` or `workspace` will require a dedicated promotion endpoint (`POST /api/v1/claims/{id}/promote`) with policy validation and promotion audit events.
2. **Supersession & Invalidation (Phase C):** Future endpoints will expose `POST /api/v1/claims/{id}/supersede` to atomically link replacement claims and trigger non-destructive cascade transitions (`needs_review`).
3. **Agent Management & Key Issuance:** For the upcoming implementation step, agents will be provisioned via migration seed scripts or internal fixtures rather than public registration routes to avoid unauthenticated agent creation.
