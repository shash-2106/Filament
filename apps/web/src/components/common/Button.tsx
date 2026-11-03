import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
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
  const baseStyles = 'inline-flex items-center justify-center font-sans font-medium transition-colors focus:outline-none focus:ring-1 focus:ring-copper cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed select-none';

  const sizeStyles = {
    sm: 'text-xs px-2.5 py-1 gap-1.5 rounded-sm',
    md: 'text-sm px-3.5 py-1.5 gap-2 rounded-sm',
    lg: 'text-base px-4 py-2 gap-2.5 rounded-sm',
  };

  const variantStyles = {
    primary: 'bg-copper text-parchment-light hover:bg-copper-hover border border-copper active:translate-y-[0.5px]',
    secondary: 'bg-parchment-light text-aubergine hover:bg-parchment border border-stone-border hover:border-stone-dark',
    ghost: 'text-aubergine-light hover:text-aubergine hover:bg-stone/20',
    danger: 'bg-terracotta text-parchment-light hover:bg-terracotta-dark border border-terracotta',
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

