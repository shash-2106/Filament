/**
 * TanStack Query hooks for Filament API.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, getStoredApiKey } from './client';
import {
  Claim,
  ClaimDetail,
  ClaimEvaluationResponse,
  WorkspaceDetail,
  Agent,
  Evidence,
  ClaimRelation,
  AuditEvent,
  SnapshotResponse,
  ConditionSetResponse,
} from './types';

export const queryKeys = {
  health: ['health'] as const,
  workspaceCurrent: ['workspace', 'current'] as const,
  agents: ['agents'] as const,
  claims: (params?: Record<string, any>) => ['claims', params] as const,
  claim: (id: string) => ['claim', id] as const,
  evidence: (params?: Record<string, any>) => ['evidence', params] as const,
  relations: (relType?: string) => ['relations', relType] as const,
  audit: (params?: Record<string, any>) => ['audit', params] as const,
};

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => api.getHealth(),
    retry: 1,
    refetchInterval: 30000,
  });
}

export function useCurrentWorkspaceQuery() {
  const apiKey = getStoredApiKey();
  return useQuery<WorkspaceDetail, ApiError>({
    queryKey: queryKeys.workspaceCurrent,
    queryFn: () => api.getCurrentWorkspace(),
    enabled: Boolean(apiKey),
    retry: false,
  });
}

export function useAgentsQuery() {
  const apiKey = getStoredApiKey();
  return useQuery<Agent[], ApiError>({
    queryKey: queryKeys.agents,
    queryFn: () => api.listAgents(),
    enabled: Boolean(apiKey),
    retry: false,
  });
}

export function useClaimsQuery(params?: {
  status?: string;
  claim_type?: string;
  limit?: number;
  offset?: number;
}) {
  const apiKey = getStoredApiKey();
  return useQuery<Claim[], ApiError>({
    queryKey: queryKeys.claims(params),
    queryFn: () => api.listClaims(params),
    enabled: Boolean(apiKey),
    retry: false,
  });
}

export function useClaimDetailQuery(claimId: string | null) {
  return useQuery<ClaimDetail, ApiError>({
    queryKey: queryKeys.claim(claimId || ''),
    queryFn: () => {
      if (!claimId) throw new Error('claimId required');
      return api.getClaim(claimId);
    },
    enabled: Boolean(claimId),
    retry: false,
  });
}

export function useEvidenceQuery(params?: { source_type?: string; limit?: number }) {
  const apiKey = getStoredApiKey();
  return useQuery<Evidence[], ApiError>({
    queryKey: queryKeys.evidence(params),
    queryFn: () => api.listEvidence(params),
    enabled: Boolean(apiKey),
    retry: false,
  });
}

export function useClaimRelationsQuery(relationType?: string) {
  const apiKey = getStoredApiKey();
  return useQuery<ClaimRelation[], ApiError>({
    queryKey: queryKeys.relations(relationType),
    queryFn: () => api.listClaimRelations(relationType),
    enabled: Boolean(apiKey),
    retry: false,
  });
}

export function useAuditEventsQuery(params?: { event_type?: string; limit?: number }) {
  const apiKey = getStoredApiKey();
  return useQuery<AuditEvent[], ApiError>({
    queryKey: queryKeys.audit(params),
    queryFn: () => api.listAuditEvents(params),
    enabled: Boolean(apiKey),
    retry: false,
  });
}

// Mutations
export function useCreateClaimMutation() {
  const queryClient = useQueryClient();
  return useMutation<Claim, ApiError, any>({
    mutationFn: (data) => api.createClaim(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['claims'] });
      queryClient.invalidateQueries({ queryKey: ['audit'] });
    },
  });
}

export function useRecordEvidenceMutation() {
  const queryClient = useQueryClient();
  return useMutation<Evidence, ApiError, any>({
    mutationFn: (data) => api.recordEvidence(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['evidence'] });
      queryClient.invalidateQueries({ queryKey: ['audit'] });
    },
  });
}

export function useLinkEvidenceMutation() {
  const queryClient = useQueryClient();
  return useMutation<any, ApiError, { claimId: string; data: any }>({
    mutationFn: ({ claimId, data }) => api.linkEvidence(claimId, data),
    onSuccess: (_, { claimId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.claim(claimId) });
      queryClient.invalidateQueries({ queryKey: ['audit'] });
    },
  });
}

export function useRecordSnapshotMutation() {
  return useMutation<SnapshotResponse, ApiError, any>({
    mutationFn: (data) => api.recordSnapshot(data),
  });
}

export function useEstablishConditionsMutation() {
  const queryClient = useQueryClient();
  return useMutation<ConditionSetResponse, ApiError, { claimId: string; params: any }>({
    mutationFn: ({ claimId, params }) => api.establishConditions(claimId, params),
    onSuccess: (_, { claimId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.claim(claimId) });
      queryClient.invalidateQueries({ queryKey: ['claims'] });
      queryClient.invalidateQueries({ queryKey: ['audit'] });
    },
  });
}

export function useEvaluateClaimMutation() {
  return useMutation<ClaimEvaluationResponse, ApiError, { claimId: string; snapshotId: string }>({
    mutationFn: ({ claimId, snapshotId }) => api.evaluateClaim(claimId, snapshotId),
  });
}

export function useReverifyClaimMutation() {
  const queryClient = useQueryClient();
  return useMutation<
    any,
    ApiError,
    {
      claimId: string;
      params: {
        snapshot_id: string;
        action: 'verify_existing' | 'adopt_new_conditions';
        expected_condition_version: number;
        attestation_notes: string;
        adopt_rationale?: string;
        proposed_conditions?: any[];
      };
    }
  >({
    mutationFn: ({ claimId, params }) => api.reverifyClaim(claimId, params),
    onSuccess: (_, { claimId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.claim(claimId) });
      queryClient.invalidateQueries({ queryKey: ['claims'] });
      queryClient.invalidateQueries({ queryKey: ['audit'] });
    },
  });
}
