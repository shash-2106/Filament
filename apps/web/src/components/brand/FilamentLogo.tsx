import React from 'react';

interface FilamentLogoProps {
  size?: 'sm' | 'md' | 'lg' | 'xl';
  animated?: boolean;
  className?: string;
  showWordmark?: boolean;
}

export const FilamentLogo: React.FC<FilamentLogoProps> = ({
  size = 'md',
  animated = false,
  className = '',
  showWordmark = false,
}) => {
  const dimensionMap = {
    sm: { box: 22, font: 'text-xs', sub: 'text-[9px]' },
    md: { box: 28, font: 'text-sm font-semibold tracking-wider', sub: 'text-[10px]' },
    lg: { box: 38, font: 'text-lg font-semibold tracking-wider', sub: 'text-xs' },
    xl: { box: 56, font: 'text-2xl font-bold tracking-wider', sub: 'text-sm' },
  };

  const { box, font, sub } = dimensionMap[size];

  return (
    <div className={`flex items-center gap-2.5 select-none ${className}`}>
      <div
        className="relative flex items-center justify-center flex-shrink-0"
        style={{ width: box, height: box }}
      >
        <svg
          viewBox="0 0 64 64"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="w-full h-full drop-shadow-sm"
        >
          <defs>
            <linearGradient id={`flGrad-${size}`} x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#7FDD9D" stopOpacity="0.95" />
              <stop offset="50%" stopColor="#58B985" stopOpacity="1" />
              <stop offset="100%" stopColor="#A4E8B8" stopOpacity="0.85" />
            </linearGradient>

            <radialGradient id={`flGlow-${size}`} cx="32" cy="32" r="20" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#7FDD9D" stopOpacity="0.25" />
              <stop offset="100%" stopColor="#7FDD9D" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* Deep Green-Graphite Container */}
          <rect width="64" height="64" rx="10" fill="#14231D" stroke="#294537" strokeWidth="1.5" />
          <circle cx="32" cy="32" r="20" fill={`url(#flGlow-${size})`} />

          {/* Precision Branching Neural Filaments forming subtle F-silhouette */}
          {/* Stem filament (Vertical spine) */}
          <path
            d="M20 14 L20 50"
            stroke="#58B985"
            strokeWidth="3"
            strokeLinecap="round"
          />

          {/* Top branching strand */}
          <path
            d="M20 18 C28 18, 36 14, 48 16"
            stroke={`url(#flGrad-${size})`}
            strokeWidth="3"
            strokeLinecap="round"
          />

          {/* Middle converging bridge & branch */}
          <path
            d="M20 32 C28 32, 34 30, 42 34"
            stroke={`url(#flGrad-${size})`}
            strokeWidth="2.5"
            strokeLinecap="round"
          />

          {/* Interconnected diagonal synapses */}
          <path
            d="M20 32 C30 26, 36 22, 48 16"
            stroke="#7FDD9D"
            strokeWidth="1.5"
            strokeDasharray="2 3"
            opacity="0.6"
          />
          <path
            d="M20 50 C28 46, 34 40, 42 34"
            stroke="#7FDD9D"
            strokeWidth="1.5"
            strokeDasharray="2 3"
            opacity="0.6"
          />

          {/* Signal travel animation along filament */}
          {animated && (
            <circle cx="20" cy="18" r="3" fill="#7FDD9D">
              <animate
                attributeName="cy"
                values="14;32;50;14"
                dur="4s"
                repeatCount="indefinite"
              />
            </circle>
          )}

          {/* Phosphor synaptic nodes */}
          <circle cx="20" cy="18" r="3" fill="#7FDD9D" stroke="#14231D" strokeWidth="1.5" />
          <circle cx="48" cy="16" r="3" fill="#A4E8B8" stroke="#14231D" strokeWidth="1.5" />
          <circle cx="20" cy="32" r="3" fill="#58B985" stroke="#14231D" strokeWidth="1.5" />
          <circle cx="42" cy="34" r="3" fill="#7FDD9D" stroke="#14231D" strokeWidth="1.5" />
          <circle cx="20" cy="50" r="3" fill="#58B985" stroke="#14231D" strokeWidth="1.5" />
        </svg>
      </div>

      {showWordmark && (
        <div className="flex flex-col">
          <span className={`font-heading ${font} text-graphite-text tracking-wider leading-tight`}>
            FILAMENT
          </span>
          <span className={`font-mono ${sub} text-graphite-text-tertiary uppercase tracking-widest leading-none mt-0.5`}>
            Neural Memory Platform
          </span>
        </div>
      )}
    </div>
  );
};
