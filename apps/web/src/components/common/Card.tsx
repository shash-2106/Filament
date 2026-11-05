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
  glass?: boolean;
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
  glass = false,
}) => {
  const containerStyle = glass
    ? 'glass-panel rounded overflow-hidden'
    : 'bg-[#14231D] border border-[#294537] rounded overflow-hidden shadow-xs hover:border-[#38604C] transition-colors';

  return (
    <div className={`${containerStyle} ${className}`}>
      {(title || actions || badge) && (
        <div
          className={`px-4 py-3 border-b border-[#294537] flex items-center justify-between gap-3 bg-[#111D18] ${headerClassName}`}
        >
          <div className="flex items-center gap-2.5">
            {badge && <div>{badge}</div>}
            <div>
              {title && (
                <h3 className="font-heading text-base text-graphite-text font-medium leading-tight">
                  {title}
                </h3>
              )}
              {subtitle && (
                <p className="text-xs text-graphite-text-tertiary font-sans mt-0.5">{subtitle}</p>
              )}
            </div>
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={`p-4 ${bodyClassName}`}>{children}</div>
    </div>
  );
};
