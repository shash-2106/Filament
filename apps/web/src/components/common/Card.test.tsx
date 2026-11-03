import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Card } from './Card';

describe('Card Component', () => {
  it('renders card title, subtitle, and body content with editorial styling', () => {
    render(
      <Card
        title="Validity Invariants"
        subtitle="Core backend governance rules"
      >
        <p>Condition evaluation requires exact hash matching.</p>
      </Card>
    );

    expect(screen.getByText('Validity Invariants')).toBeInTheDocument();
    expect(screen.getByText('Core backend governance rules')).toBeInTheDocument();
    expect(screen.getByText('Condition evaluation requires exact hash matching.')).toBeInTheDocument();
  });

  it('renders card action and badge elements', () => {
    render(
      <Card
        title="Attention Queue"
        badge={<span data-testid="test-badge">Alert</span>}
        actions={<button>View All</button>}
      >
        <span>Content</span>
      </Card>
    );

    expect(screen.getByTestId('test-badge')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'View All' })).toBeInTheDocument();
  });
});

