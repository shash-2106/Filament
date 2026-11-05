import React from 'react';
import { LucideIcon } from 'lucide-react';
import { Button } from './Button';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  unconnectedNotice?: boolean;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  unconnectedNotice = false,
  className = '',
}) => {
  return (
    <div
      className={`p-8 text-center border border-dashed border-stone-border rounded-sm bg-bone/40 flex flex-col items-center justify-center relative overflow-hidden ${className}`}
    >
      {/* Subtle background neural motif */}
      <div className="absolute inset-0 opacity-10 pointer-events-none flex items-center justify-center">
        <svg viewBox="0 0 200 200" className="w-64 h-64 text-copper" fill="none">
          <circle cx="100" cy="100" r="60" stroke="currentColor" strokeWidth="1" strokeDasharray="3 3" />
          <path d="M40 100 Q100 40 160 100 T200 160" stroke="currentColor" strokeWidth="1" />
        </svg>
      </div>

      {Icon && (
        <div className="w-11 h-11 rounded-sm bg-bone-card flex items-center justify-center text-copper mb-3 border border-stone-border/80 shadow-xs relative z-10">
          <Icon className="w-5 h-5 text-copper" />
        </div>
      )}
      <h4 className="font-editorial text-xl text-charcoal font-medium mb-1 relative z-10">
        {title}
      </h4>
      <p className="text-sm text-stone-muted max-w-md font-sans mb-4 leading-relaxed relative z-10">
        {description}
      </p>

      {unconnectedNotice && (
        <div className="mb-4 inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono rounded-sm bg-brass/15 text-charcoal border border-brass/30 relative z-10">
          <span className="w-1.5 h-1.5 rounded-full bg-brass"></span>
          Capability not connected — pending backend route
        </div>
      )}

      {actionLabel && onAction && (
        <Button size="sm" onClick={onAction} className="relative z-10">
          {actionLabel}
        </Button>
      )}
    </div>
  );
};
