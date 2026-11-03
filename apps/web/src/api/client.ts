/**
 * Filament Typed API Client
 * Integrates directly with the FastAPI backend.
 */

import {
  Claim,
  ClaimDetail,
  ClaimEvaluationResponse,
  ConditionSetResponse,
  ApiResponseError,
} from './types';

export class ApiError extends Error {
  code: string;
  status: number;
  details?: any;

  constructor(status: number, code: string, message: string, details?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

export function getStoredApiKey(): string {
  return localStorage.getItem('filament_api_key') || '';
}

export function setStoredApiKey(key: string): void {
  localStorage.setItem('filament_api_key', key.trim());
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const apiKey = getStoredApiKey();
  const headers = new Headers(options.headers || {});

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (apiKey && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${apiKey}`);
  }

  const url = `${API_BASE_URL}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorCode = 'HTTP_ERROR';
    let errorMessage = `Request failed with status ${response.status} ${response.statusText}`;
    let errorDetails: any = null;

    try {
      const errorJson: ApiResponseError = await response.json();
      if (errorJson.error) {
        errorCode = errorJson.error.code || errorCode;
        errorMessage = errorJson.error.message || errorMessage;
        errorDetails = errorJson.error.details;
      }
    } catch {
      // Fallback to text if JSON parsing fails
      const text = await response.text().catch(() => '');
      if (text) errorMessage = text;
    }

    throw new ApiError(response.status, errorCode, errorMessage, errorDetails);
  }

  return response.json() as Promise<T>;
}

export const api = {
  // Health & Gateway
  async getHealth(): Promise<{ status: string; environment?: string }> {
    return request<{ status: string; environment?: string }>('/health');
  },

  // Claims & Memory
  async listClaims(params?: {
    status?: string;
    claim_type?: string;
    limit?: number;
    offset?: number;
  }): Promise<Claim[]> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.claim_type) searchParams.set('claim_type', params.claim_type);
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.offset) searchParams.set('offset', params.offset.toString());

    const qs = searchParams.toString();
    return request<Claim[]>(`/claims${qs ? `?${qs}` : ''}`);
  },

  async getClaim(claimId: string): Promise<ClaimDetail> {
    return request<ClaimDetail>(`/claims/${claimId}`);
  },

  async createClaim(data: {
    claim_type: string;
    subject: string;
    predicate: string;
    object_value: Record<string, any>;
    raw_statement: string;
    scope?: string;
    confidence?: number;
  }): Promise<Claim> {
    return request<Claim>('/claims', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // Conditions & Evaluation
  async evaluateClaim(claimId: string, snapshotId: string): Promise<ClaimEvaluationResponse> {
    return request<ClaimEvaluationResponse>(`/claims/${claimId}/evaluate`, {
      method: 'POST',
      body: JSON.stringify({ snapshot_id: snapshotId }),
    });
  },

  async reverifyClaim(
    claimId: string,
    params: {
      snapshot_id: string;
      action: 'verify_existing' | 'adopt_new_conditions';
      expected_condition_version: number;
      attestation_notes: string;
      adopt_rationale?: string;
      proposed_conditions?: any[];
    }
  ): Promise<any> {
    return request<any>(`/claims/${claimId}/reverify`, {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  async establishConditions(
    claimId: string,
    params: {
      based_on_snapshot_id: string;
      rationale: string;
      conditions: any[];
    }
  ): Promise<ConditionSetResponse> {
    return request<ConditionSetResponse>(`/claims/${claimId}/conditions`, {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  // Snapshots
  async recordSnapshot(data: any): Promise<any> {
    return request<any>('/snapshots', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};

