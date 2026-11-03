import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Button } from './Button';

describe('Button Component', () => {
  it('renders primary button with copper accent styling', () => {
    const { container } = render(<Button variant="primary">Submit Assertion</Button>);
    expect(screen.getByText('Submit Assertion')).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('bg-copper');
    expect(container.firstChild).toHaveClass('text-parchment-light');
  });

  it('renders secondary button with parchment and stone borders', () => {
    const { container } = render(<Button variant="secondary">Cancel Action</Button>);
    expect(screen.getByText('Cancel Action')).toBeInTheDocument();
    expect(container.firstChild).toHaveClass('bg-parchment-light');
    expect(container.firstChild).toHaveClass('border-stone-border');
  });

  it('handles click events and disabled state', () => {
    const handleClick = vi.fn();
    const { rerender } = render(<Button onClick={handleClick}>Click Me</Button>);

    fireEvent.click(screen.getByText('Click Me'));
    expect(handleClick).toHaveBeenCalledTimes(1);

    rerender(<Button onClick={handleClick} disabled>Click Me</Button>);
    fireEvent.click(screen.getByText('Click Me'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
});

