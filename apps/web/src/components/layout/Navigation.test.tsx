import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { Navigation } from './Navigation';
import { renderWithProviders } from '../../test/test-utils';
import * as queries from '../../api/queries';

describe('Navigation Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders brand masthead and 7 workstation navigation items', () => {
    vi.spyOn(queries, 'useHealthQuery').mockReturnValue({
      data: { status: 'healthy', version: '0.1.0' },
      isSuccess: true,
      isError: false,
      isLoading: false,
    } as any);

    renderWithProviders(<Navigation />, { route: '/' });

    expect(screen.getByText('FILAMENT')).toBeInTheDocument();
    expect(screen.getByText('Governed Agent Memory')).toBeInTheDocument();

    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Memory')).toBeInTheDocument();
    expect(screen.getByText('Evidence')).toBeInTheDocument();
    expect(screen.getByText('Dependencies')).toBeInTheDocument();
    expect(screen.getByText('Agents')).toBeInTheDocument();
    expect(screen.getByText('Integrations')).toBeInTheDocument();
    expect(screen.getByText('Activity')).toBeInTheDocument();
  });

  it('displays gateway status when health query succeeds', () => {
    vi.spyOn(queries, 'useHealthQuery').mockReturnValue({
      data: { status: 'healthy', version: '0.1.0' },
      isSuccess: true,
      isError: false,
      isLoading: false,
    } as any);

    renderWithProviders(<Navigation />);

    expect(screen.getByText('Gateway API')).toBeInTheDocument();
    expect(screen.getByText('healthy')).toBeInTheDocument();
  });

  it('displays offline status when health check fails', () => {
    vi.spyOn(queries, 'useHealthQuery').mockReturnValue({
      data: undefined,
      isSuccess: false,
      isError: true,
      isLoading: false,
    } as any);

    renderWithProviders(<Navigation />);

    expect(screen.getByText('Gateway API')).toBeInTheDocument();
    expect(screen.getByText('offline')).toBeInTheDocument();
  });
});
