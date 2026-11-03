import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Badge } from './Badge';

describe('Badge Component', () => {
  it('renders status badge for current with sage color scheme', () => {
    const { container } = render(<Badge variant="status" status="current" />);
    expect(screen.getByText('current')).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('bg-sage/15');
    expect(container.firstChild).toHaveClass('text-sage-dark');
  });

  it('renders status badge for needs_review with terracotta pulse', () => {
    const { container } = render(<Badge variant="status" status="needs_review" />);
    expect(screen.getByText('needs review')).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('bg-terracotta/15');
    expect(container.firstChild).toHaveClass('text-terracotta-dark');
  });

  it('renders claim type badges with uppercase monospace styling', () => {
    render(<Badge variant="type" type="architecture" />);
    expect(screen.getByText('architecture')).toBeInTheDocument();
  });

  it('renders scope badges properly', () => {
    render(<Badge variant="scope" scope="repo" />);
    expect(screen.getByText('repo')).toBeInTheDocument();
  });

  it('renders outcome badges with correct labels', () => {
    render(<Badge variant="outcome" outcome="applicable" />);
    expect(screen.getByText(/applicable/i)).toBeInTheDocument();

    render(<Badge variant="outcome" outcome="environment_mismatch" />);
    expect(screen.getByText(/drifted/i)).toBeInTheDocument();
  });

  it('renders citron highlight variant', () => {
    const { container } = render(<Badge variant="citron">Active Focus</Badge>);
    expect(screen.getByText('Active Focus')).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('bg-citron/25');
  });
});
