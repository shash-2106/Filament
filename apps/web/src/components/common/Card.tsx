import React from 'react';

interface CardProps {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  headerClassName?: string;
  bodyClassName?: string;
  badge?: React.ReactNode;
}

export const Card: React.FC<CardProps> = ({
  title,
  subtitle,
  actions,
  children,
  className = '',
  headerClassName = '',
  bodyClassName = '',
  badge,
}) => {
  return (
    <div className={`bg-parchment-light border border-stone-border rounded-sm overflow-hidden ${className}`}>
      {(title || actions || badge) && (
        <div className={`px-4 py-3 border-b border-stone-border/70 flex items-center justify-between gap-3 bg-parchment/60 ${headerClassName}`}>
          <div className="flex items-center gap-2.5">
            {badge && <div>{badge}</div>}
            <div>
              {title && <h3 className="font-editorial text-lg text-aubergine font-medium leading-tight">{title}</h3>}
              {subtitle && <p className="text-xs text-stone-muted font-sans mt-0.5">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={`p-4 ${bodyClassName}`}>{children}</div>
    </div>
  );
};

