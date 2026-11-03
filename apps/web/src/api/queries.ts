/**
 * TanStack Query hooks for Filament API.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, getStoredApiKey } from './client';
import { Claim, ClaimDetail, ClaimEvaluationResponse } from './types';

export const queryKeys = {
  health: ['health'] as const,
  claims: (params?: Record<string, any>) => ['claims', params] as const,
  claim: (id: string) => ['claim', id] as const,
};

export function useHealthQuery() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => api.getHealth(),
    retry: 1,
    refetchInterval: 30000,
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
    },
  });
}

