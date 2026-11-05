/**
 * Filament Domain Models and API Schemas
 * Strictly matches backend SQLAlchemy models and Pydantic DTOs.
 */

export type ClaimType = 'fact' | 'recommendation' | 'decision' | 'preference' | 'constraint';
export type ClaimScope = 'private' | 'team' | 'workspace';
export type ClaimStatus = 'current' | 'superseded' | 'disputed' | 'needs_review' | 'retracted';

export type SupportType = 'supports' | 'refutes' | 'mentions';
export type RelationType = 'contradicts' | 'refines' | 'depends_on' | 'supersedes';

export type ConditionType = 'file_hash' | 'lockfile_hash' | 'package_version' | 'runtime_fact';
export type Comparator = 'hash_equals' | 'version_equals' | 'runtime_equals';

export type VerificationType = 'initial' | 'reverification';
export type VerificationOutcome = 'applicable' | 'environment_mismatch' | 'indeterminate' | 'not_applicable' | 'unconditioned';

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  default_scope: ClaimScope;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceDetail {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
  current_agent: Agent;
}

export interface Claim {
  id: string;
  workspace_id: string;
  agent_id: string;
  claim_type: ClaimType;
  subject: string;
  predicate: string;
  object_value: Record<string, any>;
  raw_statement: string;
  scope: ClaimScope;
  status: ClaimStatus;
  confidence: number;
  version: number;
  active_condition_version: number | null;
  created_at: string;
  updated_at: string;
}

export interface LinkedEvidence {
  evidence_id: string;
  support_type: SupportType;
  confidence_weight: number;
  extraction_notes: string | null;
  source_type: string | null;
  created_at: string;
}

export interface ClaimDetailResponse {
  claim: Claim;
  evidence: LinkedEvidence[];
  provenance: LinkedEvidence[];
}

export type ClaimDetail = ClaimDetailResponse;

export interface Evidence {
  id: string;
  workspace_id: string;
  source_type: 'file' | 'git_commit' | 'user_turn' | 'tool_output' | 'api_response';
  source_uri: string;
  content_hash: string;
  raw_snippet: string;
  collected_by_agent: string | null;
  collected_by_user: string | null;
  metadata: Record<string, any>;
  created_at: string;
}

export interface ClaimRelation {
  id: string;
  workspace_id: string;
  source_claim_id: string;
  target_claim_id: string;
  relation_type: string;
  rationale: string;
  created_by_agent: string | null;
  created_at: string;
  affected_claim_ids?: string[];
}

export interface AuditEvent {
  id: string;
  workspace_id: string;
  actor_type: 'agent' | 'user' | 'system';
  actor_id: string;
  event_type: string;
  target_type: string;
  target_id: string;
  idempotency_key: string | null;
  payload: Record<string, any>;
  created_at: string;
}

export interface ConditionEvaluationItem {
  condition_id: string | null;
  condition_type: ConditionType;
  target_path: string;
  target?: string;
  is_critical: boolean;
  comparator: string;
  expected_value: any;
  observed_value: any;
  status: 'SATISFIED' | 'DRIFTED' | 'UNCHECKED';
  reason: string;
  details: Record<string, any>;
}

export interface ClaimEvaluationResponse {
  claim_id: string;
  snapshot_id: string;
  active_condition_version: number | null;
  outcome: VerificationOutcome;
  is_applicable: boolean;
  condition_results: ConditionEvaluationItem[];
}

export interface ClaimCondition {
  id: string;
  workspace_id: string;
  claim_id: string;
  condition_set_version: number;
  condition_type: ConditionType;
  target_path: string;
  comparator: string;
  expected_hash: string | null;
  expected_value: Record<string, any>;
  is_critical: boolean;
  created_at: string;
}

export interface ConditionSetResponse {
  id: string;
  workspace_id: string;
  claim_id: string;
  version: number;
  based_on_snapshot_id: string;
  established_by_agent: string;
  rationale: string;
  created_at: string;
  conditions: ClaimCondition[];
}

export interface SnapshotResponse {
  id: string;
  workspace_id: string;
  collected_by_agent: string;
  source_type: string;
  verification_level: string;
  source_ref: string;
  scan_scope: string;
  snapshot_data: {
    scanned_roots: string[];
    files: Record<string, string>;
    unreadable_paths?: string[];
    packages?: Record<string, any>;
    runtime?: Record<string, any>;
  };
  created_at: string;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: any;
}

export interface ApiResponseError {
  error: ApiErrorDetail;
}

export interface CandidateMemory {
  temp_id: string;
  subject: string;
  predicate: string;
  statement: string;
  claim_type: ClaimType;
  scope: ClaimScope;
  confidence: number;
  evidence_quote: string;
  source_reference?: string;
  suggested_validity_requirements: string[];
  relevant_files: string[];
  uncertainty_notes?: string;
  suggested_relationships: string[];
}

export interface ExtractionEstimateResponse {
  estimated_input_tokens: number;
  max_output_tokens: number;
  estimated_cost_usd: number;
  model: string;
  remaining_lifetime_budget_usd: number;
  remaining_test_budget_usd: number;
  gateway_enabled: boolean;
}

export interface ExtractMemoriesResponse {
  candidates: CandidateMemory[];
  usage: {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    cost_usd: number;
  };
  provider_request_id?: string;
  record_id: string;
  model: string;
  explanation: string;
}

export interface ApproveCandidateRequest {
  subject: string;
  predicate: string;
  statement: string;
  claim_type: ClaimType;
  scope: ClaimScope;
  confidence: number;
  evidence_quote: string;
  source_uri?: string;
  snapshot_id?: string;
  condition_rules?: string[];
}

export interface ApproveCandidateResponse {
  claim_id: string;
  evidence_id: string;
  condition_set_id?: string;
  status: string;
  message: string;
}
