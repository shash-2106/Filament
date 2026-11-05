import React from 'react';
import { ClaimStatus, ClaimType, ClaimScope, VerificationOutcome } from '../../api/types';

interface BadgeProps {
  children?: React.ReactNode;
  variant?: 'status' | 'type' | 'scope' | 'outcome' | 'citron' | 'neutral' | 'brass' | 'phosphor';
  status?: ClaimStatus;
  type?: ClaimType | string;
  scope?: ClaimScope | string;
  outcome?: VerificationOutcome | string;
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
  // Phosphor / Citron highlight variant (kept for test compatibility)
  if (variant === 'citron' || variant === 'brass' || variant === 'phosphor') {
    return (
      <span
        className={`inline-flex items-center px-2 py-0.5 text-xs font-mono rounded bg-citron/25 text-phosphor border border-phosphor/30 ${className}`}
      >
        {children}
      </span>
    );
  }

  // 1. Status Badges
  if (variant === 'status' || status) {
    const s = status || (children as ClaimStatus);
    switch (s) {
      case 'current':
        return (
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded bg-sage/15 text-sage-dark border border-sage/40 ${className}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-phosphor"></span>
            {children || 'current'}
          </span>
        );
      case 'needs_review':
        return (
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded bg-terracotta/15 text-terracotta-dark border border-terracotta/40 ${className}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#E5B45E] animate-pulse"></span>
            {children || 'needs review'}
          </span>
        );
      case 'disputed':
        return (
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded bg-terracotta/20 text-terracotta-dark border border-terracotta/50 ${className}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#A96580]"></span>
            {children || 'disputed'}
          </span>
        );
      case 'superseded':
        return (
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded bg-stone-light/60 text-stone-muted border border-stone-border/60 ${className}`}
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#7B8E85]"></span>
            {children || 'superseded'}
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded bg-stone-light/40 text-stone-muted border border-stone-border ${className}`}
          >
            {children || s}
          </span>
        );
    }
  }

  // 2. Memory Type Badges
  if (variant === 'type' || type) {
    const t = type || (children as ClaimType);
    return (
      <span
        className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider rounded bg-[#1C3027] text-phosphor border border-[#294537] font-medium ${className}`}
      >
        {children || String(t)}
      </span>
    );
  }

  // 3. Scope Badges
  if (variant === 'scope' || scope) {
    const sc = scope || (children as ClaimScope);
    return (
      <span
        className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono uppercase tracking-wider rounded bg-[#14231D] border border-[#294537] text-graphite-text-secondary font-medium ${className}`}
      >
        {children || String(sc)}
      </span>
    );
  }

  // 4. Verification Outcome Badges
  if (variant === 'outcome' || outcome) {
    const o = outcome || children;
    if (o === 'applicable') {
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded bg-sage/15 text-sage-dark border border-sage/40 ${className}`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-phosphor" />
          applicable
        </span>
      );
    }
    if (o === 'environment_mismatch' || o === 'drifted') {
      return (
        <span
          className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono font-medium rounded bg-terracotta/15 text-terracotta-dark border border-terracotta/40 ${className}`}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-[#D67D65]" />
          drifted
        </span>
      );
    }
    return (
      <span
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono rounded bg-stone-light text-stone-muted border border-stone-border ${className}`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-[#85968E]" />
        {String(o)}
      </span>
    );
  }

  // Default neutral
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 text-xs font-mono rounded bg-[#14231D] border border-[#294537] text-graphite-text-secondary ${className}`}
    >
      {children}
    </span>
  );
};
