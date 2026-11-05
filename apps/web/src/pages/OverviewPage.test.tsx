import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { OverviewPage } from './OverviewPage';
import { renderWithProviders } from '../test/test-utils';
import * as queries from '../api/queries';
import { Claim } from '../api/types';

describe('OverviewPage Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const mockClaims: Claim[] = [
    {
      id: 'claim-111',
      workspace_id: 'default',
      agent_id: 'agent-1',
      claim_type: 'fact',
      subject: 'filament_api',
      predicate: 'uses_asyncpg',
      object_value: { driver: 'asyncpg' },
      raw_statement: 'Filament uses asynchronous SQLAlchemy engine with asyncpg driver.',
      scope: 'workspace',
      status: 'current',
      confidence: 1.0,
      version: 1,
      active_condition_version: 1,
      created_at: '2026-11-01T20:00:00Z',
      updated_at: '2026-11-01T20:00:00Z',
    },
    {
      id: 'claim-222',
      workspace_id: 'default',
      agent_id: 'agent-1',
      claim_type: 'constraint',
      subject: 'postgresql',
      predicate: 'requires_port_5433',
      object_value: { port: 5433 },
      raw_statement: 'PostgreSQL instance must be running on port 5433 with role filament_app.',
      scope: 'workspace',
      status: 'needs_review',
      confidence: 0.85,
      version: 1,
      active_condition_version: 2,
      created_at: '2026-11-01T20:05:00Z',
      updated_at: '2026-11-01T20:05:00Z',
    },
  ];

  it('renders overview header and workspace identity banner', () => {
    vi.spyOn(queries, 'useClaimsQuery').mockReturnValue({
      data: mockClaims,
      isLoading: false,
      isError: false,
    } as any);

    renderWithProviders(<OverviewPage />);

    expect(screen.getByText('Workspace Control Centre')).toBeInTheDocument();
    expect(screen.getByText('Default Workspace')).toBeInTheDocument();
    expect(screen.getByText(/Filament actively monitors AI knowledge/i)).toBeInTheDocument();
  });

  it('renders claims requiring review and recent claims ledger', () => {
    vi.spyOn(queries, 'useClaimsQuery').mockReturnValue({
      data: mockClaims,
      isLoading: false,
      isError: false,
    } as any);

    renderWithProviders(<OverviewPage />);

    // Needs review section
    expect(screen.getByText('Needs Review / Attention Queue')).toBeInTheDocument();
    // Because claim-222 is both in recent claims and review queue, getAllByText matches both
    const reviewStatements = screen.getAllByText('PostgreSQL instance must be running on port 5433 with role filament_app.');
    expect(reviewStatements.length).toBeGreaterThanOrEqual(1);

    // Recent memories
    expect(screen.getByText('Recent Agent Memories')).toBeInTheDocument();
    expect(screen.getByText('Filament uses asynchronous SQLAlchemy engine with asyncpg driver.')).toBeInTheDocument();
  });

  it('displays empty state when no claims exist in workspace', () => {
    vi.spyOn(queries, 'useClaimsQuery').mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as any);

    renderWithProviders(<OverviewPage />);

    expect(screen.getByText('No Memories Recorded Yet')).toBeInTheDocument();
    expect(screen.getByText('All memories healthy')).toBeInTheDocument();
  });
});
