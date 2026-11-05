import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { MemoryPage } from './MemoryPage';
import { renderWithProviders } from '../test/test-utils';
import * as queries from '../api/queries';
import { Claim } from '../api/types';

describe('MemoryPage Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockClaims: Claim[] = [
    {
      id: 'claim-abc-123',
      workspace_id: 'default',
      agent_id: 'agent-1',
      claim_type: 'fact',
      subject: 'filament_schema',
      predicate: 'enforces_isolation',
      object_value: { isolation: 'workspace' },
      raw_statement: 'Filament claims table links to active condition set via composite foreign key.',
      scope: 'workspace',
      status: 'current',
      confidence: 0.98,
      version: 1,
      active_condition_version: 1,
      created_at: '2026-11-01T20:00:00Z',
      updated_at: '2026-11-01T20:00:00Z',
    },
  ];

  it('renders memory browser with table headers and claims row', () => {
    vi.spyOn(queries, 'useClaimsQuery').mockReturnValue({
      data: mockClaims,
      isLoading: false,
      isError: false,
    } as any);

    renderWithProviders(<MemoryPage />);

    expect(screen.getByText('Workspace Memories')).toBeInTheDocument();
    expect(screen.getByText(/Condition-bound knowledge, decisions, and constraints/i)).toBeInTheDocument();
    expect(screen.getByText('Filament claims table links to active condition set via composite foreign key.')).toBeInTheDocument();
    expect(screen.getByText(/v1 \(req: v1\)/i)).toBeInTheDocument();
  });

  it('renders claim detail drawer when claim query param is present', () => {
    vi.spyOn(queries, 'useClaimsQuery').mockReturnValue({
      data: mockClaims,
      isLoading: false,
      isError: false,
    } as any);

    vi.spyOn(queries, 'useClaimDetailQuery').mockReturnValue({
      data: {
        claim: mockClaims[0],
        evidence: [],
        provenance: [],
      },
      isLoading: false,
      isError: false,
    } as any);

    renderWithProviders(<MemoryPage />, { route: '/memory?claim=claim-abc-123' });

    expect(screen.getByText('Structured Value')).toBeInTheDocument();
    expect(screen.getByText('Validity Requirements & Evaluation')).toBeInTheDocument();
    expect(screen.getByText(/Test whether this memory's environmental requirements are satisfied/i)).toBeInTheDocument();
  });
});
