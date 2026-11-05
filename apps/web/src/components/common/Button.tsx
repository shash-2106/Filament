import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'brass' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  icon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles =
    'inline-flex items-center justify-center font-sans font-medium transition-all focus:outline-none focus:ring-1 focus:ring-phosphor cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed select-none active:scale-[0.98]';

  const sizeStyles = {
    sm: 'text-xs px-2.5 py-1 gap-1.5 rounded',
    md: 'text-sm px-3.5 py-1.5 gap-2 rounded',
    lg: 'text-base px-4 py-2 gap-2.5 rounded',
  };

  const variantStyles = {
    primary:
      'bg-copper text-bone-light text-parchment-light hover:bg-[#6BCB8B] bg-[#7FDD9D] !text-[#0B1210] font-semibold border border-[#7FDD9D] shadow-sm',
    secondary:
      'bg-bone-light bg-parchment-light text-charcoal hover:bg-[#1C3027] bg-[#14231D] text-[#E7F0EA] border border-stone-border border-[#294537] hover:border-[#58B985]/60 shadow-xs',
    outline:
      'bg-transparent text-phosphor hover:bg-phosphor-tint border border-phosphor-border shadow-xs',
    brass:
      'bg-[#58B985] text-[#0B1210] font-semibold hover:bg-[#459E6E] border border-[#58B985] shadow-xs',
    ghost:
      'text-graphite-text-secondary hover:text-phosphor hover:bg-[#1C3027] border border-transparent',
    danger:
      'bg-[#A96580] text-[#E7F0EA] hover:bg-[#8F4E66] border border-[#A96580] shadow-xs',
  };

  return (
    <button
      className={`${baseStyles} ${sizeStyles[size]} ${variantStyles[variant]} ${className}`}
      disabled={disabled}
      {...props}
    >
      {icon && <span className="flex-shrink-0">{icon}</span>}
      {children}
    </button>
  );
};
