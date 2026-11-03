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
    <div className={`p-8 text-center border border-dashed border-stone-border rounded-sm bg-parchment/40 flex flex-col items-center justify-center ${className}`}>
      {Icon && (
        <div className="w-10 h-10 rounded-sm bg-stone-light/60 flex items-center justify-center text-aubergine-light mb-3 border border-stone-border/60">
          <Icon className="w-5 h-5 text-copper" />
        </div>
      )}
      <h4 className="font-editorial text-lg text-aubergine font-medium mb-1">{title}</h4>
      <p className="text-sm text-stone-muted max-w-md font-sans mb-4 leading-relaxed">{description}</p>

      {unconnectedNotice && (
        <div className="mb-4 inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono rounded-sm bg-citron/20 text-aubergine border border-citron-dark/30">
          <span className="w-1.5 h-1.5 rounded-full bg-citron-dark"></span>
          Capability not connected — pending backend route
        </div>
      )}

      {actionLabel && onAction && (
        <Button size="sm" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
};

