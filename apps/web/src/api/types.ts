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

export interface ConditionEvaluationItem {
  condition_id: string | null;
  condition_type: ConditionType;
  target_path: string;
  target: string;
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
  outcome: 'applicable' | 'environment_mismatch' | 'indeterminate' | 'not_applicable' | 'unconditioned';
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

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: any;
}

export interface ApiResponseError {
  error: ApiErrorDetail;
}
