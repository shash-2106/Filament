import React from 'react';
import { ClaimStatus, ClaimType, ClaimScope, VerificationOutcome } from '../../api/types';

interface BadgeProps {
  children?: React.ReactNode;
  variant?: 'status' | 'type' | 'scope' | 'outcome' | 'citron' | 'neutral';
  status?: ClaimStatus;
  type?: ClaimType;
  scope?: ClaimScope;
  outcome?: VerificationOutcome;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  status,
  type,
  scope,
  outcome,
  className = '',
}) => {
  // 1. Status Badges
  if (variant === 'status' || status) {
    const s = status || (children as ClaimStatus);
    switch (s) {
      case 'current':
        return (
          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-sage/15 text-sage-dark border border-sage/40 ${className}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-sage"></span>
            {children || 'current'}
          </span>
        );
      case 'needs_review':
        return (
          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-terracotta/15 text-terracotta-dark border border-terracotta/40 ${className}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-terracotta animate-pulse"></span>
            {children || 'needs review'}
          </span>
        );
      case 'disputed':
        return (
          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-terracotta/20 text-terracotta-dark border border-terracotta/50 ${className}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-terracotta"></span>
            {children || 'disputed'}
          </span>
        );
      case 'superseded':
        return (
          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-stone-light/60 text-stone-muted border border-stone-border/60 ${className}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-stone-dark"></span>
            {children || 'superseded'}
          </span>
        );
      case 'retracted':
        return (
          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-red-900/10 text-red-900 border border-red-900/30 ${className}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-red-800"></span>
            {children || 'retracted'}
          </span>
        );
    }
  }

  // 2. Claim Type Badges
  if (variant === 'type' || type) {
    const t = type || (children as ClaimType);
    return (
      <span className={`inline-flex items-center px-2 py-0.5 text-[11px] font-mono tracking-wider uppercase rounded-sm bg-stone-light/40 text-aubergine-surface border border-stone-border ${className}`}>
        {t}
      </span>
    );
  }

  // 3. Scope Badges
  if (variant === 'scope' || scope) {
    const sc = scope || (children as ClaimScope);
    return (
      <span className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono tracking-wider uppercase rounded-sm bg-parchment-dark/70 text-aubergine-light border border-stone-border/80 ${className}`}>
        {sc}
      </span>
    );
  }

  // 4. Outcome Badges
  if (variant === 'outcome' || outcome) {
    const o = outcome || (children as VerificationOutcome);
    switch (o) {
      case 'applicable':
        return (
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-sage/15 text-sage-dark border border-sage/40 ${className}`}>
            ✓ {children || 'applicable'}
          </span>
        );
      case 'environment_mismatch':
        return (
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-terracotta/15 text-terracotta-dark border border-terracotta/40 ${className}`}>
            ✗ {children || 'drifted'}
          </span>
        );
      case 'indeterminate':
        return (
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-amber-900/10 text-amber-950 border border-amber-900/20 ${className}`}>
            ? {children || 'indeterminate'}
          </span>
        );
      case 'not_applicable':
        return (
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-stone-light/60 text-stone-muted border border-stone-border ${className}`}>
            — {children || 'not applicable'}
          </span>
        );
      case 'unconditioned':
        return (
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-stone-light/40 text-stone-muted border border-stone-border/70 ${className}`}>
            ○ {children || 'unconditioned'}
          </span>
        );
    }
  }

  // 5. Citron Highlight Badge
  if (variant === 'citron') {
    return (
      <span className={`inline-flex items-center px-2 py-0.5 text-xs font-mono font-medium rounded-sm bg-citron/25 text-aubergine border border-citron-dark/40 ${className}`}>
        {children}
      </span>
    );
  }

  // Default neutral
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-mono rounded-sm bg-stone-light/50 text-aubergine border border-stone-border ${className}`}>
      {children}
    </span>
  );
};
