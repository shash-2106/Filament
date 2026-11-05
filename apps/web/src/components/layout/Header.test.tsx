import React from 'react';
import { describe, it, expect } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { Header } from './Header';
import { renderWithProviders } from '../../test/test-utils';

describe('Header Component', () => {
  it('renders repository and workspace context', () => {
    renderWithProviders(<Header />);

    expect(screen.getByText('repo:')).toBeInTheDocument();
    expect(screen.getByText('filament/core')).toBeInTheDocument();
    expect(screen.getByText('Default Workspace')).toBeInTheDocument();
    expect(screen.getByText('(default-workspace)')).toBeInTheDocument();
  });

  it('renders search input for claims and memories', () => {
    renderWithProviders(<Header />);

    const searchInput = screen.getByPlaceholderText(/Search memories, evidence hashes/i);
    expect(searchInput).toBeInTheDocument();
  });

  it('allows opening and closing the API Key configuration modal', () => {
    renderWithProviders(<Header />, { apiKey: '' });

    const authButton = screen.getByText('Configure API Key');
    fireEvent.click(authButton);

    expect(screen.getByText('Agent Authentication')).toBeInTheDocument();
    expect(screen.getByText('Save Credentials')).toBeInTheDocument();

    const closeButton = screen.getByRole('button', { name: /Cancel/i });
    fireEvent.click(closeButton);

    expect(screen.queryByText('Agent Authentication')).not.toBeInTheDocument();
  });
});
